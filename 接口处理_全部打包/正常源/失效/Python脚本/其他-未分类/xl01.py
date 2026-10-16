# -*- coding: utf-8 -*-
# 雪落影视 (v.xl01.cc.ua) TVBox dr_py 爬虫源
# ---------------------------------------------------------------------------
# 站点:  https://v.xl01.cc.ua  ("雪落影视" - 电影/剧集在线平台, 服务端渲染)
#
# 页面:  首页 /            分类 /s/{cat} 翻页 /s/{cat}/{pg} (all 类型 ?type=0|1)
#        详情 /{cat}/{id}.htm   播放 /play/{id}-{n}.htm   搜索 /search/{kw}
#        搜索有"30分钟内首次需验证码"限制 → 验证码为算术题(a+b / a-b / a*x),
#        内置纯 Python JPEG 解码 + 模板匹配识别器, 自动算出结果重试。
#
# 取流:  播放页内 var pid → GET /lines?t&sg&pid (sg=AES-128-ECB(md5(pid-t)前16位
#        作 key, 加密 "pid-t") 的 base64→HEX) → {url3[], tos, m3u8, m3u8_2}
#          url3   直连 mp4 (部分需 ?rkey 处理)
#          tos    POST /god/{pid}?type=1 (t/sg/verifyCode=888) → 302式JSON直链
#          m3u8*  bde4.cc 域名混淆 m3u8 → 同域 PNG 壳 + gzip 混淆,
#                 去头 3354 字节 zlib inflate 得真实播放列表;
#                 分片 https://vod.xl01.me[/hls/]/{name}.ts 同样是
#                 "120字节PNG壳 + 裸TS" → localProxy 剥壳透传
#
# 封面:  wework.qpic.cn 实测无防盗链, 直连
# ---------------------------------------------------------------------------
import sys
sys.path.append('..')
from base.spider import Spider

import re
import json
import time
import zlib
import struct
import base64
import hashlib
import http.cookiejar
import urllib.parse
import urllib.request
import urllib.error

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

HOST = 'https://v.xl01.cc.ua'
SITE_REF = 'https://v.xl01.cc.ua/'

CATS = [
    ('all0', '电影'),
    ('all1', '剧集'),
    ('donghua', '动画'),
    ('meiju', '美剧'),
    ('hanju', '韩剧'),
    ('riju', '日剧'),
    ('gangtaiju', '港台剧'),
    ('yingju', '英剧'),
    ('duanju', '短剧'),
    ('zongyi', '综艺'),
    ('dongzuo', '动作'),
    ('aiqing', '爱情'),
    ('xiju', '喜剧'),
    ('kehuan', '科幻'),
    ('kongbu', '恐怖'),
    ('zhanzheng', '战争'),
    ('wuxia', '武侠'),
    ('mohuan', '魔幻'),
    ('juqing', '剧情'),
    ('xuanyi', '悬疑'),
    ('fanzui', '犯罪'),
    ('jilu', '纪录'),
    ('guoyu', '国语'),
    ('yuanchuang', '原创压制'),
    ('3D', '3D'),
]

AREAS = ['中国大陆', '中国香港', '中国台湾', '美国', '韩国', '日本', '英国',
         '法国', '德国', '加拿大', '澳大利亚', '意大利', '西班牙', '印度',
         '泰国', '俄罗斯']

# ---------------------------------------------------------------------------
# b64 / AES-128-ECB (纯 Python, 仅加密) —— /lines 与 /god 的 sg 签名
# ---------------------------------------------------------------------------

def _b64e(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    return base64.urlsafe_b64encode(s).decode('ascii').replace('=', '')


def _b64d(s):
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b,
    0xfe, 0xd7, 0xab, 0x76, 0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0,
    0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0, 0xb7, 0xfd, 0x93, 0x26,
    0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2,
    0xeb, 0x27, 0xb2, 0x75, 0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0,
    0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84, 0x53, 0xd1, 0x00, 0xed,
    0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f,
    0x50, 0x3c, 0x9f, 0xa8, 0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5,
    0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2, 0xcd, 0x0c, 0x13, 0xec,
    0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14,
    0xde, 0x5e, 0x0b, 0xdb, 0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c,
    0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79, 0xe7, 0xc8, 0x37, 0x6d,
    0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f,
    0x4b, 0xbd, 0x8b, 0x8a, 0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e,
    0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e, 0xe1, 0xf8, 0x98, 0x11,
    0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f,
    0xb0, 0x54, 0xbb, 0x16]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a = (a ^ 0x1b) & 0xff
    return a


