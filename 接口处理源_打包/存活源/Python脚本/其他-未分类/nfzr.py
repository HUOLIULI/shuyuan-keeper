# -*- coding: utf-8 -*-
# 奈飞工厂 (netflixgc.com) TVBox dr_py 爬虫源
# ---------------------------------------------------------------------------
# 站点:  https://www.netflixgc.com  ("奈飞工厂" - Netflix风格免费影视平台)
#        苹果CMS10 + 自研模板(dsn2), 内容 = 电影/连续剧/纪录片/漫剧/综艺
#
# 列表:  POST /index.php/ds_api/vod  (明文JSON, 无WAF, 无需登录/无Referer校验)
#          参数: type & class & area & year & by(time|hot|score) & page
#          返回: {code:1, list:[40条], pagecount, total, limit:40}
#          每条: vod_id/vod_name/vod_pic/vod_remarks/vod_douban_score
# 搜索:  GET /vodsearch/{关键词}-------------.html
#        分页 GET /vodsearch/{关键词}----------{页码}---.html
# 详情:  GET /voddetail/{id}.html
#        全部线路(蓝光/1080P分组) + 各线路分集 都在页面内(隐藏容器)
# 播放:  GET /vodplay/{id}-{线路sid}-{集nid}.html
#        页内 player_aaaa={"encrypt":2,"url":"<base64>","from":"..."}
#        解码: base64解码 → url解码 → url解码 = 直链m3u8
#        (encrypt=0 时url即直链)
#
# 线路说明: 站方每片挂多条采集线路, tab按 蓝光N / 1080PN 分组
#           实测同片6条线: 优质(1080zyk)/ws/量子/电影天堂/暴风/非凡
#           优质与ws两条为无插播广告线路(1080P实测1920x1080),
#           非凡/暴风/爱坤等线路片内含插播广告 —— 播放时如遇广告请切线路
# 封面:  img.feifeiimg.vip / tupian.ffeiimg.com 等, 实测无防盗链直连可看
# ---------------------------------------------------------------------------

import sys
sys.path.append('..')
from base.spider import Spider

import re
import ssl
import json
import base64
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

HOST = 'https://www.netflixgc.com'
API = HOST + '/index.php/ds_api/vod'
SITE_REF = HOST + '/'

CATS = [
    ('1', '电影'),
    ('2', '连续剧'),
    ('24', '纪录片'),
    ('3', '漫剧'),
    ('23', '综艺'),
]

CLASSES = ['喜剧', '爱情', '恐怖', '动作', '科幻', '剧情', '犯罪', '奇幻',
           '悬疑', '惊悚', '家庭', '冒险', '同性', '运动', '战争', '历史',
           '古装', '武侠']
AREAS = ['韩国', '美国', '日本', '英国', '中国大陆', '中国香港', '中国台湾',
         '法国', '泰国', '加拿大', '西班牙', '印度', '德国', '意大利', '其他']
YEARS = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019',
         '2018', '2017', '2016', '2015']
SORTS = [('time', '最新'), ('hot', '最热'), ('score', '评分')]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _unquote_all(s, times=1):
    for _ in range(times):
        try:
            s = urllib.parse.unquote(s)
        except Exception:
            break
    return s


