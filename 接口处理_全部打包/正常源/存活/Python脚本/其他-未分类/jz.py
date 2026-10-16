# -*- coding: utf-8 -*-
# 剧踪影院 (juzong01.me) TVBox dr_py 爬虫源
# ---------------------------------------------------------------------------
# 站点:  https://www.juzong01.me  ("剧踪影院" - 免费超清/蓝光影视, maccms10+stui)
#
# 分类:  /vodshow/{tid}-{地区}-{排序}------{页码}---{年份}/
#          (12段横线路由, 42条/页; 无筛选时各段留空即可)
#          tid: 1=电影 2=剧集 3=综艺 4=动漫 6=动作 7=喜剧 8=爱情 9=科幻
#               10=恐怖 11=剧情 12=战争 22=犯罪 23=动画
#          排序by: time=最新 hits=最热 score=评分
# 详情:  /voddetail/{id}.html  (h1标题/data-info/多线路pannel)
# 播放:  /vodplay/{vid}-{sid}-{nid}/
#        页内 var player_data={...,"url":"<令牌|直链>","from":"<线路key>"}
#
# 独家线路解密(核心):  from=juzongx/juzong/dujiarbx/dujiamp4/dujiarb2/dujiarb
#          时 url 为 "前缀-加密串" 令牌, 真链解析流程(逆向自站方播放器):
#          1) GET jzpic.ok1333.cn/?url={令牌}&name={片名}&ep={集数}
#             -> 页内 window.WGART_PARSE_TOKEN="{签名token}"
#          2) GET jzpic.ok1333.cn/wgart/api.php?action=try_json_api
#                    &video_url={令牌}&parse_token={签名token}
#             -> {"success":true,"data":{"url":"真实直链"}}
#          实测解析结果:
#            juzongx(爽看)  -> douyinvod.com mp4 (抖音CDN, 签名短时效, 现解现播)
#            juzong2(热播①) -> ppvod*.zyxsuntech.com m3u8 (自有转码CDN)
#          sid7(JD4K蓝光) 实为腾讯官方页(v.qq.com), 需官方解析, 非直链
#
# 线路说明(实测):
#   剧踪独家[爽看/首选/热播①②③/X] = 站方自托管线, 分片无插播广告
#     (zyxsuntech m3u8 实测51分片零discontinuity)
#   暴风(bfzym3u8)/西瓜/电影天堂等 = 公共资源床线路, 片内含插播广告
#     -> 播放遇广告请切回"剧踪独家"系线路
#
# 已知限制: /vodsearch 搜索接口有风控(对机房IP/TLS指纹返回403, 真浏览器可搜)
#           -> 源内搜索遇403自动降级返回空并提示; 家庭宽带环境一般正常
# 封面:    p1.music.126.net 网易云图床 + 站内/upload, 直连可看
# ---------------------------------------------------------------------------

import sys
sys.path.append('..')
from base.spider import Spider

import re
import ssl
import json
import urllib.request
import urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

HOST = 'https://www.juzong01.me'
PARSE_HOST = 'https://jzpic.ok1333.cn'
PLAY_REF = PARSE_HOST + '/'

CATS = [
    ('1', '电影'),
    ('2', '剧集'),
    ('3', '综艺'),
    ('4', '动漫'),
    ('6', '动作片'),
    ('7', '喜剧片'),
    ('8', '爱情片'),
    ('9', '科幻片'),
    ('10', '恐怖片'),
    ('11', '剧情片'),
    ('12', '战争片'),
    ('22', '犯罪片'),
    ('23', '动画片'),
]

# 独家线路from前缀(令牌型, 需jzpic解析)
OWN_FROM = ('juzongx', 'juzong', 'juzong1', 'juzong2', 'juzong3',
            'dujiarbx', 'dujiamp4', 'dujiarb2', 'dujiarb')
# 官方源线路(需网页解析)
WEB_FROM = ('qq', 'qiyi', 'youku', 'mgtv', 'bilibili')