def _aes128_ecb_encrypt(key, data):
    """key: 16 bytes; data: bytes, 自动 Pkcs7 填充; 返回密文"""

    def _xt(a):
        a <<= 1
        if a & 0x100:
            a = (a ^ 0x1b) & 0xff
        return a

    def key_expand(k):
        w = [list(k[i:i + 4]) for i in range(0, 16, 4)]
        for i in range(4, 44):
            t = list(w[i - 1])
            if i % 4 == 0:
                t = t[1:] + t[:1]
                t = [_SBOX[b] for b in t]
                t[0] ^= _RCON[i // 4 - 1]
            w.append([w[i - 4][j] ^ t[j] for j in range(4)])
        # 轮密钥 rnd = w[4rnd]||w[4rnd+1]||w[4rnd+2]||w[4rnd+3]
        return [w[4 * r] + w[4 * r + 1] + w[4 * r + 2] + w[4 * r + 3]
                for r in range(11)]

    rks = key_expand(key)

    def _mix_col(a0, a1, a2, a3):
        return [
            _xt(a0) ^ _xt(a1) ^ a1 ^ a2 ^ a3,
            a0 ^ _xt(a1) ^ _xt(a2) ^ a2 ^ a3,
            a0 ^ a1 ^ _xt(a2) ^ _xt(a3) ^ a3,
            _xt(a0) ^ a0 ^ a1 ^ a2 ^ _xt(a3),
        ]

    pad_len = 16 - (len(data) % 16)
    data = data + bytes([pad_len] * pad_len)
    out = bytearray()
    for blk_start in range(0, len(data), 16):
        s = [data[blk_start + i] ^ rks[0][i] for i in range(16)]
        for rnd in range(1, 11):
            s = [_SBOX[b] for b in s]
            s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3],
                 s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]
            if rnd != 10:
                t = []
                for c in range(0, 16, 4):
                    t.extend(_mix_col(s[c], s[c + 1], s[c + 2], s[c + 3]))
                s = t
            for i in range(16):
                s[i] ^= rks[rnd][i]
        out.extend(s)
    return bytes(out)


def _sign(pid, t):
    """/lines 与 /god 的 sg 参数: AES-128-ECB(md5(pid-t)前16位, "pid-t")→HEX大写"""
    plain = '%s-%s' % (pid, t)
    key = hashlib.md5(plain.encode('utf-8')).hexdigest()[:16].encode('ascii')
    return _aes128_ecb_encrypt(key, plain.encode('utf-8')).hex().upper()


# ---------------------------------------------------------------------------
# 算术验证码识别: 纯 Python baseline JPEG 解码(仅Y通道) + 分割 + 模板匹配
# ---------------------------------------------------------------------------

class _BitReader(object):
    def __init__(self, data, pos):
        self.d = data
        self.pos = pos
        self.bit = 0
        self.cur = 0

    def read_bit(self):
        if self.bit == 0:
            b = self.d[self.pos]
            if b == 0xFF:
                nb = self.d[self.pos + 1]
                if nb == 0x00:
                    self.pos += 2
                elif 0xD0 <= nb <= 0xD7:
                    self.pos += 2
                    b = self.d[self.pos]
                    if b == 0xFF and self.d[self.pos + 1] == 0x00:
                        self.pos += 2
                else:
                    self.pos += 2
            else:
                self.pos += 1
            self.cur = b
            self.bit = 8
        self.bit -= 1
        return (self.cur >> self.bit) & 1

    def read_bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.read_bit()
        return v


class _HuffTable(object):
    def __init__(self, counts, symbols):
        self.codes = {}
        code = 0
        k = 0
        for ln in range(1, 17):
            for _ in range(counts[ln - 1]):
                self.codes[(ln, code)] = symbols[k]
                code += 1
                k += 1
            code <<= 1

    def decode(self, br):
        ln = 0
        code = 0
        while ln < 16:
            code = (code << 1) | br.read_bit()
            ln += 1
            v = self.codes.get((ln, code))
            if v is not None:
                return v
        raise ValueError('huffman decode fail')


def _jpeg_extend(v, t):
    return v - (1 << t) + 1 if v < (1 << (t - 1)) else v


_ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]

import math as _math

_COS = [[_math.cos((2 * x + 1) * 3.141592653589793 * u / 16.0)
         for x in range(8)] for u in range(8)]


