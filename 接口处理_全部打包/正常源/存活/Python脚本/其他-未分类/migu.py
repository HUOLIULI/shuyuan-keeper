# -*- coding: utf-8 -*-
# 咪咕视频 TVBox 蜘蛛 (FongMi 5.6.4 / Chaquopy)
# 首页/分类: www.miguvideo.com 频道页内嵌数据解析
# 详情:     webapi 网关 content-info v2
# 播放:     play.miguvideo.com App 接口签名 + ddCalcu(已实测打通, 标清免登录全集)
# 登录:     ext 填 {"userId":"你的用户ID","token":"你的token"} 或 "userId|token"
#           也可在 .py 同目录放 migu_config.txt, 内容两行: userId=xxx / token=xxx
#           登录后自动尝试更高画质(蓝光/高清),  token 失效时回落标清照常播。
import hashlib
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

H5_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
APP_UA = "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 7)"

GW = "https://webapi.miguvideo.com/gateway"
PLAY_HOST = "https://play.miguvideo.com/playurl/v1/play/playurl"
APP_VERSION = "2600037000"
SIGN_TAIL = "3ce941cc3cbc40528bfd1c64f9fdf6c0migu0123"
DD_KEYS = "cdabyzwxkl"
NO_APPCODE = ("641886683", "641886773")

CHANNELS = [
    ("电视剧", "121d155c2ce74e9f96e7fa80b502d062"),
    ("电影", "4b9bb7142c584534a73e78a0ef368ae1"),
    ("综艺", "72ab2f7507ce4970a6925546255145ed"),
    ("动漫", "97f2e611d636472fa84072a5d1f1bcc7"),
    ("纪实", "5fa4bf015b384c0db8fbfecbdf1c2365"),
    ("少儿", "8c69c248afaa4efd9757d53707c16f51"),
]
HOME_CHANNEL = "b1c29dcd91f94a0289bf6295140f43b2"  # 影视精选
PAGE_SIZE = 24