class Spider(Spider):

    Host = HOST

    # ==================== 生命周期 ====================

    def init(self, extend=""):
        pass

    def getName(self):
        return '奈飞工厂'

    def isVideoFormat(self, url):
        if not url:
            return False
        low = str(url).lower()
        return any(ext in low for ext in ('.m3u8', '.mp4', '.flv', '.ts'))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def liveContent(self, url):
        pass

    # ==================== 网络 ====================

    def _html(self, path, timeout=20):
        url = path if path.startswith('http') else HOST + path
        req = urllib.request.Request(url)
        req.add_header('user-agent', UA)
        req.add_header('referer', SITE_REF)
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
        return resp.read().decode('utf-8', 'replace')

    def _api(self, params, timeout=20):
        """POST ds_api/vod, 失败抛异常"""
        body = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(API, data=body)
        req.add_header('user-agent', UA)
        req.add_header('referer', SITE_REF)
        req.add_header('content-type', 'application/x-www-form-urlencoded')
        req.add_header('x-requested-with', 'XMLHttpRequest')
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
        return json.loads(resp.read().decode('utf-8', 'replace'))

    # ==================== 列表 ====================

    def _page(self, data):
        lst = []
        for it in (data.get('list') or []):
            try:
                name = (it.get('vod_name') or '').strip()
                if not name:
                    continue
                lst.append({
                    'vod_id': str(it.get('vod_id') or ''),
                    'vod_name': name,
                    'vod_pic': (it.get('vod_pic') or '').strip(),
                    'vod_remarks': (it.get('vod_remarks')
                                    or it.get('vod_tag') or '').strip(),
                    'vod_year': '',
                })
            except Exception:
                continue
        return {
            'list': lst,
            'page': int(data.get('page') or 1),
            'pagecount': int(data.get('pagecount') or 1),
            'total': int(data.get('total') or len(lst)),
        }

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {'class': [{'type_id': tid, 'type_name': name}
                            for tid, name in CATS]}
        if filter:
            cls_val = ([{'n': '全部', 'v': ''}] +
                       [{'n': c, 'v': c} for c in CLASSES])
            area_val = ([{'n': '全部', 'v': ''}] +
                        [{'n': a, 'v': a} for a in AREAS])
            year_val = ([{'n': '全部', 'v': ''}] +
                        [{'n': y, 'v': y} for y in YEARS])
            sort_val = [{'n': n, 'v': v} for v, n in SORTS]
            common = [
                {'key': 'by', 'name': '排序', 'value': sort_val},
                {'key': 'class', 'name': '类型', 'value': cls_val},
                {'key': 'area', 'name': '地区', 'value': area_val},
                {'key': 'year', 'name': '年份', 'value': year_val},
            ]
            result['filters'] = {tid: common for tid, _ in CATS}
        return result

    def homeVideoContent(self):
        try:
            d = self._api({'by': 'time', 'page': '1'})
            return {'list': self._page(d).get('list', [])[:24]}
        except Exception:
            return {'list': []}

    # ==================== 分类 ====================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        extend = extend or {}
        params = {
            'type': str(tid),
            'class': str(extend.get('class') or ''),
            'area': str(extend.get('area') or ''),
            'year': str(extend.get('year') or ''),
            'lang': '', 'version': '', 'state': '', 'letter': '',
            'time': '', 'level': '0', 'weekday': '',
            'by': str(extend.get('by') or 'time'),
            'page': str(pg),
        }
        try:
            d = self._api(params)
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'total': 0}
        return self._page(d)

    # ==================== 搜索 ====================

    def _search(self, key, pg):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        pg = max(1, pg)
        # 实测: 关键词用UTF-8编码; 若传GBK站点会退化成默认列表
        kwd = urllib.parse.quote(str(key or '').strip(), safe='')
        if pg == 1:
            path = '/vodsearch/%s-------------.html' % kwd
        else:
            path = '/vodsearch/%s----------%d---.html' % (kwd, pg)
        vids, names, pics, remarks = [], [], [], []
        try:
            html = self._html(path)
        except Exception:
            html = ''
        if html:
            chunks = html.split('class="detail-pic"')[1:]
            for ch in chunks:
                try:
                    m_id = re.search(r'href="/voddetail/(\d+)\.html"', ch)
                    if not m_id:
                        continue
                    vid = m_id.group(1)
                    m_name = re.search(r'<h3[^>]*>([^<]+)</h3>', ch)
                    name = (m_name.group(1) if m_name else '').strip()
                    if not name:
                        continue
                    m_pic = re.search(r'data-src="([^"]+)"', ch)
                    pic = (m_pic.group(1) if m_pic else '').strip()
                    m_rm = re.search(r'class="slide-info-remarks[^"]*">([^<]*)<',
                                     ch)
                    rm = (m_rm.group(1) if m_rm else '').strip()
                    m_yr = re.search(r'vodsearch/-------------?(\d{4})\.html',
                                     ch)
                    if m_yr:
                        rm = (rm + ' ' + m_yr.group(1)).strip()
                    vids.append(vid)
                    names.append(name)
                    pics.append(pic)
                    remarks.append(rm)
                except Exception:
                    continue
        lst = []
        for i in range(len(vids)):
            lst.append({
                'vod_id': vids[i],
                'vod_name': names[i],
                'vod_pic': pics[i],
                'vod_remarks': remarks[i],
            })
        return {'list': lst, 'page': pg}

    def searchContent(self, key, quick, pg='1'):
        return self._search(key, 1)

    def searchContentPage(self, key, quick, pg='1'):
        return self._search(key, pg)

    # ==================== 详情 ====================

    def _clean_links(self, block):
        return re.findall(r'>([^<]{1,60})</a>', block or '')

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        html = self._html('/voddetail/%s.html' % vid)

        m_name = re.search(r'<h3 class="slide-info-title hide">([^<]+)</h3>',
                           html)
        name = (m_name.group(1) if m_name else vid).strip()
        m_pic = re.search(r'class="detail-pic">[\s\S]{0,300}?data-src="([^"]+)"',
                          html)
        pic = (m_pic.group(1) if m_pic else '').strip()

        remarks, year, area = '', '', ''
        m_info = re.search(r'<div class="slide-info hide">'
                           r'([\s\S]{0,700}?)</div>', html)
        if m_info:
            blk = m_info.group(1)
            m_rm = re.search(r'class="slide-info-remarks[^"]*">([^<]*)<', blk)
            if m_rm:
                remarks = m_rm.group(1).strip()
            links = re.findall(r'<a href="/vodsearch/[^"]*"[^>]*>([^<]{1,12})</a>',
                               blk)
            for txt in links:
                t = txt.strip()
                if not t:
                    continue
                if re.match(r'^(19|20)\d{2}$', t) and not year:
                    year = t
                elif not area and t not in year:
                    area = t

        def _meta_row(label):
            m = re.search(label + r'\s*[:：]</strong>([\s\S]{0,600}?)</div>',
                          html)
            if not m:
                return ''
            parts = re.findall(r'<a[^>]*>([^<]{1,30})</a>', m.group(1))
            vals = [p.strip() for p in parts if p.strip()]
            return ','.join(vals)

        director = _meta_row('导演')
        actor = _meta_row('演员')
        type_name = _meta_row('类型')

        m_desc = re.search(r'id="height_limit"[^>]*>([\s\S]{0,2000}?)</div>',
                           html)
        desc = (m_desc.group(1) if m_desc else '').strip()
        desc = re.sub(r'<[^>]+>', '', desc).strip()

        # ---- 线路: anthology-tab 名称 与 anthology-list-box 分集按序配对 ----
        seg = html
        i_tab = seg.find('anthology-tab')
        i_list = seg.find('anthology-list', i_tab + 1) \
            if i_tab >= 0 else -1
        tab_names = []
        if i_tab >= 0 and i_list > i_tab:
            tabblk = seg[i_tab:i_list]
            for m in re.finditer(
                    r'<a class="swiper-slide">(?:\s*<i[^>]*></i>)?\s*'
                    r'(?:&nbsp;)?([^<]{1,16}?)\s*<span class="badge">',
                    tabblk):
                t = m.group(1).replace('&nbsp;', '').strip()
                tab_names.append(t or ('线路%d' % (len(tab_names) + 1)))

        boxes = []
        for m in re.finditer(r'anthology-list-box', seg):
            start = m.start()
            boxes.append(seg[start:start + 90000])
        if len(boxes) > 1:
            trimmed = []
            for bi, b in enumerate(boxes):
                end = b.find('anthology-list-box', 20)
                trimmed.append(b[:end] if end > 0 else b)
            boxes = trimmed

        lines, play_urls = [], []
        for bi, box in enumerate(boxes):
            eps = re.findall(
                r'href="(/vodplay/\d+-\d+-\d+\.html)"[^>]*>([^<]{1,20})<',
                box)
            if not eps:
                continue
            lid = str(bi)
            tname = tab_names[bi] if bi < len(tab_names) \
                else ('线路%d' % (bi + 1))
            lines.append('%s' % tname)
            play_urls.append('#'.join(
                '%s$%s' % (ep[1].strip(), ep[0]) for ep in eps))

        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': year,
            'vod_area': area,
            'vod_director': director,
            'vod_actor': actor,
            'vod_remarks': remarks,
            'vod_content': desc,
        }
        if not lines:
            lines = ['奈飞工厂']
            play_urls.append('正片$/vodplay/%s-1-1.html' % vid)
        vod['vod_play_from'] = '$$$'.join(lines)
        vod['vod_play_url'] = '$$$'.join(play_urls)
        return {'list': [vod]}

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')
        if not raw.startswith('/vodplay/'):
            raw = '/vodplay/' + raw.lstrip('/')
        if not raw.endswith('.html'):
            raw += '.html'
        header = {'user-agent': UA, 'referer': SITE_REF}
        try:
            html = self._html(raw)
        except Exception as e:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': header, 'msg': '取播放页失败: %s' % e}
        m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]{10,5000}?\})\s*<', html)
        play_url, fromm = '', ''
        if m:
            try:
                obj = json.loads(m.group(1))
            except Exception:
                obj = None
            src = obj or {}
            enc = str(src.get('encrypt') or '0')
            play_url = (src.get('url') or '').strip()
            fromm = (src.get('from') or '').strip()
            if play_url and enc in ('1', '2'):
                try:
                    b64 = base64.b64decode(
                        play_url + '=' * (-len(play_url) % 4)
                    ).decode('utf-8', 'replace')
                    play_url = _unquote_all(b64, 2 if enc == '2' else 1)
                except Exception:
                    play_url = ''
        if not play_url:
            m2 = re.search(r'["\']?(https?://[^"\'\s]{15,200}\.m3u8[^"\'\s]{0,40})',
                           html)
            if m2:
                play_url = m2.group(1)
        if not play_url:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': header, 'msg': '未取到播放地址'}
        low = play_url.lower()
        if ('.m3u8' in low) or ('.mp4' in low) or ('.flv' in low):
            parse = '0'
        elif fromm in ('qiyi', 'qq', 'youku', 'mgtv', 'bilibili'):
            parse = '1'
        else:
            parse = '0'
        return {'parse': parse, 'playUrl': '', 'url': play_url,
                'header': header}