def _idct2d(block):
    cu = [0.7071067811865476] + [1.0] * 7
    tmp = [[0.0] * 8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            s = 0.0
            for u in range(8):
                if block[y * 8 + u]:
                    s += block[y * 8 + u] * _COS[u][x] * cu[u]
            tmp[y][x] = s
    out = [[0] * 8 for _ in range(8)]
    for x in range(8):
        for y in range(8):
            s = 0.0
            for v in range(8):
                if tmp[v][x]:
                    s += tmp[v][x] * _COS[v][y] * cu[v]
            out[y][x] = max(0, min(255, int(s / 4 + 128.5)))
    return out


def _jpeg_decode_gray(data):
    """JPEG bytes → (w, h, gray[[int]])"""
    if data[0:2] != b'\xff\xd8':
        raise ValueError('not jpeg')
    i = 2
    qtables = {}
    huffs = {}
    w = h = 0
    comps = []
    scan_data = None
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m == 0xD8:
            i += 2
        elif m == 0xD9:
            break
        elif m == 0xDA:
            ln = struct.unpack('>H', data[i + 2:i + 4])[0]
            ns = data[i + 4]
            p = i + 5
            scomps = []
            for _ in range(ns):
                cid = data[p]
                td_ta = data[p + 1]
                scomps.append((cid, td_ta >> 4, td_ta & 15))
                p += 2
            scan_data = (scomps, data[i + 2 + ln:])
            break
        else:
            ln = struct.unpack('>H', data[i + 2:i + 4])[0]
            seg = data[i + 4:i + 2 + ln]
            if m == 0xDB:
                p = 0
                while p < len(seg):
                    pq_tq = seg[p]
                    pq, tq = pq_tq >> 4, pq_tq & 15
                    p += 1
                    if pq == 0:
                        qtables[tq] = list(seg[p:p + 64])
                        p += 64
                    else:
                        p += 128
            elif m == 0xC4:
                p = 0
                while p < len(seg):
                    tc_th = seg[p]
                    p += 1
                    counts = list(seg[p:p + 16])
                    p += 16
                    total = sum(counts)
                    huffs[(tc_th >> 4, tc_th & 15)] = _HuffTable(
                        counts, list(seg[p:p + total]))
                    p += total
            elif m in (0xC0, 0xC1):
                h = struct.unpack('>H', seg[1:3])[0]
                w = struct.unpack('>H', seg[3:5])[0]
                nc = seg[5]
                comps = []
                for c in range(nc):
                    comps.append([seg[6 + c * 3], seg[7 + c * 3] >> 4,
                                  seg[7 + c * 3] & 15, seg[8 + c * 3]])
            i += 2 + ln
    if scan_data is None:
        raise ValueError('no SOS')
    scomps, sdata = scan_data
    cinfo = []
    for cid, td, ta in scomps:
        for comp in comps:
            if comp[0] == cid:
                cinfo.append((comp[1], comp[2], qtables[comp[3]],
                              huffs[(0, td)], huffs[(1, ta)]))
    br = _BitReader(sdata, 0)
    hmax = max(c[0] for c in cinfo)
    vmax = max(c[1] for c in cinfo)
    mcuw = (w + hmax * 8 - 1) // (hmax * 8)
    mcuh = (h + vmax * 8 - 1) // (vmax * 8)
    img = [[255] * w for _ in range(h)]
    pred = [0] * len(cinfo)
    for my in range(mcuh):
        for mx in range(mcuw):
            for ci, (ch, cv, qt, hdc, hac) in enumerate(cinfo):
                for by in range(cv):
                    for bx in range(ch):
                        blk = [0] * 64
                        t = hdc.decode(br)
                        diff = _jpeg_extend(br.read_bits(t), t) if t else 0
                        pred[ci] += diff
                        blk[0] = pred[ci] * qt[0]
                        k = 1
                        while k < 64:
                            rs = hac.decode(br)
                            r, s = rs >> 4, rs & 15
                            if s == 0:
                                if r == 15:
                                    k += 16
                                    continue
                                break
                            k += r
                            if k > 63:
                                break
                            blk[_ZIGZAG[k]] = _jpeg_extend(
                                br.read_bits(s), s) * qt[k]
                            k += 1
                        px = _idct2d(blk)
                        ox = mx * hmax * 8 + bx * 8
                        oy = my * vmax * 8 + by * 8
                        if ci == 0:
                            for yy in range(8):
                                gy = oy + yy
                                if gy >= h:
                                    break
                                row = img[gy]
                                for xx in range(8):
                                    gx = ox + xx
                                    if gx < w:
                                        row[gx] = px[yy][xx]
    return w, h, img


# --- 分割管线 ---

def _binarize(img, w, h, thr=64):
    return [[1 if img[y][x] < thr else 0 for x in range(w)] for y in range(h)]


def _denoise(b, w, h):
    out = [row[:] for row in b]
    for y in range(h):
        for x in range(w):
            if b[y][x]:
                n = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if 0 <= y + dy < h and 0 <= x + dx < w and b[y + dy][x + dx]:
                            n += 1
                if n < 3:
                    out[y][x] = 0
    return out


def _remove_lines(b, w, h, minlen=14):
    out = [row[:] for row in b]
    for y in range(h):
        x = 0
        while x < w:
            if out[y][x]:
                x0 = x
                while x < w and out[y][x]:
                    x += 1
                if x - x0 >= minlen:
                    for xx in range(x0, x):
                        out[y][xx] = 0
            else:
                x += 1
    return out


def _erode4(b, w, h):
    out = [[0] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if b[y][x] and b[y - 1][x] and b[y + 1][x] and b[y][x - 1] and b[y][x + 1]:
                out[y][x] = 1
    return out


def _ccl(b, w, h):
    from collections import deque
    seen = [[False] * w for _ in range(h)]
    comps = []
    for y0 in range(h):
        for x0 in range(w):
            if b[y0][x0] and not seen[y0][x0]:
                q = deque([(y0, x0)])
                seen[y0][x0] = True
                px = []
                while q:
                    y, x = q.popleft()
                    px.append((y, x))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < h and 0 <= nx < w and b[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                q.append((ny, nx))
                ys = [p[0] for p in px]
                xs = [p[1] for p in px]
                comps.append({'bbox': (min(xs), min(ys), max(xs), max(ys)),
                              'size': len(px)})
    return comps


def _split_cols(b, w, h, x0, x1, y0, y1, valley_thr=1):
    prof = [sum(1 for y in range(y0, y1 + 1) if b[y][x])
            for x in range(x0, x1 + 1)]
    segs = []
    s = None
    e = 0
    for i, v in enumerate(prof):
        if v > valley_thr:
            if s is None:
                s = i
            e = i
        else:
            if s is not None and i - e >= 1:
                segs.append((x0 + s, x0 + e))
                s = None
    if s is not None:
        segs.append((x0 + s, x0 + e))
    return segs


def _vc_process(data):
    w, h, img = _jpeg_decode_gray(data)
    b = _remove_lines(_denoise(_binarize(img, w, h), w, h), w, h)
    be = _erode4(b, w, h)
    comps = [c for c in _ccl(be, w, h) if c['size'] >= 3]
    comps.sort(key=lambda c: c['bbox'][0])
    groups = []
    for c in comps:
        x0, y0, x1, y1 = c['bbox']
        if groups and x0 <= groups[-1][2] + 5:
            g = groups[-1]
            groups[-1] = (min(g[0], x0), min(g[1], y0),
                          max(g[2], x1), max(g[3], y1))
        else:
            groups.append((x0, y0, x1, y1))
    return w, h, b, groups


# --- 块分类 / 归一化 / 模板距离 ---

def _vc_classify(c):
    x, y, w, h = c['x'], c['y'], c['w'], c['h']
    if h <= 4:
        return 'junk'
    if x >= 78 and 10 <= w <= 14 and 8 <= h <= 11:
        return 'eq'
    if x >= 95 and w <= 8 and h >= 12:
        return 'q'
    if w <= 4 and 9 <= h <= 12 and y >= 13:
        return 'op'
    if 13 <= y <= 18 and 8 <= w <= 14 and 7 <= h <= 12:
        return 'op'
    if h >= 12:
        return 'digit'
    return 'junk'


def _vc_normalize(c, blk):
    W, H = 16, 18
    tw = max(2, min(W, round(c['w'] * H / c['h'])))
    off = (W - tw) // 2
    out = [[0] * W for _ in range(H)]
    for i in range(H):
        sy = int(i * c['h'] / H)
        for j in range(tw):
            sx = int(j * c['w'] / tw)
            if blk[c['y'] + sy][c['x'] + sx]:
                out[i][off + j] = 1
    return out


def _vc_dist(a, b):
    return sum(1 for i in range(len(a)) for j in range(len(a[0]))
               if a[i][j] != b[i][j])


_VC_TMPL_HEX = {
    '0': ["0fc00fc03fe03e383c3c3c3c3c1c3c1c3c1c3c1c3c1c3c1c3c1c3e1c3f1c0e3c03fc01f8", "0ff00ff01e1c1e1e7c0e7c0e7c0e7c0e7c0e7c0e7c0e7c0e7c0e1e1e1e1e0ffe03fc0000", "07fc07fc1e3c1c3c7c1c781c781c781c781c781c781c781c781c781c783c7c387de07fe0"],
    '1': ["07c007c007c007c007c007c007c007c007c007c007c007c007c007c007c007c007c007c0"],
    '2': ["71f071f0607c001c001c001c001c001c007c007c007c07fc0ffc1ff81ff87ff07f807fe0", "01f801f81ff81e7818380038003800380078007801f001e003c007c01fb81ff81ff81fc0"],
    '3': ["07c007c007c001c001c001c001c007c0078007c007c007c001c001c001c001c007c007c0"],
    '4': ["01fc01fc01fc07fc0ffc0f3c3e3c3e3c383c303c3c3c3ffc07fc07fc003c003c003c003c", "01f801f803f803f803f807f81ef81ef81cf81cf818f804f803f803f81ff81cf800f800f8"],
    '5': ["1fc01fc01df81c381c001c001e001fc001e00078007800380038003800381e781ff801f0", "3c003c0038003800380038303bfc3ffc3ffc3c7c003c003c003c003c003c003c007803f0", "1ff818f01810180018001f001fc000e000f000700078007800781ff81ff000c000000000"],
    '6': ["1ff81ff87e387c0c78047bc07ff07ff07c38783c781c781c781c781c781c1c1c07fc07fc", "07f007f00ffc1e0e1c027dc07ff07ef87c1e7c0e7c0e7c0e7c1e1c0e1e0e0f1e03fe00fc", "03e403e40ede1fe01e1079fc7bfc7bfc7e3e7c1e781e781e781e781e781c78387df07fe0"],
    '7': ["1ff81ff8003800f800f800f801f801f003f003e003e007e007c01fc01fc01f001f001e00"],
    '8': ["3fc03fc03ff03e383c3c3c1c3c1c0e1c0ffc3ffc3ffc3e383c383c1c3c1c3e1c07fc03fc", "01fc01fc07fc0e3c3e1c3c1c3c1c3c383ff83ffc3ffc0e3c0e1c3c1c3c1c3c3c3ff03fe0", "7ff07ff07c3c781c781c781c7c3c7c3c1ffc1ff87c387fdc781c781c781c7c3c7ffc0ffc"],
    '9': ["1fc01fc07fe07c387838781c781c781c781c781c7c1c0ffc07fc07fc001c601c787c1ffc", "0ffe0ffe1e3e1e0e780e780e780e780e780e783e783e7ffe7fce6e0e6e0e003c007801f0", "01f801f80ffc1e3c1c1e781e781e781e781e783e783e7dfe7fdc6e1c003800f001e07fc0"],
}


VC_TMPL = {}  # 由下方 _vc_init_templates() 填充 (hex → 18x16 矩阵)


def _vc_init_templates():
    for ch, reps in _VC_TMPL_HEX.items():
        mats = []
        for hx in reps:
            bits = bin(int(hx, 16))[2:].zfill(16 * 18)
            mats.append([[int(bits[y * 16 + x]) for x in range(16)]
                         for y in range(18)])
        VC_TMPL[ch] = mats


_VC_REPS = None


def _vc_reps():
    global _VC_REPS
    if _VC_REPS is None:
        _vc_init_templates()
        _VC_REPS = [(ch, r) for ch in sorted(VC_TMPL)
                    for r in VC_TMPL[ch]]
    return _VC_REPS


def _vc_topk(c, b, k=3):
    n = _vc_normalize(c, b)
    ds = sorted((_vc_dist(n, r), ch) for ch, r in _vc_reps())
    return ds[:k]


def _vc_enum_num(cs, b):
    outs = [(0, 0)]
    for c in cs:
        cands = _vc_topk(c, b)
        outs = [(td + d, num * 10 + int(ch))
                for td, num in outs for d, ch in cands]
        outs.sort()
        outs = outs[:6]
    return outs


def _vc_solve_bytes(data):
    """验证码图片 bytes → (op, a, b) 或 None"""
    try:
        w, h, b, groups = _vc_process(data)
    except Exception:
        return None
    blocks = []
    for gx0, gy0, gx1, gy1 in groups:
        for sx0, sx1 in _split_cols(b, w, h, gx0, gx1, gy0, gy1):
            blocks.append({'x': sx0, 'y': gy0,
                           'w': sx1 - sx0 + 1, 'h': gy1 - gy0 + 1})
    blocks.sort(key=lambda c: c['x'])
    kinds = [_vc_classify(c) for c in blocks]
    op_idx = [i for i, k in enumerate(kinds) if k == 'op']
    digits = [(c, i) for i, (c, k) in enumerate(zip(blocks, kinds))
              if k == 'digit']
    if len(op_idx) == 1:
        i = op_idx[0]
        cb = blocks[i]
        if cb['h'] <= 9 and cb['w'] > 4:
            op_cands = ['x']
        elif 10 <= cb['h'] <= 12 and cb['w'] > 4:
            op_cands = ['+', 'x']
        else:
            op_cands = ['+']
        left = [c for c, _ in digits if c['x'] < cb['x']]
        right = [c for c, _ in digits if c['x'] > cb['x']]
    else:
        op_cands = ['-']
        left = [c for c, _ in digits]
        right = []
    try:
        if right:
            A = _vc_enum_num(left, b)
            B = _vc_enum_num(right, b)
            results = []
            for opc in op_cands:
                for da, va in A:
                    for db, vb in B:
                        if opc == '-' and va < vb:
                            continue
                        results.append((da + db, opc, va, vb))
            if not results:
                return None
            results.sort()
            return results[0][1], results[0][2], results[0][3]
        n = len(left)
        if n < 2:
            return None
        allouts = []
        for i in (max(1, n - 2), min(2, n - 1)):
            A = _vc_enum_num(left[:i], b)
            B = _vc_enum_num(left[i:], b)
            for da, va in A:
                for db, vb in B:
                    if vb >= 100:
                        continue
                    allouts.append((da + db, va, vb))
        if not allouts:
            return None
        allouts.sort()
        return '-', allouts[0][1], allouts[0][2]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# /god 与 url3 的 CDN rebase 规则 (来自 xlplayer.js 逆向)
# ---------------------------------------------------------------------------

_TOS_LIST = ['f19-', 'f77-', 'lf16-capcut.faceueditorv.com',
             'lf16-secsdk.bitssec.com', 'lf16-data.bytepluscdn.com',
             'lf16-fdm.fdimgs.com', 'lf16-cc-everphoto.faceulv.com',
             'lf16-capcut.faceulv.com',
             'lf16-geckocdn-offline.g-p-static.com']

_MARK = '||tsline||'


def _deal_url(u):
    """url3 直连 mp4 的 rkey/域名处理 (dealUrl 逆向)"""
    now = int(time.time() * 1000)
    if 'handler' in u:
        u += '/%d.mp4' % now
    u = u.replace('?rkey', '%d.mp4?ver=6010&rkey' % now)
    if 'bde4.cc' in u:
        u = u.replace('ftn_handler/', '%d.mp4?rkey=' % now)
        u = u.replace('bde4.cc', 'weiyun.com')
    return u


# ---------------------------------------------------------------------------
# Spider
# ---------------------------------------------------------------------------

# 模块级共享会话: 搜索验证码与 JSESSIONID 绑定, 30 分钟内免重复验证
_CJ = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_CJ),
    urllib.request.ProxyHandler({}))


def _strip_tags(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = (s.replace('&nbsp;', ' ').replace('&amp;', '&')
          .replace('&lt;', '<').replace('&gt;', '>')
          .replace('&quot;', '"').replace('&#39;', "'"))
    return re.sub(r'\s+', ' ', s).strip()


class Spider(Spider):

    def __init__(self):
        pass

    def init(self, extend=""):
        pass

    def getName(self):
        return '雪落影视'

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def liveContent(self, url):
        return ''

    # ==================== 基础请求 ====================

    def _http(self, url, data=None, referer=None, timeout=20):
        headers = {'User-Agent': UA,
                   'Accept': 'text/html,application/xhtml+xml,'
                             'application/xml;q=0.9,*/*;q=0.8'}
        if referer:
            headers['Referer'] = referer
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(url, data=data, headers=headers)
        res = _OPENER.open(req, timeout=timeout)
        return res.read()

    def _fetch_head(self, url, referer=None, rng='0-63', timeout=20):
        """Range 探测: 返回 (status, body)"""
        headers = {'User-Agent': UA, 'Range': 'bytes=' + rng}
        if referer:
            headers['Referer'] = referer
        req = urllib.request.Request(url, headers=headers)
        try:
            res = urllib.request.urlopen(req, timeout=timeout)
            return res.status, res.read()
        except urllib.error.HTTPError as e:
            return e.code, b''

    # ==================== 解析 ====================

    def _parse_cards(self, html):
        out = []
        seen = set()
        for m in re.finditer(r'class="movie-card"', html):
            seg = html[m.start():m.start() + 1600]
            am = re.search(r'title="([^"]+)"\s+href="([^"]+)"', seg)
            if not am:
                continue
            title = _strip_tags(am.group(1))
            href = am.group(2)
            if not re.search(r'/\d+\.htm$', href):
                continue
            if href in seen:
                continue
            seen.add(href)
            pm = re.search(r'data-src="([^"]+)"', seg)
            h4 = re.search(r'<h4>(.*?)</h4>', seg, re.S)
            date = re.search(r'<span>(\d{4}-\d{2}-\d{2})</span>', seg)
            name = _strip_tags(h4.group(1)) if h4 else title
            if not name:
                name = title
            remark = ''
            if '》' in title:
                remark = title.split('》', 1)[1].strip()
            if not remark and date:
                remark = date.group(1)
            ym = re.search(r'(\d{4})', title)
            out.append({
                'vod_id': href,
                'vod_name': name,
                'vod_pic': pm.group(1) if pm else '',
                'vod_remarks': remark,
                'vod_year': ym.group(1) if ym else '',
            })
        return out

    def _pagecount(self, html):
        m = re.search(r'href="/s/[^"]*/(\d+)[^"]*"[^>]*>\s*尾页', html)
        if m:
            return int(m.group(1))
        return 1

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {'class': [{'type_id': tid, 'type_name': name}
                            for tid, name in CATS]}
        if filter:
            common = [
                {'key': 'order', 'name': '排序', 'value': [
                    {'n': '最近更新', 'v': '0'},
                    {'n': '豆瓣评分', 'v': '1'}]},
                {'key': 'area', 'name': '地区', 'value':
                    [{'n': '全部', 'v': ''}] + [{'n': a, 'v': a}
                                                for a in AREAS]},
            ]
            result['filters'] = {tid: common for tid, _ in CATS}
        return result

    def homeVideoContent(self):
        try:
            html = self._http(HOST + '/', referer=SITE_REF).decode('utf-8', 'replace')
            vids = self._parse_cards(html)[:24]
        except Exception:
            vids = []
        return {'list': vids}

    # ==================== 分类 (下滑自动翻页) ====================

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        ext = {}
        if extend:
            if isinstance(extend, dict):
                ext = extend
            else:
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}
        if tid == 'all0' or tid == 'all1':
            path = '/s/all/%d' % pg if pg > 1 else '/s/all'
            q = {'type': '0' if tid == 'all0' else '1'}
        else:
            path = '/s/%s/%d' % (tid, pg) if pg > 1 else '/s/%s' % tid
            q = {}
        area = str(ext.get('area') or '').strip()
        if area:
            q['area'] = area
        order = str(ext.get('order') or '').strip()
        if order != '':
            q['order'] = order
        qs = '&'.join('%s=%s' % (k, urllib.parse.quote(v, safe=''))
                      for k, v in q.items()) if q else ''
        url = HOST + path + (('?' + qs) if qs else '')
        html = self._http(url, referer=SITE_REF).decode('utf-8', 'replace')
        cards = self._parse_cards(html)
        pages = self._pagecount(html)
        return {
            'list': cards,
            'page': pg,
            'pagecount': pages,
            'limit': 24,
            'total': pages * 24,
        }

    # ==================== 详情 ====================

    def detailContent(self, ids):
        path = str(ids[0]) if isinstance(ids, list) else str(ids)
        html = self._http(HOST + path, referer=SITE_REF).decode('utf-8', 'replace')
        hm = re.search(r'<h1 class="movie-title">(.*?)</h1>', html, re.S)
        name, year = '', ''
        if hm:
            t = _strip_tags(hm.group(1))
            m2 = re.match(r'(.*?)\s*[\(（](\d{4})[\)）]', t)
            if m2:
                name, year = m2.group(1).strip(), m2.group(2)
            else:
                name = t
        if not name:
            tm = re.search(r'<title>(.*?)\s*-\s*雪落影视', html, re.S)
            full = _strip_tags(tm.group(1)) if tm else ''
            m3 = re.search(r'《(.+?)》', full)
            name = m3.group(1) if m3 else full
        if not year:
            ym = re.search(r'[\(（](\d{4})[\)）]', html)
            year = ym.group(1) if ym else ''
        pm = re.search(r'movie-poster"><img src="([^"]+)"', html)
        if not pm:
            pm = re.search(r'(https://wework[^"]+)', html)
        pic = pm.group(1) if pm else ''
        remark = ''
        h2 = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.S)
        if h2:
            full = _strip_tags(h2.group(1))
            if '》' in full:
                remark = full.split('》', 1)[1].strip()
        info = {}
        for m in re.finditer(
                r'<span class="info-label">([^<]+)</span>(.*?)</div>',
                html, re.S):
            label = _strip_tags(m.group(1)).rstrip('：:')
            vals = [_strip_tags(v) for v in re.findall(
                r'class="info-value"[^>]*>([^<]+)<', m.group(2))]
            info[label] = vals
        dm = re.search(r'<div class="desc">(.*?)</div>', html, re.S)
        desc = _strip_tags(dm.group(1)) if dm else ''
        eps = []
        seen = set()
        for m in re.finditer(r'href="(/play/\d+-\d+\.htm)"[^>]*>([^<]+)<', html):
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
            eps.append('%s$%s' % (_strip_tags(m.group(2)), m.group(1)))
        vod = {
            'vod_id': path,
            'vod_name': name,
            'vod_pic': pic,
            'vod_year': year,
            'vod_remarks': remark,
            'vod_area': ','.join(info.get('制片国家', [])),
            'vod_type': ','.join(info.get('类型', [])),
            'vod_director': ','.join(info.get('导演', [])),
            'vod_actor': ','.join(info.get('主演', [])),
            'vod_content': desc,
            'vod_play_from': '雪落影视',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg='1'):
        return self._search(key)

    def searchContentPage(self, key, quick, pg='1'):
        return self._search(key)

    def _search(self, wd):
        kw = urllib.parse.quote(str(wd), safe='')
        url = HOST + '/search/' + kw
        html = ''
        try:
            html = self._http(url, referer=SITE_REF).decode('utf-8', 'replace')
        except Exception:
            pass
        for _ in range(6):
            if 'search/verifyCode' not in html:
                break
            try:
                img = self._http(HOST + '/search/verifyCode?t=%d'
                                 % int(time.time() * 1000), referer=url)
            except Exception:
                break
            r = _vc_solve_bytes(img)
            if r is None:
                continue
            opc, a, b = r
            val = {'+': a + b, '-': a - b, 'x': a * b}[opc]
            if val < 0:
                continue
            try:
                html = self._http(url + '?code=%d' % val,
                                  referer=url).decode('utf-8', 'replace')
            except Exception:
                continue
        items = []
        if 'xl-result-item' in html:
            for m in re.finditer(r'class="xl-result-item"', html):
                seg = html[m.start():m.start() + 3500]
                nm = re.search(r'class="xl-result-name"[^>]*href="([^"]+)"'
                               r'[^>]*>(.*?)</a>', seg, re.S)
                if not nm:
                    continue
                pic = re.search(r'<img[^>]+src="(https://[^"]+)"', seg)
                ym = re.search(r'上映：[^<]*?(\d{4})', seg)
                items.append({
                    'vod_id': nm.group(1),
                    'vod_name': _strip_tags(nm.group(2)),
                    'vod_pic': pic.group(1) if pic else '',
                    'vod_remarks': '',
                    'vod_year': ym.group(1) if ym else '',
                })
        return {'list': items, 'page': 1, 'pagecount': 1,
                'limit': 20, 'total': len(items)}

    # ==================== 播放 ====================

    def _get_lines(self, pid):
        t = int(time.time() * 1000)
        sg = _sign(pid, t)
        url = '%s/lines?t=%d&sg=%s&pid=%s' % (HOST, t, sg, pid)
        body = self._http(url, referer=SITE_REF)
        d = json.loads(body.decode('utf-8', 'replace'))
        return d.get('data') or {}

    def _god_url(self, pid, code='888', with_type=True):
        t = int(time.time() * 1000)
        sg = _sign(pid, t)
        data = urllib.parse.urlencode(
            {'t': t, 'sg': sg, 'verifyCode': code}).encode('ascii')
        url = '%s/god/%s%s' % (HOST, pid, '?type=1' if with_type else '')
        body = self._http(url, data=data, referer=SITE_REF)
        d = json.loads(body.decode('utf-8', 'replace'))
        u = (d.get('url') or '').strip()
        if not u:
            raise RuntimeError('god empty: %s' % (d.get('error') or ''))
        return u

    def _rebase_tos(self, u):
        for mark in ('tos-alisg-v-0000', 'tos-maliva-o-0000-us',
                     'tos-alisg-i-0000'):
            idx = u.find(mark)
            if idx < 0:
                continue
            if any(k in u for k in _TOS_LIST):
                if mark == 'tos-alisg-v-0000':
                    return 'http://lf77-geckocdn.bytegecko-i18n.com/obj/' + u[idx:]
                if mark == 'tos-maliva-o-0000-us':
                    return 'http://lf16-cdn-solve.gauthmath.com/obj/' + u[idx:]
                return 'https://lf16-anyweb.anyweb.space/obj/' + u[idx:]
            return 'https://p16-hera-sign-va.ibyteimg.com/obj/' + u[idx:]
        return u

    def _mp4_ok(self, url):
        try:
            st, body = self._fetch_head(url, referer=SITE_REF)
            return st in (200, 206) and len(body) >= 8 and (
                body[4:8] == b'ftyp' or body[:4] == b'\x00\x00\x00\x18')
        except Exception:
            return False

    def playerContent(self, flag, id, vipFlags):
        path = str(id) if not isinstance(id, list) else str(id[0])
        try:
            html = self._http(HOST + path,
                              referer=SITE_REF).decode('utf-8', 'replace')
            pm = re.search(r'var\s+pid\s*=\s*(\d+)', html)
            if not pm:
                raise RuntimeError('no pid')
            pid = pm.group(1)
        except Exception as e:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': {'User-Agent': UA},
                    'msg': '播放页获取失败: %s' % e}
        try:
            data = self._get_lines(pid)
        except Exception as e:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': {'User-Agent': UA},
                    'msg': '线路获取失败: %s' % e}
        cands = []
        for u in str(data.get('url3') or '').split(','):
            u = u.strip()
            if u:
                cands.append(('url3', u))
        if data.get('tos'):
            cands.append(('god', str(pid)))
        if data.get('ptoken'):
            cands.append(('god0', str(pid)))
        if data.get('m3u8'):
            cands.append(('m3u8', str(data.get('m3u8'))))
        for u in str(data.get('m3u8_2') or '').split(','):
            u = u.strip()
            if u:
                cands.append(('m3u8', u))
        # url3 域名修正 (www.xlys01.com → 当前域)
        fixed = []
        for kind, u in cands:
            if kind == 'url3':
                u = u.replace('www.xlys01.com', 'v.xl01.cc.ua')
            fixed.append((kind, u))
        cands = fixed
        header = {'User-Agent': UA, 'Referer': SITE_REF}
        for kind, u in cands:
            try:
                if kind == 'url3':
                    du = _deal_url(u)
                    if self._mp4_ok(du):
                        return {'parse': 0, 'playUrl': '', 'url': du,
                                'header': header}
                    ru = self._rebase_tos(du)
                    if ru != du and self._mp4_ok(ru):
                        return {'parse': 0, 'playUrl': '', 'url': ru,
                                'header': header}
                elif kind == 'god':
                    du = self._god_url(pid, '888', True)
                    if self._mp4_ok(du):
                        return {'parse': 0, 'playUrl': '', 'url': du,
                                'header': header}
                    ru = self._rebase_tos(du)
                    if ru != du and self._mp4_ok(ru):
                        return {'parse': 0, 'playUrl': '', 'url': ru,
                                'header': header}
                elif kind == 'god0':
                    du = _deal_url(self._god_url(pid, '666', False))
                    if self._mp4_ok(du):
                        return {'parse': 0, 'playUrl': '', 'url': du,
                                'header': header}
                elif kind == 'm3u8':
                    raw = u.split('#')
                    mu = raw[0].replace('www.bde4.cc', 'v.xl01.cc.ua')
                    label = raw[1] if len(raw) > 1 else ''
                    if not mu.startswith('http'):
                        continue
                    prox = ('proxy://do=py&type=m3u8&url=%s'
                            % _b64e(mu + _MARK + label))
                    return {'parse': 0, 'playUrl': '', 'url': prox,
                            'header': header}
            except Exception:
                continue
        return {'parse': 0, 'playUrl': '', 'url': '',
                'header': header, 'msg': '无可用线路'}

    # ==================== 代理 ====================

    def localProxy(self, param):
        try:
            if not isinstance(param, dict):
                return [404, 'text/plain', 'not found']
            ptype = (param.get('type') or '').strip()
            raw = (param.get('url') or '').strip()
            if not ptype or not raw:
                return [404, 'text/plain', 'not found']
            url = raw
            if not url.startswith(('http://', 'https://')):
                url = urllib.parse.unquote(url)
            if not url.startswith(('http://', 'https://')):
                url = _b64d(url).decode('utf-8', 'replace')
            if ptype == 'm3u8':
                return self._proxy_m3u8(url)
            if ptype == 'seg':
                return self._proxy_seg(url)
            return [404, 'text/plain', 'unknown type']
        except Exception as e:
            try:
                return [502, 'text/plain',
                        ('proxy error: %s' % e).encode('utf-8')]
            except Exception:
                return [502, 'text/plain', 'proxy error']

    def _proxy_m3u8(self, raw):
        if _MARK in raw:
            mu, label = raw.split(_MARK, 1)
        else:
            mu, label = raw, ''
        body = self._http(mu, referer=SITE_REF, timeout=25)
        if len(body) <= 3354 + 16:
            raise RuntimeError('m3u8 blob too small')
        blob = body[3354:]
        try:
            out = zlib.decompress(blob, 47)
        except Exception:
            out = zlib.decompress(blob, -15)
        text = out.decode('utf-8', 'replace')
        prefix = ('https://vod.xl01.me/hls/'
                  if label in ('2014-us', 'ac5634-us')
                  else 'https://vod.xl01.me/')
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                lines.append(line)
            elif re.search(r'\.ts($|\?)', line):
                ts = line if line.startswith('http') else prefix + line
                lines.append(self._proxy_url('seg', ts))
            else:
                lines.append(line)
        body_text = '\n'.join(lines) + '\n'
        return [200, 'application/vnd.apple.mpegurl',
                body_text.encode('utf-8')]

    def _proxy_seg(self, url):
        body = self._http(url, referer=SITE_REF, timeout=30)
        if body[:4] == b'\x89PNG':
            i = body.find(b'IEND')
            if i > 0:
                body = body[i + 8:]
        return [200, 'video/mp2t', body]

    def _proxy_url(self, ptype, raw_url):
        return 'proxy://do=py&type=%s&url=%s' % (ptype, _b64e(raw_url))