def _http_urllib(url, headers=None, data=None, timeout=15, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last = e
            time.sleep(1 + i)
    raise last


_JAVA_CLIENT = [None]


def _java_client():
    # FongMi 自带 OkHttp 栈:咪咕播放域名会按 TLS 指纹丢弃 Python 的连接,
    # App 自己的网络栈是"真 App"指纹,能通过。非安卓环境建不出来返回 None。
    if _JAVA_CLIENT[0] is not None:
        return _JAVA_CLIENT[0] or None
    try:
        from java import jclass
        Builder = jclass("okhttp3.OkHttpClient$Builder")
        TimeUnit = jclass("java.util.concurrent.TimeUnit")
        b = Builder()
        b.followRedirects(True)
        b.followSslRedirects(True)
        b.connectTimeout(15, TimeUnit.SECONDS)
        b.readTimeout(35, TimeUnit.SECONDS)
        b.writeTimeout(15, TimeUnit.SECONDS)
        _JAVA_CLIENT[0] = b.build()
    except Exception:
        _JAVA_CLIENT[0] = False
    return _JAVA_CLIENT[0] or None


def _java_http_bytes(url, headers=None, data=None):
    client = _java_client()
    if client is None:
        return None
    try:
        from java import jclass
        ReqBuilder = jclass("okhttp3.Request$Builder")
        rb = ReqBuilder()
        rb.url(str(url))
        ctype = "application/x-www-form-urlencoded"
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk == "content-type":
                ctype = str(v)
                continue
            if lk in ("content-length", "host"):
                continue
            try:
                rb.header(str(k), str(v))
            except Exception:
                pass
        if data is not None:
            MediaType = jclass("okhttp3.MediaType")
            RequestBody = jclass("okhttp3.RequestBody")
            rb.post(RequestBody.create(MediaType.parse(ctype), bytes(data)))
        resp = client.newCall(rb.build()).execute()
        code = 0
        try:
            code = int(resp.code())
        except Exception:
            pass
        out = b""
        try:
            bd = resp.body()
            if bd is not None:
                out = bytes(bd.bytes())
        except Exception:
            pass
        try:
            resp.close()
        except Exception:
            pass
        if code and not (200 <= code < 400) and not out:
            return None
        return out
    except Exception:
        return None


def _http(url, headers=None, data=None, timeout=15, retries=2):
    try:
        return _http_urllib(url, headers=headers, data=data,
                            timeout=timeout, retries=retries)
    except Exception:
        # Python 栈被目标站丢弃时回落 App 的 OkHttp 再试两次
        for _ in range(2):
            out = _java_http_bytes(url, headers=headers, data=data)
            if out:
                return out
            time.sleep(1)
        raise


def _http_json(url, headers=None, data=None, timeout=15, retries=2):
    raw = _http(url, headers=headers, data=data, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8", "ignore"))


class Spider(BaseSpider):
    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.user_id = ""
        self.token = ""
        self._chan_cache = {}

    def getName(self):
        return "咪咕视频"

    # ---------------- 配置 / 登录 ----------------
    def init(self, extend=""):
        uid, tok = "", ""
        ext = extend if isinstance(extend, str) else ""
        if ext:
            ext = ext.strip()
            if ext.startswith("{"):
                try:
                    d = json.loads(ext)
                    uid = str(d.get("userId") or d.get("user_id") or d.get("uid") or "")
                    tok = str(d.get("token") or d.get("userToken") or d.get("user_token") or "")
                except Exception:
                    pass
            elif "|" in ext:
                parts = ext.split("|", 1)
                uid, tok = parts[0].strip(), parts[1].strip()
        if not uid:
            uid, tok = self._read_config_file()
        self.user_id, self.token = uid, tok
        return True

    def _read_config_file(self):
        dirs = []
        try:
            dirs.append(os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass
        try:
            dirs.append(os.getcwd())
        except Exception:
            pass
        for d in dirs:
            try:
                p = os.path.join(d, "migu_config.txt")
                if os.path.isfile(p):
                    uid, tok = "", ""
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("userId="):
                                uid = line.split("=", 1)[1].strip()
                            elif line.startswith("token="):
                                tok = line.split("=", 1)[1].strip()
                    if uid:
                        return uid, tok
            except Exception:
                continue
        return "", ""

    def _logged_in(self):
        return bool(self.user_id and self.token)

    # ---------------- 频道页解析(首页/分类) ----------------
    def _channel_items(self, chan_hash):
        now = time.time()
        hit = self._chan_cache.get(chan_hash)
        if hit and now - hit[0] < 300:
            return hit[1]
        url = "https://www.miguvideo.com/p/channel/" + chan_hash
        raw = _http(url, headers={"User-Agent": PC_UA,
                                  "Referer": "https://www.miguvideo.com/"},
                    timeout=25, retries=2)
        html = raw.decode("utf-8", "ignore")
        items = self._parse_items(html)
        self._chan_cache[chan_hash] = (now, items)
        return items

    def _parse_items(self, html):
        items, seen = [], set()
        for m in re.finditer(r'"pID":"(\d{6,})"', html):
            pid = m.group(1)
            if pid in seen:
                continue
            back = html[max(0, m.start() - 700):m.start()]
            names = re.findall(r'"name":"((?:[^"\\]|\\.)*)"', back)
            if not names:
                continue
            name = names[-1]
            if not name or name in ("图文", "视频", "直播"):
                continue
            fwd = html[m.end():m.end() + 1600]
            if '"pics"' not in fwd and '"score"' not in fwd:
                continue
            pic = ""
            pm = re.search(r'"lowResolutionV":"(https?://[^"]+)"', fwd)
            if not pm:
                pm = re.search(r'"lowResolutionH":"(https?://[^"]+)"', fwd)
            if pm:
                pic = pm.group(1).replace("\\/", "/")
            remarks = ""
            um = re.search(r'"updateEP":"([^"]*)"', fwd)
            sm = re.search(r'"score":"([^"]*)"', fwd)
            if um and um.group(1):
                remarks = um.group(1)
            elif sm and sm.group(1):
                remarks = sm.group(1) + "分"
            seen.add(pid)
            items.append({"vod_id": pid, "vod_name": name,
                          "vod_pic": pic, "vod_remarks": remarks})
        return items

    def _page(self, items, pg):
        try:
            p = int(pg)
        except Exception:
            p = 1
        total = len(items)
        pagecount = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = (p - 1) * PAGE_SIZE
        return {"list": items[start:start + PAGE_SIZE], "page": p,
                "pagecount": pagecount, "limit": PAGE_SIZE, "total": total}

    def homeContent(self, filter=False):
        classes = [{"type_id": h, "type_name": n} for n, h in CHANNELS]
        lst = []
        try:
            lst = self._channel_items(HOME_CHANNEL)[:PAGE_SIZE]
        except Exception:
            pass
        return {"class": classes, "list": lst}

    def homeVideoContent(self):
        try:
            return {"list": self._channel_items(HOME_CHANNEL)[:PAGE_SIZE]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        try:
            items = self._channel_items(tid)
        except Exception:
            items = []
        return self._page(items, pg)

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        vid = ""
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        else:
            vid = str(ids or "")
        vod = self._detail_v2(vid) or self._detail_fallback(vid)
        return {"list": [vod] if vod else []}

    def _detail_v2(self, vid):
        try:
            d = _http_json(GW + "/program/v2/cont/content-info/" + vid,
                           headers={"User-Agent": H5_UA,
                                    "Referer": "https://m.miguvideo.com/"},
                           timeout=18, retries=2)
        except Exception:
            return None
        if not isinstance(d, dict) or d.get("code") != 200:
            return None
        data = (d.get("body") or {}).get("data") or {}
        if not data:
            return None
        pics = data.get("pics") or {}
        pic = pics.get("lowResolutionV") or pics.get("lowResolutionH") or ""
        eps = []
        for i, ep in enumerate(data.get("datas") or []):
            epid = str(ep.get("pID") or "")
            if not epid:
                continue
            ename = str(ep.get("name") or "")
            ename = re.sub(r"^《[^》]*》", "", ename).replace("：", " ").strip()
            if not ename:
                ename = "第%d集" % (i + 1)
            eps.append("%s$%s" % (ename, epid))
        if not eps:
            eps = ["正片$%s" % vid]
        type_name = ""
        dn = data.get("displayName") or {}
        if isinstance(dn, dict):
            type_name = dn.get("first") or ""
        return {
            "vod_id": vid,
            "vod_name": data.get("name") or "",
            "vod_pic": pic,
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_actor": data.get("actor") or "",
            "vod_director": data.get("director") or "",
            "vod_content": data.get("detail") or "",
            "vod_remarks": data.get("updateEP") or "",
            "type_name": type_name,
            "vod_play_from": "咪咕",
            "vod_play_url": "#".join(eps),
        }

    def _detail_fallback(self, vid):
        # content-info 挂时用播放接口的 content 兜底组选集
        try:
            body = self._playurl_raw(vid, 2)
        except Exception:
            return None
        if not body:
            return None
        content = body.get("content") or {}
        eps = []
        for sub in content.get("subcollectionList") or []:
            sid = str(sub.get("subSetId") or "")
            idx = sub.get("index") or (len(eps) + 1)
            if sid:
                eps.append("第%s集$%s" % (idx, sid))
        if not eps:
            cid = str(content.get("contId") or vid)
            eps = ["正片$%s" % cid]
        name = str(content.get("contName") or "")
        m = re.match(r"《([^》]*)》", name)
        return {
            "vod_id": vid,
            "vod_name": m.group(1) if m else name,
            "vod_pic": "",
            "vod_play_from": "咪咕",
            "vod_play_url": "#".join(eps),
        }

    # ---------------- 播放 ----------------
    def _playurl_raw(self, cont_id, rate):
        ts = str(int(time.time() * 1000))
        m1 = hashlib.md5((ts + str(cont_id) + APP_VERSION[:8]).encode()).hexdigest()
        sign = hashlib.md5((m1 + SIGN_TAIL).encode()).hexdigest()
        q = ("sign=%s&rateType=%s&contId=%s&timestamp=%s&salt=1230024"
             "&flvEnable=true&super4k=true&h265N=true"
             "&4kvivid=true&2Kvivid=true&vivid=2") % (sign, rate, cont_id, ts)
        headers = {"AppVersion": APP_VERSION, "TerminalId": "android",
                   "X-UP-CLIENT-CHANNEL-ID": "2600037000-99000-200300220100002",
                   "User-Agent": APP_UA}
        if str(cont_id) not in NO_APPCODE:
            headers["appCode"] = "miguvideo_default_android"
        if self._logged_in() and str(rate) != "2":
            headers["UserId"] = self.user_id
            headers["UserToken"] = self.token
        d = _http_json(PLAY_HOST + "?" + q, headers=headers, timeout=20, retries=2)
        if isinstance(d, dict):
            return d.get("body") or {}
        return {}

    def _ddcalcu(self, pudata, program_id, rate):
        words = ["v", "a", "0", "a"]
        uid = self.user_id if self._logged_in() else ""
        if uid:
            try:
                words[0] = DD_KEYS[int(uid[7])]
            except Exception:
                pass
        if str(rate) == "2":
            words[0] = "v"
        if 3 < len(uid) <= 8:
            words[0] = "e"
        datestr = datetime.now().strftime("%Y%m%d")
        out, n = [], len(pudata)
        for i in range(n // 2):
            out.append(pudata[n - 1 - i])
            out.append(pudata[i])
            if i == 1:
                out.append(words[0])
            elif i == 2:
                out.append(DD_KEYS[int(datestr[0])])
            elif i == 3:
                try:
                    out.append(DD_KEYS[int(str(program_id)[6])])
                except Exception:
                    out.append("a")
            elif i == 4:
                out.append(words[3])
        return "".join(out)

    def playerContent(self, flag, id, vipFlags=None):
        cont_id = str(id or "")
        rates = [4, 3, 2] if self._logged_in() else [2]
        for rate in rates:
            try:
                body = self._playurl_raw(cont_id, rate)
            except Exception:
                continue
            if not body:
                continue
            if body.get("rid") == "TIPS_NEED_MEMBER":
                continue
            url = ((body.get("urlInfo") or {}).get("url")) or ""
            if not url:
                continue
            ep_id = str((body.get("content") or {}).get("contId") or cont_id)
            if "&puData=" in url:
                pudata = url.split("&puData=")[1].split("&")[0]
                url = (url + "&ddCalcu=" + self._ddcalcu(pudata, ep_id, rate)
                       + "&sv=10004&ct=android")
            return {"parse": 0, "playUrl": "", "url": url,
                    "header": {"User-Agent": APP_UA}}
        return {"parse": 0, "playUrl": "", "url": ""}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        kw = urllib.parse.quote(str(key or ""))
        sid = uuid.uuid4().hex
        url = ("https://jadeite.migu.cn/search/v3/open-search/"
               "?searchKey=%s&pageNum=%s&pageSize=20&sid=%s") % (kw, pg or "1", sid)
        headers = {"User-Agent": H5_UA, "Referer": "https://www.miguvideo.com/",
                   "appId": "miguvideo",
                   "clientId": "f1bf515c-4006-4606-a752-2b4cdd9343d0"}
        items = []
        try:
            d = _http_json(url, headers=headers, timeout=15, retries=1)
            found = []
            self._walk_search(d, found)
            seen = set()
            for pid, name, pic in found:
                if pid in seen or not name:
                    continue
                seen.add(pid)
                items.append({"vod_id": pid, "vod_name": name,
                              "vod_pic": pic, "vod_remarks": "咪咕"})
        except Exception:
            items = []
        return {"list": items, "page": int(pg or 1), "pagecount": 1,
                "limit": 20, "total": len(items)}

    def _walk_search(self, node, out):
        if isinstance(node, dict):
            pid = node.get("contId") or node.get("pID") or node.get("contentId")
            name = node.get("name") or node.get("title") or node.get("contName")
            if pid and name and str(pid).isdigit():
                pic = ""
                pics = node.get("pics") or {}
                if isinstance(pics, dict):
                    pic = pics.get("lowResolutionV") or pics.get("lowResolutionH") or ""
                if not pic:
                    pic = node.get("pic") or node.get("img") or node.get("imgUrl") or ""
                out.append((str(pid), str(name), str(pic)))
            for v in node.values():
                self._walk_search(v, out)
        elif isinstance(node, list):
            for v in node:
                self._walk_search(v, out)

    def destroy(self):
        return True
