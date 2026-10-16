#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人人视频(短剧/影视) TVBox Python 爬虫
站点: https://mh.yichengwlkj.com  (API: https://api.rrmj.plus)
格式: drpy2-python / hipy Spider (type 3, api: py_mh)

TVBox/影视仓/OK影视 配置示例(文件放 spider 目录, 名为 py_mh.py):
  {"key":"py_mh","name":"人人视频(py)","type":3,"api":"py_mh",
   "searchable":1,"quickSearch":1,"filterable":1}
hipy-server 环境 ext 填本文件的网络地址即可。

功能: 首页推荐 / 排行榜分类(分页) / 剧集详情+选集 / 搜索(含翻页) / 播放
逆向要点:
  1. 请求签名 x-ca-sign = base64(HMAC-SHA256("GET\naliId:..\nct:..\ncv:..\nt:..\npath?sortedQuery", SECRET))
  2. 接口响应 AES-128-ECB 解密 (key=3b744389882a4067, base64密文)
  3. 播放地址 AES-128-CBC 解密 (key=data.newSign[4:20], iv=b1da7878016e4e2b)
  4. 播放 URL 与签发会话绑定, 播放器需带相同 User-Agent (playerContent 已返回 header)
  5. CDN 节点每次随机分配: ws-302 源站防盗链长期 403, qn-302-m-play https 超时但 http 可播;
     playerContent 内置验证式重试(过滤ws-302 + Range实测 + https失败记忆, 最多10次),
     只返回实测可下载的播放地址(实测全片源通过率 >99%)
  6. 封面图 img.bwcgee.cn 强制 Referer 防盗链(仅认官网域名),
     封面经 proxy://do=py&url=.. 走 localProxy 本地带 Referer 取图;
     引擎不支持 localProxy 时封面退化为占位图, 不影响使用
