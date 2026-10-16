# -*- coding: utf-8 -*-
# 91动漫 (91dongman.net) TVBox / T3 Python Spider
# 站点: https://91dongman.net/
#
# ============ 封面色块根因（2026-10-08 二次修正） ============
# 1) 列表页封面 markup：
#      <img class="dm-cover__image"
#           src="/static/web/images/cover-placeholder-91dm.png"     ← 占位图，跳过
#           data-src="https://pic.wirqed.cn/....jpeg?auth_key=..."  ← 真封面（加密流）
# 2) 真封面是 AES-128-CBC 加密流，key/iv 为 16 字节 ASCII 常量：
#      key = f5d965df75336270
#      iv  = 97b60394abc2fbe1
#    解密后为原始 JPEG/PNG，PKCS7 去填充。实测 head = ffd8ffdb008400...
# 3) ★ 色块的直接原因不在解密，在【代理 URL 格式】：
#      错误: "proxy?do=jpg&url=..."        → 壳认不出 do 值，当普通 URL 直连图床
#                                            → 拿到加密流 → 显示色块
#      正确: "http://127.0.0.1:9978/proxy?do=py&url=" + quote(url, safe="")
#            · do 必须是 py —— 壳靠它定位 py 源的 localProxy
#            · 必须是完整 http 绝对地址，不能是相对路径
#            · url 必须 quote(safe="") 全编码，否则 url 里的 & 会截断参数
# 4) localProxy 必须返回【4 格】：[状态码, mime, bytes, headers]
#
# ============ 症状分流（纯黑/噪点=解密错；色块+汉字=代理URL错；灰块=没取到图） ============
#
# 取图模式可切换（_PIC_MODE）：
#   0 = 壳代理 do=py（默认，契约标准写法）
#   1 = 源内自起本地图服务（不依赖壳的代理实现，壳端口/形态不确定时用）
#   2 = data URI 内嵌（绕开一切网络环节，体积换稳定，适合条数少的列表）
#   3 = 直链（仅排障：区分「源问题」还是「壳代理问题」）

import base64
import re
import threading
from urllib.parse import quote, unquote, urljoin, urlparse, parse_qs

try:
    import requests
except ImportError:
    requests = None

try:
    import urllib.request as _urlreq
    import ssl as _ssl
    _CTX = _ssl.create_default_context()
    _CTX.check_hostname = False
    _CTX.verify_mode = _ssl.CERT_NONE
except Exception:
    _urlreq = None
    _CTX = None


# ============================ 可调参数 ============================

# 取图模式：0=壳代理 1=源内自服务 2=data URI 3=直链(排障)
_PIC_MODE = 0

# 壳的本地代理入口。do=py 必带（壳靠它找到 py 源的 localProxy）。
# 端口非 9978 的壳：站点 extend 里写 {"proxy_port": <端口>} 覆盖。
# 注意用函数拼串，不要把 "%d" 残留进最终 URL（2026-10-08 踩过：模板未替换 → 字面量 %d）
_SHELL_PROXY_PORT = 9978


def _shell_proxy_prefix():
    return "http://127.0.0.1:%d/proxy?do=py&url=" % _SHELL_PROXY_PORT

# 源内自起服务端口起点（_PIC_MODE=1 时使用，被占用自动顺延）
_SELF_PORT_BASE = 34567
_SELF_PORT_TRIES = 10

# 封面内存缓存条数
_PIC_CACHE_MAX = 200

# ============================ 封面解密常量 ============================

_AES_KEY = b"f5d965df75336270"
_AES_IV = b"97b60394abc2fbe1"

# 真封面在 data-src；src 是 cover-placeholder 占位图（旧的全页正则已废弃，见 _UNIT_RES）

