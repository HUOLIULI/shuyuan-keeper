# -*- coding: utf-8 -*-
# TVBox/影视仓 Python 爬虫 - 短剧网 daxju.py v1.0
# 站点: https://www.daxju.com/
# 只提取短剧分类, 忽略电影/电视剧/综艺/动漫
import re
import sys
import json
import time
import gzip
import threading
import urllib.parse
import urllib.request
import ssl

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass

CACHE_TTL = 1800
_HOST_CACHE = {"host": None, "ts": 0}
_REQ_CACHE = {}

# 必须用移动端UA, 否则会跳转到PC端JS渲染页面
UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1')

HOSTS = [
    "https://www.daxju.com",
]

# 只有短剧分类
CATEGORIES = [
    {"type_id": "26", "type_name": "短剧"},
]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _log(*args):
    try:
        print("[短剧网]", *args)
    except Exception:
        pass


def _http_get(url, referer=None, timeout=15):
    headers = {'User-Agent': UA, 'Accept': 'text/html,*/*;q=0.8',
               'Accept-Language': 'zh-CN,zh;q=0.9', 'Accept-Encoding': 'gzip'}
    if referer:
        headers['Referer'] = referer
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return raw.decode('utf-8', 'ignore')
        except Exception as e:
            _log("GET失败(%d/2)" % (attempt + 1), url[:80], repr(e)[:80])
            time.sleep(0.4)
    return ''


def _cache_get(key):
    v = _REQ_CACHE.get(key)
    if v and v[0] > time.time():
        return v[1]
    _REQ_CACHE.pop(key, None)
    return None


def _cache_set(key, val, ttl=CACHE_TTL):
    if len(_REQ_CACHE) > 256:
        _REQ_CACHE.clear()
    _REQ_CACHE[key] = (time.time() + ttl, val)


def _get(url, referer=None, ttl=CACHE_TTL):
    ck = 'G|%s|%s' % (url, referer or '')
    hit = _cache_get(ck)
    if hit is not None:
        return hit
    html = _http_get(url, referer=referer)
    if html:
        _cache_set(ck, html, ttl)
    else:
        _cache_set(ck, '', 30)
    return html


def _host():
    if _HOST_CACHE["host"] and _HOST_CACHE["ts"] > time.time():
        return _HOST_CACHE["host"]
    host = HOSTS[0].rstrip('/')
    _HOST_CACHE.update(host=host, ts=time.time() + 7200)
    return host


def _abs(u):
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http'):
        return u
    return _host() + u


def _fix_pic(u):
    if not u or u == '/':
        return ''
    return _abs(u)


def _parse_items(html):
    vods = []
    seen = set()
    # 详情页格式: /duanju/{子分类}/{id}/
    for m in re.finditer(r'<a[^>]*href="(/duanju/([^"]+)/(\d+)/?)"[^>]*>', html):
        a_tag = m.group(0)
        full_path, sub_cat, vid = m.group(1), m.group(2), m.group(3)
        if vid in seen:
            continue
        # 跳过播放链接
        if 'play-' in full_path:
            continue
        # 从a标签里提取标题
        title = ''
        tm = re.search(r'title="([^"]+)"', a_tag)
        if tm:
            title = tm.group(1).strip()
        if not title:
            continue
        # 海报提取: 两种格式都支持
        pic = ''
        # 1. 懒加载格式: data-original="..."
        dm = re.search(r'data-original="([^"]+)"', a_tag)
        if dm:
            pic = dm.group(1)
        # 2. 旧格式: background: url(...)
        if not pic:
            sm = re.search(r'background:\s*url\(["\']?([^"\')]+)["\']?\)', a_tag)
            if sm:
                pic = sm.group(1)
        seen.add(vid)
        vods.append({
            "vod_id": full_path,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": '',
        })
    return vods


