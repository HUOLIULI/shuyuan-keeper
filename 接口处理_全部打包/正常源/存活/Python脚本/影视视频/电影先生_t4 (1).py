# -*- coding: utf-8 -*-
# 电影先生 T4
# 站点: https://eas4.dyxs61.com
# 2026-10-09:
#   1. 必须用手机 UA, 桌面 UA 返回"请使用手机端访问"
#   2. 分类: /vodtype/{tid}/ (电影/连续剧/综艺/动漫/体育赛事/短剧)
#   3. 详情: /voddetail/{vid}/; 播放: /vodplay/{vid}-{route}-{ep}/ 页内 "url":"..." 取 m3u8
#   4. 封面直链
#   5. playerContent 返回整数 parse, 补 playUrl
#   6. 注意: m3u8 CDN (v4.ppqrrs.com) 在测试环境返回 403, 用户真机需验证
#   7. T4 规范: 基类四级兼容导入, 完整模块级转发函数

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    try:
        from base import Spider as BaseSpider
    except ImportError:
        try:
            from spider import Spider as BaseSpider
        except ImportError:
            class BaseSpider:
                def init(self, extend=""): pass
                def homeContent(self, filter): return {}
                def homeVideoContent(self): return {}
                def categoryContent(self, tid, pg, filter, extend): return {}
                def detailContent(self, ids): return {}
                def searchContent(self, key, quick, pg="1"): return {}
                def searchContentPage(self, key, quick, pg): return {}
                def playerContent(self, flag, id, vipFlags): return {}
                def localProxy(self, param): return [404, "text/plain", ""]
                def isVideoFormat(self, url): return False
                def manualVideoCheck(self): return False
                def getName(self): return ""


import re
import ssl
import time
import urllib.request
import urllib.parse


HOST = "https://eas4.dyxs61.com"
# 必须手机 UA
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
CATEGORIES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "5", "type_name": "体育赛事"},
    {"type_id": "6", "type_name": "短剧"},
]