# ★ 列表单元：必须按「单元」配对 (href + data-src + 标题)，不能全页分散匹配。
#   全页 href 正则会混入导航等杂链接 → 封面整体错位、末条缺图（2026-10-08 实测踩坑）。
#   列表/搜索页：  <article class="dm-card"> ... </article>
#   排行页：      <li class="dm-ranking-row"> ... </li>（desktop/mobile 双份 DOM，靠 vod_id 去重）
_UNIT_RES = (
    re.compile(r'<article[^>]*class="[^"]*dm-card[^"]*"[^>]*>[\s\S]*?</article>', re.I),
    re.compile(r'<li[^>]*class="[^"]*dm-ranking-(?:mobile-)?row[^"]*"[^>]*>[\s\S]*?</li>', re.I),
)

# 单元内详情链接优先取这些锚点，取不到再退回单元内第一个 href
_LINK_HINT_RE = re.compile(
    r'<a[^>]+class="[^"]*(?:dm-card__media|dm-card__title|dm-ranking-cover'
    r'|dm-ranking-row__main|dm-ranking-mobile-row__main)[^"]*"[^>]*href="([^"]+)"',
    re.I)
_ANY_HREF_RE = re.compile(r'href="([^"]+)"', re.I)

# 单元内标题优先 h2 / h3，再退回 title 类节点
_TITLE_RES = (
    re.compile(r'<h2[^>]*>([\s\S]*?)</h2>', re.I),
    re.compile(r'<h3[^>]*>([\s\S]*?)</h3>', re.I),
    re.compile(r'class="[^"]*(?:dm-card__title|dm-ranking-row__title'
               r'|dm-ranking-mobile-row__title)[^"]*"[^>]*>([\s\S]*?)</', re.I),
)

# 详情链接形态（实测三种，缺一种就会整类返回 0 条）：
#   /anime/<cat>/<id>/    动漫
#   /manga/<cat>/<id>/    漫画分类页（旧版路径）
#   /comic/<id>/          漫画（当前实际路径，manga/* 分类页里全是这个）
_DETAIL_RE = re.compile(r'/(anime|manga)/([a-z0-9-]+)/(\d+)/?$', re.I)
_COMIC_RE = re.compile(r'/comic/(\d+)/?$', re.I)

_TAG_RE = re.compile(r'<[^>]+>')
_ENT = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
        ("&#39;", "'"), ("&nbsp;", " "), ("&#x27;", "'"))


def _clean_text(s):
    """去标签、解实体、压空白。"""
    if not s:
        return ""
    s = _TAG_RE.sub("", s)
    for a, b in _ENT:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()

_IMG_SIG = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
)


def _sniff_mime(data):
    """按魔数嗅探图片 MIME，非图片返回空串。"""
    if not data:
        return ""
    for sig, mime in _IMG_SIG:
        if data.startswith(sig):
            return mime
    return ""


def _looks_encrypted(data):
    """密文判据：无图片魔数 + 长度 16 对齐。"""
    if not data or _sniff_mime(data):
        return False
    if len(data) % 16 != 0:
        return False
    return True


# ============================ 封面缓存（内存 LRU） ============================

_PIC_CACHE = {}
_PIC_CACHE_ORDER = []
_PIC_LOCK = threading.Lock()


def _cache_get(key):
    with _PIC_LOCK:
        if key in _PIC_CACHE:
            try:
                _PIC_CACHE_ORDER.remove(key)
            except ValueError:
                pass
            _PIC_CACHE_ORDER.append(key)
            return _PIC_CACHE[key]
    return None


def _cache_put(key, val):
    with _PIC_LOCK:
        if key not in _PIC_CACHE:
            _PIC_CACHE_ORDER.append(key)
        _PIC_CACHE[key] = val
        while len(_PIC_CACHE_ORDER) > _PIC_CACHE_MAX:
            old = _PIC_CACHE_ORDER.pop(0)
            _PIC_CACHE.pop(old, None)


# ============================ AES-128-CBC 解密 ============================

