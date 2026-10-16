# -*- coding: utf-8 -*-
# 全看电影网(www.qkw1.com) TVBox dr_py 爬虫源
# ---------------------------------------------------------------------------
# 功能:
#   1. 搜索          → /qkwsearch/{词}-------------.html, 支持下滑翻页
#                      (第2页起 /qkwsearch/{词}----------1--{页}-.html)
#   2. 分类/筛选     → 5大分类(电影/连续剧/综艺/动漫/短剧)
#                      子类/地区/排序 走 /qkwshow/{slug}-{区}-{排}--------{页}---.html
#                      年份走 /qkwsearch/----------{页}---{年}.html
#                      (站点 qkwshow 年份槽是坏的: 数字被当地区, 已实测)
#   2.1 搜索限速     → 站点限制 6 秒/次搜索, 源内自动等待错峰
#   3. 下滑自动翻页  → categoryContent 按 pg 递增:
#                      无筛选 /qkwlist/{tid}-{pg}.html
#                      有筛选 /qkwshow/{slug}--------{pg}---.html
#   4. 获取所有播放源 → 详情页 7 条线路(樱樱秒播/JP超清/酷高清/QKW/YZ/BF/LZ),
#                      每条线路完整分集列表, 按站点默认顺序排列
#   5. 直连播放      → 播放页 player_aaaa{"encrypt":3,"url":"XXXO0O0O混淆串",
#                      "from":"yinghua/1080zyk/lzm3u8/..."} (页面有403 Cookie
#                      挑战, 两轮握手自动过) → 混淆串 b64 后 POST 站点解析器
#                      /admin/mizhi_json.php (必须带 X-Requested-With 头)
#                      → 返回真实 mp4/m3u8 直链, parse=0 免嗅探秒播
#
# 站点结构(2026-10 实测, MacCMS + stui 模板):
#   详情: /qkwtv/{id}.html
#   播放: /qkwplay/{id}-{sid}-{nid}.html  线路面板 h3.title=线路名
#   卡片: <li class="stui-vodlist__item"><a class="stui-vodlist__thumb
#          lazyload" href="/qkwtv/{id}.html" title="片名"
#          data-original="海报"><span class="pic-text">备注</span>
#   解析器: https://zyz-...-cp11.xmsu8.top/index.php (所有线路共用)
#           POST /admin/mizhi_json.php  url=b64("{obf}&type={from}")
#           → {"code":"200","url":"真实直链","is_hls":bool}
#   注意: 服务器对 HTTP/2 挂起, 必须 HTTP/1.1 (urllib 默认即是)
#         douyinvod 类 mp4 直链带 Referer 会 403 → 播放头只带 UA
# ---------------------------------------------------------------------------
import sys
sys.path.append('..')
from base.spider import Spider

import re
import ssl
import json
import time
import base64
import urllib.parse
import urllib.request
import http.cookiejar