依赖: python3 标准库即可; 有 pycryptodome 时自动加速, 无则用内置纯 python AES
"""

import base64
import hashlib
import hmac
import json
import re
import time
import urllib.parse
import urllib.request
import uuid

try:
    import sys
    sys.path.append('..')
    from base.spider import Spider
except Exception:
    class Spider(object):
        pass

# ---------------- AES 兜底实现(pure python, 无第三方依赖时使用) ----------------
_AES_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1)


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r & 0xff


def _key_expand(key16):
    w = [list(key16[i * 4:(i + 1) * 4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= _AES_RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    return w


def _add_round_key(state, kw):
    for c in range(4):
        for r in range(4):
            state[4 * c + r] ^= kw[c][r]


def _inv_shift_rows(state):
    old = state[:]
    for r in range(1, 4):
        for c in range(4):
            state[4 * c + r] = old[4 * ((c - r) % 4) + r]


def _inv_sub_bytes(state):
    for i in range(16):
        state[i] = _AES_INV_SBOX[state[i]]


def _inv_mix_columns(state):
    for c in range(4):
        a = state[4 * c:4 * c + 4]
        state[4 * c + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
        state[4 * c + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
        state[4 * c + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
        state[4 * c + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)


def _aes128_decrypt_block(block, w):
    state = list(block)
    _add_round_key(state, w[40:44])
    for rnd in range(9, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, w[rnd * 4:rnd * 4 + 4])
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, w[0:4])
    return bytes(state)


def aes_ecb_decrypt(key, data):
    """AES-128-ECB 解密, key 16字节, data 长度为16倍数"""
    w = _key_expand(key)
    out = b''
    for i in range(0, len(data), 16):
        out += _aes128_decrypt_block(data[i:i + 16], w)
    return out


def aes_cbc_decrypt(key, iv, data):
    """AES-128-CBC 解密"""
    w = _key_expand(key)
    out = b''
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        dec = _aes128_decrypt_block(blk, w)
        out += bytes(a ^ b for a, b in zip(dec, prev))
        prev = blk
    return out


def _pkcs7_unpad(data):
    if not data:
        return data
    n = data[-1]
    if 1 <= n <= 16 and data[-n:] == bytes([n]) * n:
        return data[:-n]
    return data


class _AESCipher:
    """优先用 pycryptodome, 退化到纯 python"""

    def __init__(self, key16):
        self.key = key16
        self._lib = None
        try:
            from Crypto.Cipher import AES as _AES
            self._lib = _AES
        except Exception:
            try:
                from Cryptodome.Cipher import AES as _AES
                self._lib = _AES
            except Exception:
                self._lib = None

    def ecb_decrypt_b64(self, b64text):
        raw = base64.b64decode(b64text)
        if self._lib is not None:
            c = self._lib.new(self.key, self._lib.MODE_ECB)
            dec = c.decrypt(raw)
        else:
            dec = aes_ecb_decrypt(self.key, raw)
        return _pkcs7_unpad(dec).decode('utf-8', 'ignore')

    def cbc_decrypt_b64(self, b64text, key, iv):
        raw = base64.b64decode(b64text)
        if self._lib is not None:
            c = self._lib.new(key, self._lib.MODE_CBC, iv)
            dec = c.decrypt(raw)
        else:
            dec = aes_cbc_decrypt(key, iv, raw)
        return _pkcs7_unpad(dec).decode('utf-8', 'ignore')


# ---------------- Spider 主体 ----------------

class Spider(Spider):
    HOST = 'https://api.rrmj.plus'
    ORIGIN = 'https://mh.yichengwlkj.com'
    SIGN_SECRET = 'ES513W0B1CsdUrR13Qk5EgDAKPeeKZY'
    DATA_KEY = b'3b744389882a4067'
    URL_IV = b'b1da7878016e4e2b'
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
    PAGE_SIZE = 20
    CACHE_TTL = 1800

    def init(self, extend=""):
        self.device_id = str(uuid.uuid4()).upper()
        self.cipher = _AESCipher(self.DATA_KEY)
        self._cache = {}
        self._top_cache = None
        self._top_cache_ts = 0
        self._https_fail_hosts = set()

    def getName(self):
        return "人人视频"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|ts)', url, re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        """本地代理: 封面图防盗链绕过(源站必须带官网 Referer 才能取图)"""
        try:
            url = (param or {}).get('url') or ''
            if url and not url.startswith(('http://', 'https://')):
                url = urllib.parse.unquote(url)
            if url.startswith('http'):
                req = urllib.request.Request(url, headers={
                    'User-Agent': self.UA, 'Referer': self.ORIGIN + '/'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                    ctype = (r.headers.get('Content-Type') or 'image/jpeg').split(';')[0]
                if data:
                    return [200, ctype, data, {}]
        except Exception:
            pass
        # 失败时返1x1透明png, 避免引擎报错
        px = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
            'AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
        return [200, 'image/png', px, {}]

    def _pic(self, url):
        """封面地址包一层 proxy://, 由 localProxy 带 Referer 取图;
        引擎不支持时退化为占位图(与无图一致, 无副作用)"""
        url = (url or '').strip()
        if not url:
            return ''
        return 'proxy://do=py&url=' + urllib.parse.quote(url, safe='')

    # ---------- 基础请求 ----------

    def _sign(self, method, path_with_query, ts):
        text = (method.upper() + '\n'
                + 'aliId:' + self.device_id + '\n'
                + 'ct:web_pc\n'
                + 'cv:1.0.0\n'
                + 't:' + str(ts) + '\n'
                + path_with_query)
        mac = hmac.new(self.SIGN_SECRET.encode(), text.encode(), hashlib.sha256).digest()
        return base64.b64encode(mac).decode()

    def _headers(self, method, path_with_query):
        ts = int(time.time() * 1000)
        return {
            'User-Agent': self.UA,
            'Accept': 'application/json, text/plain, */*',
            'Referer': self.ORIGIN + '/',
            'token': '',
            'clientVersion': '1.0.0',
            'clientType': 'web_pc',
            'cv': '1.0.0',
            'ct': 'web_pc',
            'deviceId': self.device_id,
            'umid': self.device_id,
            'aliId': self.device_id,
            'uet': '9',
            't': str(ts),
            'x-ca-sign': self._sign(method, path_with_query, ts),
        }

    def _http_get(self, path, params):
        q = urllib.parse.urlencode(sorted(params.items()))
        p = path + ('?' + q if q else '')
        req = urllib.request.Request(self.HOST + p, headers=self._headers('GET', p))
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', 'ignore')

    def _api(self, path, params=None):
        """带签名的 API GET, 自动识别并解密响应, 返回 dict 或 None"""
        try:
            body = self._http_get(path, params or {})
        except Exception:
            return None
        try:
            j = json.loads(body)
            if isinstance(j, dict) and ('code' in j or 'msg' in j):
                return j
        except Exception:
            pass
        try:
            return json.loads(self.cipher.ecb_decrypt_b64(body))
        except Exception:
            return None

    def _decrypt_play_url(self, enc_url, new_sign):
        """播放地址二层解密: AES-128-CBC(key=newSign[4:20], iv=固定)"""
        key = new_sign[4:20].encode()
        return self.cipher.cbc_decrypt_b64(enc_url, key, self.URL_IV)

    # ---------- 数据转换 ----------

    def _vod_from_item(self, it):
        did = str(it.get('dramaId') or it.get('id') or '')
        return {
            'vod_id': did,
            'vod_name': (it.get('title') or it.get('name') or '').strip(),
            'vod_pic': self._pic(it.get('cover') or it.get('coverUrl') or it.get('cover3Url') or ''),
            'vod_remarks': it.get('playStatus') or it.get('cornerMark') or '',
            'vod_year': str(it.get('year') or ''),
            'vod_area': it.get('area') or '',
            'vod_score': str(it.get('score') or ''),
            'vod_content': (it.get('description') or it.get('shortDesc') or it.get('brief') or '').strip(),
        }

    def _cache_get(self, key):
        v = self._cache.get(key)
        if v and time.time() - v[1] < self.CACHE_TTL:
            return v[0]
        return None

    def _cache_set(self, key, val):
        self._cache[key] = (val, time.time())

    def _top_containers(self):
        """排行榜配置(9大榜×子榜), 缓存"""
        now = time.time()
        if self._top_cache and now - self._top_cache_ts < self.CACHE_TTL:
            return self._top_cache
        j = self._api('/m-station/top/home')
        out = []
        data = (j or {}).get('data') or {}
        for container in data.get('containerList') or []:
            cname = container.get('name') or ''
            for tl in (container.get('topList') or [])[:4]:
                out.append({
                    'id': tl.get('id'),
                    'tid': 'top_' + str(tl.get('id')),
                    'name': (cname + '·' + tl.get('name', '')).strip('·'),
                })
        self._top_cache = out
        self._top_cache_ts = now
        return out

    # ---------- TVBox 标准接口 ----------

    def homeContent(self, filter):
        classes = []
        try:
            for c in self._top_containers():
                classes.append({'type_id': c['tid'], 'type_name': c['name']})
        except Exception:
            pass
        result = {'class': classes}
        try:
            hv = self.homeVideoContent()
            if hv.get('list'):
                result['list'] = hv['list']
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        """首页推荐: 板块剧集"""
        try:
            j = self._api('/m-station/app/page',
                          {'position': 'CHANNEL_INDEX', 'pageNum': '1', 'personalRecommend': '0'})
            data = (j or {}).get('data') or {}
            vods, seen = [], set()
            for sec in (data.get('sections') or []):
                for sc in (sec.get('sectionContents') or []):
                    for it in (sc.get('series') or []):
                        did = str(it.get('dramaId') or '')
                        if not did or did in seen:
                            continue
                        seen.add(did)
                        vods.append({
                            'vod_id': did,
                            'vod_name': (it.get('title') or '').strip(),
                            'vod_pic': self._pic(it.get('coverUrl') or it.get('cover3Url') or ''),
                            'vod_remarks': (it.get('subTitle') or it.get('score') or '')[:12],
                        })
            return {'list': vods[:30]}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        result = {'list': [], 'page': pg, 'pagecount': 1, 'limit': self.PAGE_SIZE, 'total': 0}
        if not tid.startswith('top_'):
            return result
        top_id = tid[4:]
        try:
            j = self._api('/m-station/top/drama/list',
                          {'topId': top_id, 'pageNum': pg, 'pageSize': self.PAGE_SIZE})
            data = (j or {}).get('data') or {}
            content = data.get('content') or []
            vods = [self._vod_from_item(it) for it in content]
            total = int(data.get('total') or 0)
            is_end = bool(data.get('isEnd'))
            pagecount = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE) if total else (pg if is_end else pg + 1)
            result.update({'list': vods, 'total': total, 'pagecount': pagecount})
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        did = str(ids[0]).split('_')[-1]
        vod = {'vod_id': did, 'vod_play_from': '人人视频', 'vod_play_url': ''}
        try:
            j = self._api('/m-station/drama/page',
                          {'hsdrOpen': '0', 'isAgeLimit': '0', 'dramaId': did,
                           'quality': 'SD', 'hevcOpen': '0'})
            data = (j or {}).get('data') or {}
            info = data.get('dramaInfo') or {}
            vod.update({
                'vod_name': (info.get('title') or '').strip(),
                'vod_pic': self._pic(info.get('cover') or info.get('cover3Url') or ''),
                'vod_year': str(info.get('year') or ''),
                'vod_area': info.get('area') or '',
                'vod_remarks': info.get('playStatus') or '',
                'vod_score': str(info.get('score') or ''),
                'vod_type': info.get('plotType') or '',
                'vod_tag': info.get('dramaType') or '',
                'vod_director': info.get('author') or '',
                'vod_actor': ' '.join(
                    (a.get('name') or '') for a in (info.get('actorList') or [])[:8]),
                'vod_content': (info.get('intro') or info.get('subTitle') or '').strip(),
            })
            eps = data.get('episodeList') or []
            parts = []
            for ep in eps:
                sid = str(ep.get('sid') or ep.get('id') or '')
                name = (ep.get('text') or ep.get('title') or '').strip()
                if not name:
                    name = '第' + str(ep.get('episodeNo') or (len(parts) + 1)) + '集'
                if ep.get('feeMode') and ep.get('feeMode') != 'free':
                    name += '·VIP'
                parts.append(name + '$' + did + '_' + sid)
            vod['vod_play_url'] = '#'.join(parts)
        except Exception:
            pass
        # 详情文字兜底: intro 接口
        if not vod.get('vod_content'):
            try:
                j2 = self._api('/m-station/drama/intro', {'dramaId': did})
                intro = ((j2 or {}).get('data') or {}).get('intro') or ''
                if intro:
                    vod['vod_content'] = intro.strip()
            except Exception:
                pass
        return {'list': [vod]}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, 1)

    def searchContentPage(self, key, quick, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        size = min(pg * self.PAGE_SIZE, 100)
        result = {'list': []}
        try:
            j = self._api('/m-station/search/drama',
                          {'keywords': key, 'size': size, 'order': 'match',
                           'search_after': '', 'isExecuteVipActivity': 'false'})
            data = (j or {}).get('data') or {}
            rows = data.get('searchDramaList') or []
            start = (pg - 1) * self.PAGE_SIZE
            page_rows = rows[start:start + self.PAGE_SIZE]
            vods = []
            for it in page_rows:
                v = self._vod_from_item(it)
                if v['vod_name']:
                    vods.append(v)
            result['list'] = vods
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = str(id).split('_')
            did, sid = parts[0], parts[-1]
        except Exception:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': {}}
        result = {'parse': 0, 'playUrl': '', 'url': '',
                  'header': {'User-Agent': self.UA, 'Referer': self.ORIGIN + '/'}}
        # 节点每次随机分配: ws-302 防盗链签名长期 403(源站问题), 其余节点可播;
        # 策略=过滤ws-302 + Range实探测验证 + https失败记忆, 最多10次
        fallback = ''
        for _ in range(10):
            try:
                j = self._api('/m-station/drama/play',
                              {'dramaId': did, 'episodeSid': sid, 'quality': 'SD',
                               'hevcOpen': '0', 'tria4k': '0', 'hsdrOpen': '0'})
                data = (j or {}).get('data') or {}
                m3u8 = data.get('m3u8') or {}
                enc = m3u8.get('url')
                sign = data.get('newSign') or ''
                if not enc or len(sign) < 20:
                    time.sleep(0.5)
                    continue
                url = self._decrypt_play_url(enc, sign)
                if not url:
                    continue
                host = url.split('/')[2] if '://' in url else ''
                if not fallback and host:
                    fallback = url
                if host.startswith('ws-302'):
                    time.sleep(0.5)
                    continue
                # qn-302-m-play 等节点 https 超时但 http 可播;
                # _probe_url 返回实测可用的地址(必要时自动 https->http 降级)
                tail = url.split('://', 1)[-1]
                cands = ['http://' + tail, url] if host in self._https_fail_hosts \
                    else [url, 'http://' + tail]
                for cand in dict.fromkeys(cands):
                    good = self._probe_url(cand)
                    if good:
                        result['url'] = good
                        return result
                time.sleep(0.4)
            except Exception:
                time.sleep(0.4)
        # 兜底: 重试耗尽, 返回最后一次拿到的地址(可能不可播, 但优于空)
        if not result['url']:
            result['url'] = fallback
        return result

    def _probe_url(self, url):
        """Range 探测播放地址是否真实可下载;
        成功返回实测可用的地址(https 超时自动降级 http 并记忆 host), 失败返回 None"""
        if self._probe_direct(url):
            return url
        if url.startswith('https://'):
            alt = 'http://' + url.split('://', 1)[1]
            if self._probe_direct(alt):
                self._https_fail_hosts.add(url.split('/')[2])
                return alt
        return None

    def _probe_direct(self, url):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': self.UA, 'Referer': self.ORIGIN + '/',
                'Range': 'bytes=0-65535'})
            with urllib.request.urlopen(req, timeout=6) as r:
                return r.status in (200, 206) and len(r.read(65536)) > 8192
        except Exception:
            return False