def _aes_decrypt(raw):
    """AES-CBC 解密封面。已是明文图或失败时原样返回。"""
    if not raw:
        return raw
    if _sniff_mime(raw):          # 已经是明文图
        return raw
    if len(raw) % 16 != 0:        # 不是密文块长度
        return raw
    try:
        from Crypto.Cipher import AES
        pt = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(raw)
        if _sniff_mime(pt):
            return pt
    except Exception:
        pass
    try:
        pt = _aes_cbc_decrypt_pure(raw, _AES_KEY, _AES_IV)
        if _sniff_mime(pt):
            return pt
    except Exception:
        pass
    return raw


# ---------- AES-128-CBC 纯 Python 兜底（零第三方依赖） ----------

_SBOX = None
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _build_sbox():
    global _SBOX
    if _SBOX is not None:
        return _SBOX
    p = q = 1
    sbox = [0] * 256
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) \
            ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    _SBOX = sbox
    return sbox


def _xtime(a):
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _expand_key(key):
    sbox = _build_sbox()
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [sbox[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [sbox[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _add_round_key(state, w, rnd):
    for c in range(4):
        for r in range(4):
            state[r][c] ^= w[rnd * 4 + c][r]


def _inv_sub_bytes(state):
    sbox = _build_sbox()
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    for r in range(4):
        for c in range(4):
            state[r][c] = inv[state[r][c]]


def _inv_shift_rows(state):
    for r in range(1, 4):
        state[r] = state[r][-r:] + state[r][:-r]


def _inv_mix_columns(state):
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
        state[1][c] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
        state[2][c] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
        state[3][c] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)


def _decrypt_block(block, w, nr):
    state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
    _add_round_key(state, w, nr)
    for rnd in range(nr - 1, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, w, rnd)
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, w, 0)
    return bytes(state[r][c] for c in range(4) for r in range(4))


def _aes_cbc_decrypt_pure(data, key, iv):
    """AES-128-CBC 解密（纯 Python，无第三方依赖）。"""
    w, nr = _expand_key(key)
    out = bytearray()
    prev = iv
    for off in range(0, len(data) - len(data) % 16, 16):
        blk = data[off:off + 16]
        dec = _decrypt_block(blk, w, nr)
        out += bytes(a ^ b for a, b in zip(dec, prev))
        prev = blk
    if out and 1 <= out[-1] <= 16 and out[-out[-1]:] == bytes([out[-1]]) * out[-1]:
        out = out[:-out[-1]]
    return bytes(out)


# ============================ 源内自起本地图服务（_PIC_MODE=1） ============================

_SELF_SERVER = None
_SELF_PORT = None
_SELF_LOCK = threading.Lock()


def _ensure_self_server(fetch_pic):
    """幂等启动本地图服务，端口被占用自动顺延。失败返回 None。"""
    global _SELF_SERVER, _SELF_PORT
    with _SELF_LOCK:
        if _SELF_SERVER is not None:
            return _SELF_PORT
        try:
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        except Exception:
            return None

        class _H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, ctype, body):
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    pass

            def do_GET(self):
                try:
                    qs = parse_qs(urlparse(self.path).query)
                    target = (qs.get("u") or qs.get("url") or [""])[0]
                    if not target:
                        return self._send(400, "text/plain", b"no url")
                    data = fetch_pic(target)
                    if not data:
                        return self._send(404, "text/plain", b"upstream fail")
                    mime = _sniff_mime(data) or "image/jpeg"
                    return self._send(200, mime, data)
                except Exception:
                    return self._send(500, "text/plain", b"err")

        for i in range(_SELF_PORT_TRIES):
            port = _SELF_PORT_BASE + i
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port), _H)
            except Exception:
                continue
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            _SELF_SERVER = srv
            _SELF_PORT = port
            return port
        return None


# ============================ Spider ============================