class Spider(BaseSpider):

    def init(self, extend=""):
        self.headers = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        }
        try:
            self.ssl_ctx = ssl._create_unverified_context()
        except Exception:
            self.ssl_ctx = None
        self._detail_cache = {}

    def _get(self, url, timeout=20, retries=3):
        last = None
        for i in range(retries):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                kw = {"timeout": timeout}
                if self.ssl_ctx:
                    kw["context"] = self.ssl_ctx
                resp = urllib.request.urlopen(req, **kw)
                return resp.read().decode("utf-8", errors="ignore")
            except Exception as e:
                last = e
                time.sleep(1 + i)
        raise last if last else Exception("fetch failed")

    def _abs(self, url):
        if not url:
            return ""
        if url.startswith("http://"):
            # 明文 http 在手机端可能被拦, 能 https 就升
            url = "https://" + url[7:]
        if url.startswith("https://"):
            return url
        if url.startswith("//"):
            return "https:" + url
        return HOST + (url if url.startswith("/") else "/" + url)

    def _parse_list(self, html):
        items, seen = [], set()
        for m in re.finditer(r'<a[^>]*href="/voddetail/(\d+)/"[^>]*title="([^"]*)"[^>]*>', html):
            vid, title = m.group(1), m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            tag = m.group(0)
            # 封面: data-src (lazyload), src 只是 loading 占位图
            pic = ""
            pm = re.search(r'data-src="([^"]+)"', html[m.start():m.start()+2000])
            if not pm:
                pm = re.search(r'data-original="([^"]+)"', html[m.start():m.start()+2000])
            if pm:
                pic = self._abs(pm.group(1))
            items.append({
                "vod_id": vid,
                "vod_name": title.strip()[:80],
                "vod_pic": pic,
                "vod_remarks": "",
            })
        return items

    def getName(self):
        return "电影先生"

    def homeContent(self, filter):
        return {"class": CATEGORIES, "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        # 主分类暂无分页参数, 子分类如 /vodtype/101/ 可直接用
        url = f"{HOST}/vodtype/{tid}/"
        items = self._parse_list(self._get(url))
        return {
            "list": items,
            "page": pn,
            "pagecount": 1,
            "limit": len(items),
            "total": len(items),
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else str(ids)
        vid = re.search(r'(\d+)', vid).group(1)
        now = time.time()
        if vid in self._detail_cache:
            ts, d = self._detail_cache[vid]
            if now - ts < 300:
                return {"list": [d]}
        html = self._get(f"{HOST}/voddetail/{vid}/")
        t = re.search(r'<title>([^<]*)</title>', html)
        title = t.group(1).split("剧情介绍")[0].split("--")[0].strip() if t else vid
        pic = ""
        pm = re.search(r'data-src="([^"]+)"', html)
        if not pm:
            pm = re.search(r'data-original="([^"]+)"', html)
        if pm:
            pic = self._abs(pm.group(1))
        # 播放线路: /vodplay/{vid}-{route}-{ep}/
        eps_by_route = {}
        for m in re.finditer(r'href="(/vodplay/%s-(\d+)-(\d+)/)"[^>]*>([^<]*)</a>' % vid, html):
            href, route, ep, name = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            eps_by_route.setdefault(route, []).append((ep, name, href))
        if not eps_by_route:
            # 兜底: 所有 vodplay 链接
            for m in re.finditer(r'href="(/vodplay/%s-\d+-\d+/)"' % vid, html):
                href = m.group(1)
                parts = href.strip("/").split("/")[-1].split("-")
                if len(parts) >= 3:
                    eps_by_route.setdefault(parts[1], []).append((parts[2], f"第{parts[2]}集", href))
        pf, pu = [], []
        for route in sorted(eps_by_route.keys()):
            eps = sorted(eps_by_route[route], key=lambda x: int(x[0]) if x[0].isdigit() else 0)
            pf.append(f"线路{route}")
            # 首集直链, 其余播放时解析
            first_m3u8 = self._resolve_m3u8(self._abs(eps[0][2])) if eps else ""
            parts = []
            for i, (ep, name, href) in enumerate(eps):
                if i == 0 and first_m3u8:
                    parts.append(f"{name}${first_m3u8}")
                else:
                    parts.append(f"{name}${self._abs(href)}")
            pu.append("#".join(parts))
        d = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_year": "",
            "vod_area": "",
            "vod_class": "",
            "vod_content": "",
            "vod_play_from": "$$$".join(pf),
            "vod_play_url": "$$$".join(pu),
        }
        self._detail_cache[vid] = (now, d)
        return {"list": [d]}

    def searchContent(self, key, quick, pg="1"):
        # /vodsearch/{key}-------------/
        url = f"{HOST}/vodsearch/{urllib.parse.quote(key)}-------------/"
        try:
            items = self._parse_list(self._get(url))
        except Exception:
            items = []
        return {
            "list": items,
            "page": 1,
            "pagecount": 1,
            "limit": len(items),
            "total": len(items),
        }

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def _resolve_m3u8(self, play_url):
        try:
            html = self._get(play_url, timeout=20, retries=3)
            # "url":"https:\/\/...m3u8"
            m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
            if m:
                return m.group(1).replace("\\/", "/")
            m = re.search(r'(https?://[^"\'\s\\]+\.m3u8[^"\'\s\\]*)', html)
            return m.group(1) if m else ""
        except Exception:
            return ""

    def playerContent(self, flag, id, vipFlags):
        raw = str(id).split("$")[-1] if "$" in str(id) else str(id)
        header = {"User-Agent": UA, "Referer": HOST + "/"}
        m3u8 = ""
        if ".m3u8" in raw and raw.startswith("http"):
            m3u8 = raw
        elif "/vodplay/" in raw:
            m3u8 = self._resolve_m3u8(self._abs(raw))
        if not m3u8.startswith("http"):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": m3u8,
            "header": header,
        }

    def localProxy(self, param):
        return [404, "text/plain", ""]

    def isVideoFormat(self, url):
        return isinstance(url, str) and (".m3u8" in url or ".mp4" in url)

    def manualVideoCheck(self):
        return False


# ---------- 模块级转发 (T4 规范) ----------
_sp = None

def _ins():
    global _sp
    if _sp is None:
        _sp = Spider()
    return _sp

def init(extend=""):
    return _ins().init(extend)

def getName():
    return _ins().getName()

def homeContent(filter):
    return _ins().homeContent(filter)

def homeVideoContent():
    return _ins().homeVideoContent()

def categoryContent(tid, pg, filter, extend):
    return _ins().categoryContent(tid, pg, filter, extend)

def detailContent(ids):
    return _ins().detailContent(ids)

def searchContent(key, quick, pg="1"):
    return _ins().searchContent(key, quick, pg)

def searchContentPage(key, quick, pg):
    return _ins().searchContentPage(key, quick, pg)

def playerContent(flag, id, vipFlags):
    return _ins().playerContent(flag, id, vipFlags)

def localProxy(param):
    return _ins().localProxy(param)

def isVideoFormat(url):
    return _ins().isVideoFormat(url)

def manualVideoCheck():
    return _ins().manualVideoCheck()