UA = ('Mozilla/5.0 (Linux; Android 11; M2012K11AC) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

HOST = 'https://www.qkw1.com'
PARSER = ('https://zyz-omtcqq-com-oss-cn-hangzhou-shanghai-yys-'
          'valipl-vip-cp11.xmsu8.top')

# 分类: tid 与站点 /qkwlist/{tid}.html 及 /qkwshow/{tid}-*.html 对应
CLASSES = [
    {'type_id': 'dy',     'type_name': '电影'},
    {'type_id': 'tv',     'type_name': '连续剧'},
    {'type_id': 'zy',     'type_name': '综艺'},
    {'type_id': 'dm',     'type_name': '动漫'},
    {'type_id': 'duanju', 'type_name': '短剧'},
]

# 子类(类别筛选): v 为 qkwshow slug
SUB_CLASS = {
    'dy': [('dongzuo', '动作片'), ('xiju', '喜剧片'), ('aiqing', '爱情片'),
           ('kehuan', '科幻片'), ('kongbu', '恐怖片'), ('juqing', '剧情片'),
           ('zhanzheng', '战争片'), ('qihuan', '奇幻片'), ('jilu', '纪录片'),
           ('xuanyi', '悬疑片'), ('fanzui', '犯罪片'), ('jingsong', '惊悚片')],
    'tv': [('guochan', '国产剧'), ('gangtai', '港台剧'), ('rihan', '日韩剧'),
           ('oumei', '欧美剧'), ('haiwai', '海外剧')],
}
AREAS = ['大陆', '中国香港', '中国台湾', '美国', '韩国', '日本', '泰国',
         '新加坡', '马来西亚', '印度', '英国', '法国', '加拿大', '西班牙',
         '俄罗斯', '其它']
YEARS = [str(y) for y in range(2026, 2005, -1)]
SORTS = [('time', '最新'), ('hits', '最热'), ('score', '评分')]
SEARCH_GAP = 6.5   # 站点搜索限速 6 秒/次, 留 0.5 秒余量

RE_CARD = re.compile(
    r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*'
    r'href="/qkwtv/(\d+)\.html"[^>]*title="([^"]*)"[^>]*>', re.S)
RE_CARD_PIC = re.compile(r'data-original="([^"]+)"')
RE_CARD_NOTE = re.compile(r'class="pic-text[^"]*"[^>]*>([^<]*)<')
RE_BLOCK = re.compile(
    r'(<li class="stui-vodlist__item">.*?</li>)', re.S)
RE_PLAYER = re.compile(r'player_aaaa\s*=\s*(\{.*?\})\s*[;<]', re.S)
RE_MEDIA = re.compile(r'\.(m3u8|mp4|flv|mkv)(\?|$|&)', re.I)
# 详情页: 线路面板 = h3.title(线路名) + ul.stui-content__playlist(分集)
RE_SOURCE = re.compile(
    r'<h3 class="title">([^<]+)</h3>\s*</div>\s*'
    r'<ul class="stui-content__playlist[^"]*">(.*?)</ul>', re.S)
RE_EP = re.compile(r'href="/qkwplay/(\d+-(\d+)-(\d+))\.html"[^>]*>([^<]+)<')
RE_THUMB = re.compile(
    r'stui-content__thumb.*?title="([^"]*)".*?'
    r'data-original="([^"]+)"', re.S)
RE_META = {
    'type':  re.compile(r'类型：</span><a href="([^"]+)"[^>]*>([^<]+)</a>'),
    'year':  re.compile(r'年份：</span><a href="([^"]+)"[^>]*>([^<]+)</a>'),
    'area':  re.compile(r'地区：</span><a href="([^"]+)"[^>]*>([^<]+)</a>'),
    'director': re.compile(r'导演：</span>(.*?)</p>', re.S),
    'actor':    re.compile(r'主演：</span>(.*?)</p>', re.S),
    'desc':     re.compile(r'简介：</span>(.*?)</p>', re.S),
    'update':   re.compile(r'更新：</span>([^<]*)<'),
}
RE_LINK_TXT = re.compile(r'<a[^>]*>([^<]+)</a>')


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Spider(Spider):

    Host = HOST
    _opener = None
    _last_search = 0.0   # 上次搜索时间戳(站点 6 秒/次限速)

    # ==================== 生命周期 ====================

    def init(self, extend=""):
        jar = http.cookiejar.CookieJar()
        handler = urllib.request.HTTPCookieProcessor(jar)
        self._opener = urllib.request.build_opener(
            handler, urllib.request.HTTPSHandler(context=_ssl_ctx()))

    def getName(self):
        return '全看电影网'

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._opener = None

    def localProxy(self, param):
        return []

    # ==================== 网络层 ====================

    def _http(self, url, referer=None, timeout=15, data=None, xhr=False):
        """GET/POST(cookiejar 自动管理), 播放页 403 Cookie 挑战自动两轮握手"""
        headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/json,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        if referer:
            headers['Referer'] = referer
        if xhr:
            headers['X-Requested-With'] = 'XMLHttpRequest'
            headers['Content-Type'] = \
                'application/x-www-form-urlencoded'
        last_err = ''
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=headers,
                                             data=data)
                resp = self._opener.open(req, timeout=timeout)
                raw = resp.read()
                try:
                    text = raw.decode('utf-8')
                except UnicodeDecodeError:
                    text = raw.decode('utf-8', 'ignore')
                # 未过挑战/被跳转: 页面无正文或 player 页无 player_aaaa
                if data is None and text and len(text) < 400 \
                        and 'window.location' in text:
                    time.sleep(0.3)
                    continue
                return text
            except urllib.error.HTTPError as e:
                last_err = str(e)
                if e.code in (403, 503):
                    # Cookie 挑战: 服务端已 Set-Cookie, 原样重试即可
                    try:
                        e.read()
                    except Exception:
                        pass
                    time.sleep(0.3)
                    continue
                return ''
            except Exception as e:
                last_err = str(e)
                time.sleep(0.3)
        if last_err:
            pass
        return ''

    def _pic(self, raw):
        if not raw:
            return ''
        raw = raw.replace('&amp;', '&')
        if raw.startswith('//'):
            return 'https:' + raw
        if raw.startswith('/'):
            return HOST + raw
        return raw

    def _strip_tags(self, s):
        s = re.sub(r'<[^>]+>', ' ', s or '')
        return re.sub(r'\s+', ' ', s).strip()

    def _parse_cards(self, html, limit=0):
        """通用卡片解析: 详情链接+标题+备注+海报(首页/列表/搜索通用)"""
        out, seen = [], set()
        for block in RE_BLOCK.findall(html):
            m = RE_CARD.search(block)
            if not m:
                continue
            vid, name = m.group(1), m.group(2)
            if vid in seen:
                continue
            note = RE_CARD_NOTE.search(block)
            pic = RE_CARD_PIC.search(block)
            seen.add(vid)
            out.append({
                'vod_id': vid,
                'vod_name': name.strip(),
                'vod_pic': self._pic(pic.group(1)) if pic else '',
                'vod_remarks': note.group(1).strip() if note else '',
            })
            if limit and len(out) >= limit:
                break
        return out

    # ==================== qkwshow URL 构造 ====================
    # 12 段: [slug, 地区/年份, 排序, -, -, -, -, -, 页码, -, -, -]

    def _show_url(self, slug, area='', by='', pg=1):
        parts = [''] * 12
        parts[0] = slug
        if area:
            parts[1] = area
        if by:
            parts[2] = by
        if pg and int(pg) > 1:
            parts[8] = str(pg)
        seg = '-'.join(parts)
        return '%s/qkwshow/%s.html' % (HOST, urllib.parse.quote(seg))

    def _year_url(self, year, pg=1):
        """年份筛选: 站点 qkwshow 年份槽失效(数字被当地区),
        走 qkwsearch 年份槽: /qkwsearch/----------{页}---{年}.html"""
        try:
            pg = int(pg)
        except (TypeError, ValueError):
            pg = 1
        seg = '----------%d---%s' % (pg if pg > 0 else 1, year)
        return '%s/qkwsearch/%s.html' % (HOST, seg)

    def _wait_search_gap(self):
        """搜索限速守护: 距上次搜索不足 6 秒则等待"""
        now = time.time()
        gap = now - self._last_search
        if self._last_search > 0 and gap < SEARCH_GAP:
            time.sleep(SEARCH_GAP - gap)
        self._last_search = time.time()

    @staticmethod
    def _filters(tid):
        """TVBox 筛选面板: 子类/地区/年份/排序"""
        flt = []
        subs = SUB_CLASS.get(tid)
        if subs:
            flt.append({
                'key': 'class', 'name': '类别',
                'value': [{'n': '全部', 'v': ''}] +
                         [{'n': name, 'v': slug} for slug, name in subs],
            })
        flt.append({
            'key': 'area', 'name': '地区',
            'value': [{'n': '全部', 'v': ''}] +
                     [{'n': a, 'v': a} for a in AREAS],
        })
        flt.append({
            'key': 'year', 'name': '年份',
            'value': [{'n': '全部', 'v': ''}] +
                     [{'n': y + '年', 'v': y} for y in YEARS],
        })
        flt.append({
            'key': 'by', 'name': '排序',
            'value': [{'n': '默认', 'v': ''}] +
                     [{'n': name, 'v': slug} for slug, name in SORTS],
        })
        return flt

    # ==================== TVBox 接口 ====================

    def homeContent(self, filter):
        result = {'class': CLASSES}
        if filter:
            result['filters'] = {c['type_id']: self._filters(c['type_id'])
                                 for c in CLASSES}
        return result

    def homeVideoContent(self):
        html = self._http(HOST + '/')
        return {'list': self._parse_cards(html, limit=40)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except (TypeError, ValueError):
            pg = 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}
        cls = extend.get('class') or ''
        area = extend.get('area') or ''
        year = extend.get('year') or ''
        by = extend.get('by') or ''
        if year:
            # 年份走 qkwsearch(站点 qkwshow 年份槽失效), 不与其它筛选组合
            url = self._year_url(year, pg)
        elif cls or area or by:
            url = self._show_url(cls or tid, area=area, by=by, pg=pg)
        else:
            if pg > 1:
                url = '%s/qkwlist/%s-%d.html' % (HOST, tid, pg)
            else:
                url = '%s/qkwlist/%s.html' % (HOST, tid)
        html = self._http(url, referer=HOST + '/')
        items = self._parse_cards(html)
        return {
            'list': items,
            'page': pg,
            'pagecount': 9999 if items else pg,
            'limit': 36,
            'total': 999999 if items else 0,
        }

    def searchContent(self, key, quick, pg='1'):
        return self._search(key, pg)

    def searchContentPage(self, key, quick, pg='1'):
        return self._search(key, pg)

    def _search(self, key, pg='1'):
        try:
            pg = int(pg)
        except (TypeError, ValueError):
            pg = 1
        key = (key or '').strip()
        if not key:
            return {'list': [], 'page': 1}
        # 支持直接粘详情页链接/纯数字ID直达
        m = re.search(r'qkwtv/(\d+)\.html', key)
        if not m:
            m = re.match(r'^(\d{3,9})$', key)
        if m:
            vid = m.group(1)
            items = self._parse_cards(self._http(
                '%s/qkwtv/%s.html' % (HOST, vid), referer=HOST + '/'))
            if items:
                return {'list': items[:1], 'page': 1}
            return {'list': [{'vod_id': vid, 'vod_name': 'ID:' + vid,
                              'vod_pic': '', 'vod_remarks': '直达'}],
                    'page': 1}
        wd = urllib.parse.quote(key)
        self._wait_search_gap()
        if pg > 1:
            url = '%s/qkwsearch/%s----------1--%d-.html' % (HOST, wd, pg)
        else:
            url = '%s/qkwsearch/%s-------------.html' % (HOST, wd)
        html = self._http(url, referer=HOST + '/')
        if '请不要频繁操作' in html:
            # 被限速: 等 6.5 秒重试一次
            time.sleep(SEARCH_GAP)
            self._last_search = time.time()
            html = self._http(url, referer=HOST + '/')
        items = self._parse_cards(html)
        return {'list': items, 'page': pg}

    def detailContent(self, ids):
        vid = re.sub(r'\D', '', str(ids[0])) or str(ids[0])
        url = '%s/qkwtv/%s.html' % (HOST, vid)
        html = self._http(url, referer=HOST + '/')
        if not html:
            return {'list': [{'vod_id': vid, 'vod_name': '加载失败'}]}

        # 标题/海报/备注: 详情头图区块(stui-content__thumb)
        name = pic = ''
        remark = ''
        mt = RE_THUMB.search(html)
        if mt:
            name = mt.group(1).strip()
            pic = mt.group(2)
        if not name:
            m2 = re.search(r'<title>《?([^》<]+)》?', html)
            name = m2.group(1).strip() if m2 else vid
        mnote = re.search(r'stui-content__thumb.*?class="pic-text[^"]*"'
                          r'[^>]*>([^<]*)<', html, re.S)
        if mnote:
            remark = mnote.group(1).strip()

        # 信息区: 类型/年份/地区/导演/主演/简介/更新
        vod_class = year = area = director = actor = content = ''
        m = RE_META['type'].search(html)
        if m:
            vod_class = m.group(2).strip()
        m = RE_META['year'].search(html)
        if m:
            year = m.group(2).strip()
        m = RE_META['area'].search(html)
        if m:
            area = m.group(2).strip()
        m = RE_META['director'].search(html)
        if m:
            director = self._strip_tags('/'.join(
                RE_LINK_TXT.findall(m.group(1)))).strip('/ ')
        m = RE_META['actor'].search(html)
        if m:
            actor = self._strip_tags('/'.join(
                RE_LINK_TXT.findall(m.group(1)))).strip('/ ')
        m = RE_META['desc'].search(html)
        if m:
            content = self._strip_tags(m.group(1))
            content = re.sub(r'详细\s*>?\s*$', '', content).strip()
        m = RE_META['update'].search(html)
        if m and not remark:
            remark = m.group(1).strip()

        # 线路 + 分集: h3.title(线路名) ↔ ul.stui-content__playlist
        flags, play_groups = [], []
        for sm in RE_SOURCE.finditer(html):
            fname = sm.group(1).strip()
            eps, seen = [], set()
            for em in RE_EP.finditer(sm.group(2)):
                pid = em.group(1)
                if pid in seen:
                    continue
                seen.add(pid)
                ep = em.group(4).strip()
                eps.append('%s$%s' % (ep, pid))
            if eps:
                flags.append(fname)
                play_groups.append('#'.join(eps))

        if not flags:
            flags, play_groups = ['默认线路'], ['播放$%s-1-1' % vid]

        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': self._pic(pic),
            'type_name': vod_class,
            'vod_year': year,
            'vod_area': area,
            'vod_remarks': remark or ('共%d线' % len(flags)),
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': content or name,
            'vod_play_from': '$$$'.join(flags),
            'vod_play_url': '$$$'.join(play_groups),
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        pid = str(id)
        if not re.match(r'^\d+-\d+-\d+$', pid):
            # 容错: 只给数字ID时取线路1第1集
            m = re.match(r'^(\d+)$', pid)
            pid = '%s-1-1' % m.group(1) if m else ''
        if not pid:
            return {'parse': 1, 'playUrl': '', 'url': HOST,
                    'header': {'User-Agent': UA}}
        play_url = '%s/qkwplay/%s.html' % (HOST, pid)
        html = self._http(play_url, referer=HOST + '/')
        obf = frm = play_data = ''
        m = RE_PLAYER.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                obf = (data.get('url') or '').strip()
                frm = (data.get('from') or '').strip()
                play_data = (data.get('play_data') or '').strip()
            except Exception:
                obf = frm = ''
        if not obf:
            # 兜底: TVBox WebView 嗅探站点播放页
            return {'parse': 1, 'playUrl': '', 'url': play_url,
                    'header': {'User-Agent': UA,
                               'Referer': HOST + '/'}}
        # 混淆串 → 解析器直解: b64("{obf}&type={from}") POST mizhi_json
        real = self._resolve_parser(obf, frm)
        if real:
            return {'parse': 0, 'playUrl': '', 'url': real,
                    'header': {'User-Agent': UA}}
        # 直解失败 → 回退嗅探解析页(iframe 播放器)
        target = ('%s/index.php?url=%s&type=%s&data=%s'
                  % (PARSER, urllib.parse.quote(obf, safe=''),
                     urllib.parse.quote(frm or 'yinghua', safe=''),
                     urllib.parse.quote(play_data, safe='')))
        return {'parse': 1, 'playUrl': '', 'url': target,
                'header': {'User-Agent': UA, 'Referer': HOST + '/'}}

    def _resolve_parser(self, obf, frm):
        """站点解析器直解: POST /admin/mizhi_json.php
        url=b64("{obf}&type={from}") + X-Requested-With 头(必须)
        → {"code":"200","url":"真实mp4/m3u8"} 直链分钟级时效, 每次现解"""
        try:
            payload = base64.b64encode(
                ('%s&type=%s' % (obf, frm or 'yinghua'))
                .encode('utf-8')).decode('ascii')
            data = urllib.parse.urlencode({'url': payload}).encode()
            text = self._http(
                PARSER + '/admin/mizhi_json.php', data=data, xhr=True,
                referer=PARSER + '/index.php', timeout=18)
            if not text:
                return ''
            info = json.loads(text)
            if str(info.get('code')) == '200' and info.get('url'):
                return str(info['url']).strip()
        except Exception:
            pass
        return ''