class Spider:
    def __init__(self):
        self.host = "https://91dongman.net"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": "age_verified=1; isAdult=1; adult=1",
        }
        self.extend = {}
        self.session = None
        self.s = None
        self.sess = None

    # ---------- 契约必备 ----------

    def getDependence(self):
        return []

    def getName(self):
        return "91动漫"

    def isVideoFormat(self, url):
        return any(x in (url or "").lower() for x in [".m3u8", ".mp4", ".flv"])

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        return None

    def init(self, extend=""):
        import json
        self.host = "https://91dongman.net"
        # extend 兼容：空串 / JSON 串 / dict
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}
        self.extend = extend

        port = extend.get("proxy_port")
        if port:
            try:
                globals()["_SHELL_PROXY_PORT"] = int(port)
            except Exception:
                pass

        mode = extend.get("pic_mode")
        if mode is not None:
            try:
                globals()["_PIC_MODE"] = int(mode)
            except Exception:
                pass

        if _PIC_MODE == 1:
            _ensure_self_server(self._fetch_cover)
        return self

    # ---------- 网络 ----------

    def _session(self):
        if requests is None:
            return None
        if self.session is None:
            try:
                s = requests.session()
                s.headers.update(self.headers)
                self.session = self.s = self.sess = s
            except Exception:
                self.session = None
        return self.session

    def fetch(self, url, headers=None):
        """取文本。requests 优先，urllib 降级（壳里可能没有 requests）。"""
        h = dict(self.headers)
        if headers:
            h.update(headers)
        s = self._session()
        if s is not None:
            try:
                r = s.get(url, headers=h, timeout=18, verify=False)
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            except Exception as e:
                print(f"[91动漫] fetch error(req): {url[:80]} -> {e}")
        if _urlreq is None:
            return ""
        try:
            req = _urlreq.Request(url, headers=h)
            with _urlreq.urlopen(req, timeout=18, context=_CTX) as resp:
                raw = resp.read()
            return raw.decode("utf-8", "ignore")
        except Exception as e:
            print(f"[91动漫] fetch error(url): {url[:80]} -> {e}")
            return ""

    def _fetch_bytes(self, url):
        """取原始字节。requests 优先，urllib 降级。"""
        s = self._session()
        if s is not None:
            try:
                r = s.get(url, headers=self.headers, timeout=20, verify=False)
                return r.content or b""
            except Exception as e:
                print(f"[91动漫] _fetch_bytes(req) {url[:60]} -> {e}")
        if _urlreq is None:
            return b""
        try:
            req = _urlreq.Request(url, headers=self.headers)
            with _urlreq.urlopen(req, timeout=20, context=_CTX) as resp:
                return resp.read()
        except Exception as e:
            print(f"[91动漫] _fetch_bytes(url) {url[:60]} -> {e}")
            return b""

    def _fetch_cover(self, url):
        """取封面并解密，带内存缓存。返回图片 bytes（失败返回 b""）。"""
        if not url:
            return b""
        hit = _cache_get(url)
        if hit is not None:
            return hit
        raw = self._fetch_bytes(url)
        if not raw:
            return b""
        plain = _aes_decrypt(raw)
        if not _sniff_mime(plain):
            # 解密失败：原样回吐，保证不 502 断链（壳仍不显示，但不断源）
            plain = raw
        _cache_put(url, plain)
        return plain

    # ---------- 封面 URL 包装 ----------

    def _prefetch_covers(self, urls):
        """并发预取封面进缓存。仅模式 2（data URI）需要——串行拉图会拖到 20s+。"""
        todo = []
        for u in urls:
            if _cache_get(u) is None:
                todo.append(u)
        if not todo:
            return
        try:
            from concurrent.futures import ThreadPoolExecutor
        except Exception:
            for u in todo:
                self._fetch_cover(u)
            return

        def _work(u):
            try:
                self._fetch_cover(u)
            except Exception:
                pass

        try:
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(_work, todo))
        except Exception:
            for u in todo:
                try:
                    self._fetch_cover(u)
                except Exception:
                    pass

    def _proxy_url(self, url):
        """把真封面 URL 按当前模式包装成 vod_pic。

        ★ 模式 0 的关键：必须 http://127.0.0.1:<port>/proxy?do=py&url=<全编码>
          - do=py 让壳找到 py 源的 localProxy；写成 do=jpg 壳会当普通 URL 直连 → 色块
        """
        if not url:
            return ""
        url = url.replace("&amp;", "&").strip()
        if _PIC_MODE == 3:            # 直链（排障）
            return url
        if _PIC_MODE == 2:            # data URI
            data = self._fetch_cover(url)
            if not data:
                return ""
            mime = _sniff_mime(data) or "image/jpeg"
            return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))
        if _PIC_MODE == 1:            # 源内自起服务
            port = _ensure_self_server(self._fetch_cover)
            if not port:
                return url
            return "http://127.0.0.1:%d/img?u=%s" % (port, quote(url, safe=""))
        # 模式 0：壳代理（默认）
        # ★ 拼串时用 _shell_proxy_prefix()，绝不让 "%d" 残留进最终 URL
        return _shell_proxy_prefix() + quote(url, safe="")

    # ---------- localProxy：封面解密中转 ----------

    def _parse_proxy_param(self, param):
        """兼容三种入参：dict / query string / 完整 URL。"""
        url = ""
        if isinstance(param, dict):
            url = param.get("url") or param.get("u") or param.get("path") or ""
        else:
            s = str(param or "")
            if s.startswith("http"):
                s = urlparse(s).query or s
            if "=" in s:
                qs = parse_qs(s)
                url = (qs.get("url") or qs.get("u") or qs.get("path") or [""])[0]
            elif s:
                url = s
        # parse_qs 已解一层；若还残留 %3A%2F%2F 再解一层
        if isinstance(url, str) and ("%3A" in url.upper() or "%2F" in url.upper()):
            url = unquote(url)
        return url.strip()

    def localProxy(self, param):
        """壳请求 /proxy?do=py&url=<urlenc> 时，取回加密图 → 解密 → 回吐真图。

        ★ 必须返回 4 格：[状态码, content-type, bytes, 标头 dict]
        """
        headers = {"Access-Control-Allow-Origin": "*"}
        try:
            url = self._parse_proxy_param(param)
            if not url:
                return [400, "text/plain", b"bad param", headers]
            if not url.startswith("http"):
                url = urljoin(self.host, url)

            data = self._fetch_cover(url)
            if not data:
                return [502, "text/plain", b"upstream fail", headers]

            mime = _sniff_mime(data)
            if not mime:
                # 解不开也原样回吐，避免 502 断链（壳里表现为不显示，不报错）
                mime = "application/octet-stream"
            return [200, mime, data, headers]
        except Exception as e:
            print(f"[91动漫] localProxy error: {e}")
            return [500, "text/plain", b"err", headers]

    # 别名：部分壳按这些名字找
    def proxyLocal(self, param):
        return self.localProxy(param)

    # ---------- 取封面 URL ----------

    def _pick_pic(self, unit_html):
        """从单元 HTML 取真封面。src 是占位图，必须用 data-src。"""
        for attr in ("data-src", "data-original", "data-lazy-src"):
            m = re.search(r'\b%s="([^"]+)"' % attr, unit_html)
            if not m:
                continue
            pic = (m.group(1) or "").strip()
            low = pic.lower()
            if not pic or "placeholder" in low or "/static/" in low or "logo" in low:
                continue
            return pic
        return ""

    def _parse_units(self, html):
        """按单元（article/li）解析出条目，href+封面+标题在同一单元内配对。

        ★ 不能用全页分散正则：那会把导航等杂链接算进序号，导致封面整体错位。
        """
        units = []
        for rx in _UNIT_RES:
            units = rx.findall(html)
            if units:
                break

        # 先扫出所有真封面 URL，模式 2（data URI）需要并发预取，否则串行极慢
        if _PIC_MODE == 2:
            raw_pics = []
            for unit in units:
                raw_pics.append(self._pick_pic(unit))
            self._prefetch_covers([p for p in raw_pics if p])

        items = []
        seen = set()
        for unit in units:
            # 详情链接：优先语义锚点，退回单元内第一个 href
            href = ""
            m = _LINK_HINT_RE.search(unit)
            if m:
                href = m.group(1)
            else:
                for h in _ANY_HREF_RE.findall(unit):
                    if _DETAIL_RE.search(h) or _COMIC_RE.search(h):
                        href = h
                        break
            if not href:
                continue

            vm = _DETAIL_RE.search(href)
            if vm:
                kind, cat, vid = vm.group(1), vm.group(2), vm.group(3)
                dedup_key = vid
            else:
                cm = _COMIC_RE.search(href)
                if not cm:
                    continue
                kind, cat, vid = "comic", "comic", cm.group(1)
                dedup_key = "c" + vid
            if dedup_key in seen:    # 排行页 desktop/mobile 双份 DOM 去重
                continue
            seen.add(dedup_key)

            full = href if href.startswith("http") else urljoin(self.host, href)

            name = ""
            for trx in _TITLE_RES:
                tm = trx.search(unit)
                if tm:
                    t = _clean_text(tm.group(1))
                    if len(t) > 1 and not re.match(r"^\d+$", t):
                        name = t
                        break
            # 标题兜底：alt 属性
            if not name:
                am = re.search(r'\balt="([^"]{4,120})"', unit)
                if am:
                    name = _clean_text(am.group(1))
            # 再兜底：detail id
            if not name:
                name = "%s %s" % (cat, vid)

            items.append({
                "vod_id": full if full.endswith("/") else full + "/",
                "vod_name": name[:120],
                "vod_pic": self._proxy_url(self._pick_pic(unit)),
                "vod_remarks": vid,
            })
        return items

    # ---------- 列表 ----------

    def _build_list(self, html, base_url, limit=0):
        items = self._parse_units(html)
        if limit:
            items = items[:limit]
        return items

    # ---------- 五接口 ----------

    def homeContent(self, filter_=None):
        return {
            "class": [
                {"type_id": "anime/lifan", "type_name": "里番动漫"},
                {"type_id": "anime/paomian", "type_name": "泡面番"},
                {"type_id": "anime/3d", "type_name": "3D动漫"},
                {"type_id": "anime/ai", "type_name": "AI漫剧"},
                {"type_id": "manga/tongrenzhi", "type_name": "同人志"},
                {"type_id": "manga/books", "type_name": "单行本"},
                {"type_id": "manga/hanman", "type_name": "韩漫"},
                {"type_id": "ranking", "type_name": "热门排行"},
            ],
            "filters": {},
        }

    def homeVideoContent(self):
        return self.categoryContent("anime/lifan", "1", None, {})

    def categoryContent(self, tid, pg="1", filter_=None, extend=None):
        page = str(pg) if str(pg) not in ("1", "0", "") else "1"
        result = {"list": [], "page": int(page), "pagecount": 9999, "limit": 24, "total": 999999}
        try:
            tid = (tid or "anime/lifan").strip("/")
            url = "%s/%s/" % (self.host, tid) if page == "1" \
                else "%s/%s/page/%s/" % (self.host, tid, page)

            html = self.fetch(url)
            if not html:
                result["pagecount"] = int(page)
                return result

            result["list"] = self._build_list(html, url)

            pages = re.findall(r'/page/(\d+)/', html)
            if pages:
                result["pagecount"] = max(int(p) for p in pages)
            elif len(result["list"]) >= 12:
                result["pagecount"] = int(page) + 1
            else:
                result["pagecount"] = int(page)
            result["total"] = len(result["list"])
        except Exception as e:
            print(f"[91动漫] categoryContent error: {e}")
        return result

    def detailContent(self, ids):
        result = {"list": []}
        if not ids:
            return result
        try:
            if isinstance(ids, (list, tuple)):
                url = str(ids[0]) if ids else ""
            else:
                url = str(ids or "")
            if not url.startswith("http"):
                url = urljoin(self.host, url)
            if not url.endswith("/"):
                url += "/"

            html = self.fetch(url)
            if not html:
                return result

            title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
            vod_name = title_m.group(1).strip() if title_m else ""
            vod_name = re.sub(r"\s*[-|].*?(91动漫|高清|在线观看).*$", "", vod_name, flags=re.I).strip()

            vod_pic = ""
            dm = re.search(r'\bdata-src="(https?://[^"]+)"', html, re.I)
            if dm:
                cand = dm.group(1)
                if "placeholder" not in cand.lower() and "/static/" not in cand.lower():
                    vod_pic = self._proxy_url(cand)

            play_from, play_url = [], []

            # ① 漫画章节目录：/reader/<id>/（dm-comic-chapter 单元）
            chapters = re.findall(
                r'<a[^>]*class="[^"]*dm-comic-chapter[^"]*"[^>]*href="([^"]+)"'
                r'[\s\S]{0,600}?</a>', html, re.I)
            if chapters:
                eps = []
                for i, h in enumerate(chapters):
                    full_c = h if h.startswith("http") else urljoin(self.host, h)
                    # 章节名：取该单元内 dm-episode-name 文本，失败用序号
                    nm = re.search(
                        r'href="%s"[\s\S]{0,600}?dm-episode-name[^>]*>([\s\S]{0,80}?)</' %
                        re.escape(h), html, re.I)
                    label = _clean_text(nm.group(1)) if nm else ""
                    if not label:
                        label = "第%d话" % (i + 1)
                    eps.append("%s$%s" % (label, full_c))
                play_from.append("漫画章节")
                play_url.append("#".join(eps))

            # ② 视频线路：页面里的 m3u8 / mp4
            m3u8s = [u.replace("&amp;", "&") for u in
                     re.findall(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*)', html, re.I)]
            seen_u = set()
            for i, u in enumerate(m3u8s):
                if u in seen_u:
                    continue
                seen_u.add(u)
                play_from.append("线路%d" % (i + 1) if i else "HLS")
                play_url.append("正片$" + u)
                if i >= 3:
                    break

            mp4s = re.findall(r'(https?://[^"\'\s]+\.mp4[^"\'\s]*)', html, re.I)
            if mp4s:
                play_from.insert(0, "MP4")
                play_url.insert(0, "正片$" + mp4s[0])

            if not play_from:
                play_from = ["页面嗅探"]
                play_url = ["播放$" + url]
            else:
                play_from.append("页面嗅探")
                play_url.append("播放$" + url)

            result["list"].append({
                "vod_id": url,
                "vod_name": vod_name or "动漫",
                "vod_pic": vod_pic,
                "type_name": "里番",
                "vod_year": "",
                "vod_area": "Japan",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": "",
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            })
        except Exception as e:
            print(f"[91动漫] detailContent error: {e}")
        return result

    def playerContent(self, flag, id, vipFlags=None):
        if isinstance(id, (list, tuple)):
            vid = str(id[0]) if id else ""
        else:
            vid = str(id or "")
        result = {
            "parse": 0 if (".m3u8" in vid or ".mp4" in vid) else 1,
            "jx": 0,
            "playUrl": "",
            "url": vid,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/",
            },
        }
        if ".m3u8" in vid:
            result["format"] = "application/x-mpegURL"
        return result

    def searchContent(self, key, quick=False, pg="1"):
        page = str(pg) if str(pg) not in ("1", "0", "") else "1"
        result = {"list": [], "page": int(page), "pagecount": 30, "limit": 24, "total": 0}
        try:
            q = quote(key)
            url = "%s/search-result/%s/" % (self.host, q) if page == "1" \
                else "%s/search-result/%s/page/%s/" % (self.host, q, page)

            html = self.fetch(url)
            if not html:
                return result

            result["list"] = self._build_list(html, url)
            result["total"] = len(result["list"])
            result["pagecount"] = int(page) if len(result["list"]) < 12 else int(page) + 1
        except Exception as e:
            print(f"[91动漫] searchContent error: {e}")
        return result