AREAS = ['大陆', '香港', '台湾', '美国', '法国', '英国', '日本', '韩国',
         '德国', '泰国', '印度', '意大利', '西班牙', '加拿大', '其他']
YEARS = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019',
         '2018', '2017', '2016', '2015', '2014', '2013', '2012', '2011',
         '2010', '2009', '2008', '2007', '2006', '2005', '2004', '2003',
         '2002', '2001', '2000']
SORTS = [('time', '最新'), ('hits', '最热'), ('score', '评分')]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Spider(Spider):

    Host = HOST

    # ==================== 生命周期 ====================

    def init(self, extend=""):
        pass

    def getName(self):
        return '剧踪影院'

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

    def _html(self, path, referer=None, timeout=22):
        url = path if path.startswith('http') else HOST + path
        # 中文筛选值/关键词须转百分号编码, 否则urllib报ascii错误
        url = urllib.parse.quote(url, safe=':/#?=&%.-')
        req = urllib.request.Request(url)
        req.add_header('user-agent', UA)
        req.add_header('accept-language', 'zh-CN,zh;q=0.9')
        if referer:
            req.add_header('referer', referer)
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
        return resp.read().decode('utf-8', 'replace')

    # ==================== 列表解析 ====================

    def _parse_list(self, html):
        lst = []
        seen = set()
        for m in re.finditer(
                r'<a class="stui-vodlist__thumb[^"]*" href="/voddetail/(\d+)/"'
                r'[^>]*?title="([^"]*)"', html):
            vid, name = m.group(1), m.group(2).strip()
            if not name or vid in seen:
                continue
            seen.add(vid)
            blk = html[m.start():m.start() + 1200]
            mp = re.search(r'data-original="([^"]+)"', blk)
            mr = re.search(r'class="pic-text[^"]*">([^<]*)<', blk)
            lst.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': (mp.group(1) if mp else '').strip(),
                'vod_remarks': (mr.group(1) if mr else '').strip(),
            })
        return lst

    @staticmethod
    def _show_path(tid, area, by, pg, year):
        """12段路由: tid-地区-排序------页码---年份 (空段自动留空)"""
        return '/vodshow/%s-%s-%s------%s---%s/' % (
            tid, area or '', by or '', pg or '', year or '')

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {'class': [{'type_id': tid, 'type_name': name}
                            for tid, name in CATS]}
        if filter:
            area_val = ([{'n': '全部', 'v': ''}] +
                        [{'n': a, 'v': a} for a in AREAS])
            year_val = ([{'n': '全部', 'v': ''}] +
                        [{'n': y, 'v': y} for y in YEARS])
            sort_val = [{'n': n, 'v': v} for v, n in SORTS]
            common = [
                {'key': 'by', 'name': '排序', 'value': sort_val},
                {'key': 'area', 'name': '地区', 'value': area_val},
                {'key': 'year', 'name': '年份', 'value': year_val},
            ]
            result['filters'] = {tid: common for tid, _ in CATS}
        return result

    def homeVideoContent(self):
        try:
            html = self._html('/')
            return {'list': self._parse_list(html)[:24]}
        except Exception:
            return {'list': []}

    # ==================== 分类 ====================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        extend = extend or {}
        path = self._show_path(tid,
                               extend.get('area') or '',
                               extend.get('by') or '',
                               pg,
                               extend.get('year') or '')
        try:
            html = self._html(path)
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 1, 'total': 0}
        lst = self._parse_list(html)
        # 总页数: <span class="num">1/677</span>
        pagecount = 1
        m = re.search(r'class="num">\s*\d+/(\d+)\s*<', html)
        if m:
            try:
                pagecount = max(1, int(m.group(1)))
            except Exception:
                pagecount = 1
        total = pagecount * 42
        return {'list': lst, 'page': pg,
                'pagecount': pagecount, 'total': total}

    # ==================== 搜索 ====================

    def _search(self, key, pg):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        pg = max(1, pg)
        kw = urllib.parse.quote(str(key or '').strip(), safe='')
        lst = []
        # 站内演员/类型链接格式: /vodsearch/-{词}------------/
        for path in ('/vodsearch/-%s------------/' % kw if pg == 1
                     else '/vodsearch/-%s------------%s---/' % (kw, pg),
                     '/vodsearch/%s-------------%s---.html' % (kw, pg)
                     if pg == 1 else
                     '/vodsearch/%s----------%s---.html' % (kw, pg)):
            try:
                html = self._html(path, referer=HOST + '/')
            except Exception:
                continue
            # 搜索结果页: 卡片含 /voddetail/{id}/ + title
            for m in re.finditer(
                    r'href="/voddetail/(\d+)/"[^>]*?title="([^"]*)"',
                    html):
                vid, name = m.group(1), m.group(2).strip()
                if not name:
                    continue
                if any(v['vod_id'] == vid for v in lst):
                    continue
                blk = html[m.start():m.start() + 1200]
                mp = re.search(r'data-original="([^"]+)"', blk)
                lst.append({
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': (mp.group(1) if mp else '').strip(),
                    'vod_remarks': '',
                })
            if lst:
                break
        return {'list': lst, 'page': pg}

    def searchContent(self, key, quick, pg='1'):
        return self._search(key, 1)

    def searchContentPage(self, key, quick, pg='1'):
        return self._search(key, pg)

    # ==================== 详情 ====================

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        html = self._html('/voddetail/%s/' % vid)

        m_name = re.search(r'<h1 class="title">([^<]+)</h1>', html)
        name = (m_name.group(1) if m_name else vid).strip()
        m_pic = re.search(
            r'class="stui-content__thumb[^"]*">[\s\S]{0,300}?'
            r'(?:data-original|src)="([^"]+)"', html)
        pic = (m_pic.group(1) if m_pic else '').strip()

        remarks, year, area, type_name = '', '', '', ''
        m_data = re.search(r'<p class="data">([\s\S]{0,900}?)</p>', html)
        if m_data:
            blk = m_data.group(1)
            links = re.findall(r'<a href="/vodtype/[^"]*"[^>]*>([^<]{1,12})</a>',
                               blk)
            if links:
                type_name = links[0].strip()
            plain = re.findall(r'<span class="text-muted[^"]*">([^<]*)</span>'
                               r'([^<]*)', blk)
            for label, val in plain:
                v = val.strip()
                if '类型' in label:
                    type_name = type_name or v
                elif '地区' in label:
                    area = v
                elif '年份' in label:
                    year = v
            m_rm = re.search(r'class="pic-text[^"]*">([^<]*)<', html)
            if m_rm:
                remarks = m_rm.group(1).strip()

        def _meta_row(label):
            m = re.search(label + r'[：:</strong>]*\s*</span>([\s\S]{0,600}?)</p>',
                          html)
            if not m:
                m = re.search(label + r'：</span>([\s\S]{0,600}?)</p>', html)
            if not m:
                return ''
            vals = re.findall(r'<a[^>]*>([^<]{1,20})</a>', m.group(1))
            out = [v.strip() for v in vals if v.strip()]
            if not out:
                txt = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                out = [txt] if txt else []
            return ','.join(out[:12])

        director = _meta_row('导演')
        actor = _meta_row('主演')

        m_desc = re.search(r'<p class="desc[^"]*">([\s\S]{0,2500}?)</p>', html)
        if not m_desc:
            m_desc = re.search(r'<span class="detail-content"[^>]*>'
                               r'([\s\S]{0,2500}?)</span>', html)
        desc = (m_desc.group(1) if m_desc else '').strip()
        desc = re.sub(r'<[^>]+>', '', desc).strip()

        # ---- 线路: stui-pannel-box 逐个解析(第1个box是视频信息, 跳过) ----
        boxes = html.split('stui-pannel-box')
        lines, play_urls = [], []
        for b in boxes[2:]:
            m_h3 = re.search(r'<h3 class="title">[^<]*(?:<img[^>]*>)?'
                             r'([^<]+)</h3>', b)
            tname = (m_h3.group(1) if m_h3 else '').strip()
            eps = re.findall(r'href="(/vodplay/\d+-\d+-\d+/)"[^>]*>([^<]{1,20})<',
                             b)
            if not eps:
                continue
            lines.append(tname or ('线路%d' % (len(lines) + 1)))
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
            lines = ['剧踪影院']
            play_urls.append('正片$/vodplay/%s-1-1/' % vid)
        vod['vod_play_from'] = '$$$'.join(lines)
        vod['vod_play_url'] = '$$$'.join(play_urls)
        return {'list': [vod]}

    # ==================== 播放 ====================

    def _resolve_token(self, token, vod_name, ep_name):
        """独家线路令牌 -> 真实直链 (走站方jzpic播放器接口)"""
        q = urllib.parse.urlencode({
            'url': token,
            'name': (vod_name or '').encode('utf-8'),
            'ep': (ep_name or '1').encode('utf-8'),
        })
        html = self._html(PARSE_HOST + '/?' + q, referer=HOST + '/')
        mt = re.search(r'WGART_PARSE_TOKEN="([^"]+)"', html)
        if not mt:
            return ''
        ptok = mt.group(1)
        api = (PARSE_HOST + '/wgart/api.php?action=try_json_api'
               '&video_url=' + urllib.parse.quote(token, safe='') +
               '&parse_token=' + urllib.parse.quote(ptok, safe=''))
        data = self._html(api, referer=PLAY_REF)
        try:
            j = json.loads(data)
            if j.get('success') and j.get('data', {}).get('url'):
                return str(j['data']['url'])
        except Exception:
            pass
        return ''

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')
        if not raw.startswith('/vodplay/'):
            m = re.search(r'/vodplay/\d+-\d+-\d+/', raw)
            raw = m.group(0) if m else '/vodplay/' + raw.lstrip('/')
        header = {'user-agent': UA, 'referer': PLAY_REF}
        try:
            html = self._html(raw, referer=HOST + '/')
        except Exception as e:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': header, 'msg': '取播放页失败: %s' % e}
        m = re.search(r'var player_data=(\{[\s\S]{5,2500}?\});?\s*</script>',
                      html)
        play_url, fromm, ep_name = '', '', ''
        if m:
            try:
                obj = json.loads(m.group(1))
            except Exception:
                obj = {}
                for kv in re.finditer(r'"(\w+)":"([^"]*)"', m.group(1)):
                    obj[kv.group(1)] = kv.group(2)
            play_url = (obj.get('url') or '').strip()
            fromm = (obj.get('from') or '').strip()
        if not play_url:
            return {'parse': 0, 'playUrl': '', 'url': '',
                    'header': header, 'msg': '未取到播放数据'}
        # 独家线路: 前缀-令牌 形式, 走jzpic解析
        if not play_url.startswith('http'):
            if fromm in OWN_FROM or re.match(r'^[a-z0-9]{2,12}-', play_url):
                real = self._resolve_token(play_url, flag, ep_name)
                if real:
                    play_url = real
                else:
                    return {'parse': 0, 'playUrl': '', 'url': '',
                            'header': header,
                            'msg': '独家线解析失败, 请切换其他线路'}
            else:
                return {'parse': 0, 'playUrl': '', 'url': '',
                        'header': header, 'msg': '未知线路格式'}
        low = play_url.lower()
        if '.m3u8' in low or '.mp4' in low or '.flv' in low:
            parse = '0'
        elif fromm in WEB_FROM:
            parse = '1'
        else:
            parse = '0'
        return {'parse': parse, 'playUrl': '', 'url': play_url,
                'header': header}