def _parse_detail(html, vid=""):
    if not vid:
        m = re.search(r'/duanju/[^"]+/(\d+)/', html)
        vid = m.group(1) if m else ''
    # 标题
    title = ''
    m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if m:
        title = m.group(1).strip()
    else:
        tm = re.search(r'<title>([^<]+)</title>', html)
        if tm:
            t = tm.group(1).strip()
            # 去掉后缀: "xxx短剧,2026xxx在线看- 现代都市 - 短剧网"
            title = re.sub(r'(短剧|电视剧|电影).*?-.*?-.*$', '', t).strip()
            if not title:
                title = t
    # 海报
    pic = ''
    m = re.search(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"', html)
    if m:
        pic = m.group(1)
    # 播放列表: 格式 /duanju/.../play-{line}-{ep}.html
    plays = []
    eps = []
    for m in re.finditer(r'href="(/duanju/[^"]+/play-(\d+)-(\d+)\.html)"', html):
        path, line, ep = m.group(1), m.group(2), m.group(3)
        ep_num = int(ep)
        eps.append((ep_num, line, path))
    # 去重排序
    eps = sorted(set(eps))
    if eps:
        items = []
        for ep_num, line, path in eps:
            items.append('$'.join(['第%02d集' % ep_num, path]))
        urlstr = '#'.join(items)
        plays.append(("在线播放", urlstr))
    vod = {
        "vod_id": vid,
        "vod_name": title,
        "vod_pic": _fix_pic(pic),
        "type_name": '短剧',
        "vod_year": '',
        "vod_area": '',
        "vod_remarks": '',
        "vod_director": '',
        "vod_actor": '',
        "vod_content": '',
    }
    return vod, plays


def _parse_play(html):
    """播放页提取m3u8直链"""
    m3u8s = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
    return m3u8s[0] if m3u8s else ''


def home_content(filter_=False):
    return {
        "class": [{"type_id": c["type_id"], "type_name": c["type_name"]} for c in CATEGORIES],
        "filters": {},
    }


def home_video_content():
    html = _get(_host() + '/list/index.php?26-1.html', ttl=3600)
    vods = _parse_items(html) if html else []
    return {"list": vods[:36]}


def category_content(tid, pg="1", filter_=None, extend=None):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if pg < 1:
        pg = 1
    base = _host()
    url = '%s/list/index.php?%s-%d.html' % (base, tid, pg)
    html = _get(url)
    vods = _parse_items(html) if html else []
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": 24,
        "total": 999999 if vods else 0,
    }


def detail_content(ids):
    if isinstance(ids, list):
        ids = ids[0]
    path = str(ids).strip()
    if not path.startswith('/'):
        return {"list": []}
    url = _host() + path
    html = _get(url)
    if not html:
        return {"list": []}
    vod, plays = _parse_detail(html)
    if not vod["vod_name"]:
        return {"list": []}
    if plays:
        vod["vod_play_from"] = '$$$'.join(nm for nm, _ in plays)
        vod["vod_play_url"] = '$$$'.join(urls for _, urls in plays)
    else:
        vod["vod_play_from"] = '在线播放'
        vod["vod_play_url"] = '正片$' + path + 'play-0-0.html'
    return {"list": [vod]}


def search_content(key, quick=False, pg="1"):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if not key or pg < 1:
        return {"list": [], "page": pg}
    wd = urllib.parse.quote(key)
    url = '%s/search.php?searchtype=5&searchword=%s&tid=26&page=%d' % (_host(), wd, pg)
    html = _get(url)
    vods = _parse_items(html) if html else []
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": 24,
        "total": 999999 if vods else 0,
    }


def play_parse(flag, id_, flags=None):
    pid = str(id_ or '').strip()
    hdr = json.dumps({"User-Agent": UA, "Referer": _host() + '/'}, ensure_ascii=False)
    if not pid.startswith('/'):
        return {"parse": 0, "url": "", "header": hdr, "playUrl": ""}
    url = _host() + pid
    html = _get(url, referer=_host() + '/', ttl=1800)
    m3u8 = _parse_play(html) if html else ''
    return {"parse": 0, "url": m3u8, "header": hdr, "playUrl": ""}


class Spider(_BaseSpider):
    def getName(self):
        return "短剧网"

    def init(self, extend=""):
        def warm():
            try:
                h = _host()
                _get(h + '/list/index.php?26-1.html', ttl=1800)
            except Exception:
                pass
        try:
            threading.Thread(target=warm, daemon=True).start()
        except Exception:
            pass
        self.site = HOSTS[0]

    def destroy(self):
        pass

    def homeContent(self, filter):
        try:
            return home_content(filter)
        except Exception as e:
            _log("homeContent异常", repr(e)[:100])
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        try:
            return home_video_content()
        except Exception as e:
            _log("homeVideoContent异常", repr(e)[:100])
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            return category_content(tid, pg, filter, extend)
        except Exception as e:
            _log("categoryContent异常", repr(e)[:100])
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            return search_content(key, quick, pg)
        except Exception as e:
            _log("searchContent异常", repr(e)[:100])
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, array):
        try:
            return detail_content(array)
        except Exception as e:
            _log("detailContent异常", repr(e)[:100])
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            return play_parse(flag, id)
        except Exception as e:
            _log("playerContent异常", repr(e)[:100])
            return {"parse": 0, "url": "", "playUrl": "", "header": ""}

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False


if __name__ == "__main__":
    print("短剧网爬虫 v1.0")





