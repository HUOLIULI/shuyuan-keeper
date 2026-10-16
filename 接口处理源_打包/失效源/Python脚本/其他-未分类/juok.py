# -*- coding: utf-8 -*-
# 剧OK (juok3.top) TVBox dr_py 爬虫源
# ---------------------------------------------------------------------------
# 站点:  https://juok3.top  ("剧OK" - 360kan系影视聚合, Next.js + API)
#        内容 = 爱奇艺/腾讯等平台资源聚合, 站内解析成 m3u8 直链播放
#
# WAF:   无 JS 计算, 纯 cookie 累积挑战:
#        每个新路径先 403 2-3次, 每次响应 set-cookie(随机名), 带上全部
#        cookie 再请求即 200。spider 用持久 cookie 罐循环重试即可。
#
# 接口:
#   分类:  /api/filter?catId={1电影|2电视剧|3综艺|4动漫}&sort=ranklatest&page=N&size=24
#          → {movies:[{id(en_id),title,cover,cdncover,pubdate,actor,description,
#                      playlink_sites,playlinks}], total}
#   搜索:  /api/search?q={kw}&page=N
#          → {results:[{cat_id,en_id,titleTxt,cover,year,coverInfo:{txt}}]}
#   详情:  /api/detail?cat={catId}&id={en_id}
#          → data.{title,area,director,actor,description,cdncover,playlinks,
#                  allepidetail:{site:[{playlink_num,url}]},playlink_sites}
#   取流:  POST /api/player/resolve  (Content-Type: application/json,
#          X-Player-Request: 1)  body={"playUrl":"<平台页URL>"}
#          → {success,mode,url(m3u8,302跳真实流)}  无需登录/签名
#   封面:  qhimg/iqiyipic CDN 无防盗链直连
# ---------------------------------------------------------------------------
import sys
sys.path.append('..')
from base.spider import Spider

import re
import ssl
import json
import math
import html as html_lib
import http.cookiejar
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

HOST = 'https://juok3.top'

CATS = [
    ('1', '电影'),
    ('2', '电视剧'),
    ('3', '综艺'),
    ('4', '动漫'),
]

SITE_NAMES = {
    'qiyi': '爱奇艺', 'qq': '腾讯视频', 'mgtv': '芒果TV', 'youku': '优酷',
    'sohu': '搜狐', 'letv': '乐视', 'bilibili': '哔哩', 'm1905': '电影网',
    'pptv': 'PPTV', 'imgo': '芒果TV',
}


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class Spider(Spider):

    Host = HOST
    _opener = None

    # ==================== 生命周期 ====================

    def init(self, extend=""):
        # 每 Spider 实例一个持久 cookie 罐 (过 WAF cookie 累积挑战)
        cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))

    def getName(self):
        return '剧OK'

    def isVideoFormat(self, url):
        if not url:
            return False
        low = str(url).lower()
        return any(ext in low for ext in ('.m3u8', '.mp4', '.flv', '.mkv', '.ts'))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def liveContent(self, url):
        pass

    # ==================== 网络 ====================

    def _get(self, path, timeout=20, json_data=None):
        """GET/POST, 自动过 cookie 累积 WAF (403 循环)"""
        url = path if path.startswith('http') else self.Host + path
        last = b''
        for rnd in range(8):
            try:
                if json_data is not None:
                    body = json.dumps(json_data).encode('utf-8')
                    req = urllib.request.Request(url, data=body, method='POST')
                    req.add_header('Content-Type', 'application/json')
                    req.add_header('X-Player-Request', '1')
                else:
                    req = urllib.request.Request(url)
                req.add_header('user-agent', UA)
                resp = self._opener.open(req, timeout=timeout)
                code = resp.status
                data = resp.read()
            except urllib.error.HTTPError as e:
                code = e.code
                try:
                    data = e.read()
                except Exception:
                    data = b''
            except Exception:
                time.sleep(0.4)
                continue
            if code == 200:
                return data.decode('utf-8', 'ignore')
            last = data
            time.sleep(0.3)
        return last.decode('utf-8', 'ignore') if last else ''

    # ==================== 工具 ====================

    def _txt(self, s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', ' ', str(s))
        s = html_lib.unescape(s)
        return re.sub(r'\s+', ' ', s).strip()

    def _cover(self, raw):
        raw = (raw or '').strip()
        if not raw:
            return ''
        if raw.startswith('//'):
            raw = 'https:' + raw
        return raw

    def _site_name(self, site):
        return SITE_NAMES.get(site, '线路%s' % site)

    def _item_card(self, it, cat_id=''):
        en_id = str(it.get('en_id') or it.get('id') or '')
        cat = str(it.get('cat_id') or cat_id or '1')
        title = self._txt(it.get('titleTxt') or it.get('title') or en_id)
        title = re.sub(r'<[^>]+>', '', title)
        pic = self._cover(it.get('cover') or it.get('cdncover'))
        remarks = ''
        ci = it.get('coverInfo')
        if isinstance(ci, dict) and ci.get('txt'):
            remarks = ci['txt']
        elif it.get('total'):
            remarks = '全%s集' % it['total']
        elif it.get('pubdate'):
            remarks = str(it['pubdate'])[:4]
        return {'vod_id': '%s-%s' % (cat, en_id), 'vod_name': title,
                'vod_pic': pic, 'vod_remarks': remarks}

    # ==================== 六接口 ====================

    def homeContent(self, filter):
        result = {'class': [{'type_id': k, 'type_name': v} for k, v in CATS],
                  'list': []}
        raw = self._get('/api/filter?catId=1&sort=ranklatest&page=1&size=24')
        if raw:
            try:
                d = json.loads(raw)
                result['list'] = [self._item_card(x, '1')
                                  for x in (d.get('movies') or [])][:24]
            except Exception:
                pass
        return result

    def homeVideoContent(self):
        raw = self._get('/api/filter?catId=1&sort=ranklatest&page=1&size=24')
        vids = []
        if raw:
            try:
                d = json.loads(raw)
                vids = [self._item_card(x, '1') for x in (d.get('movies') or [])]
            except Exception:
                pass
        return {'list': vids}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        limit = 24
        tid = str(tid)
        path = ('/api/filter?catId=%s&sort=ranklatest&page=%d&size=%d'
                % (tid, page, limit))
        raw = self._get(path)
        vids = []
        total = 0
        if raw:
            try:
                d = json.loads(raw)
                total = int(d.get('total') or 0)
                vids = [self._item_card(x, tid) for x in (d.get('movies') or [])]
            except Exception:
                pass
        pagecount = max(1, math.ceil(total / limit)) if total else (page + 1 if vids else page)
        return {'list': vids, 'page': page, 'pagecount': pagecount,
                'limit': limit, 'total': total}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, '1')

    def searchContentPage(self, key, quick, pg):
        page = int(pg) if str(pg).isdigit() else 1
        q = urllib.parse.quote(str(key))
        raw = self._get('/api/search?q=%s&page=%d' % (q, page))
        vids = []
        if raw:
            try:
                d = json.loads(raw)
                vids = [self._item_card(x) for x in (d.get('results') or [])]
            except Exception:
                pass
        pagecount = page + 1 if vids else page
        return {'list': vids, 'page': page, 'pagecount': pagecount,
                'limit': 20, 'total': len(vids)}

    def detailContent(self, ids):
        vod_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        cat, en_id = '1', vod_id
        if '-' in vod_id:
            a, b = vod_id.split('-', 1)
            if a.isdigit():
                cat, en_id = a, b
            else:
                en_id = vod_id
        raw = self._get('/api/detail?cat=%s&id=%s' % (cat, urllib.parse.quote(en_id)))
        vod = {
            'vod_id': vod_id, 'vod_name': '', 'vod_pic': '', 'vod_remarks': '',
            'vod_year': '', 'vod_area': '', 'vod_actor': '', 'vod_director': '',
            'type_name': '', 'vod_content': '',
            'vod_play_from': '', 'vod_play_url': ''
        }
        if not raw:
            vod['vod_name'] = en_id
            return {'list': [vod]}
        try:
            d = json.loads(raw).get('data') or {}
        except Exception:
            d = {}
        vod['vod_name'] = self._txt(d.get('title') or en_id)
        vod['vod_pic'] = self._cover(d.get('cdncover') or d.get('cover'))
        area = d.get('area')
        if isinstance(area, list) and area:
            vod['vod_area'] = self._txt(area[0])
        elif isinstance(area, str):
            vod['vod_area'] = self._txt(area)
        pd = str(d.get('pubdate') or '')[:4]
        if pd.isdigit():
            vod['vod_year'] = pd
        directors = d.get('director') or []
        actors = d.get('actor') or []
        if isinstance(directors, list):
            vod['vod_director'] = '/'.join(directors[:6])
        if isinstance(actors, list):
            vod['vod_actor'] = '/'.join(actors[:12])
        mc = d.get('moviecategory')
        if isinstance(mc, list) and mc:
            vod['type_name'] = self._txt(' '.join(str(x) for x in mc))
        vod['vod_content'] = self._txt(d.get('description'))
        upinfo = d.get('upinfo') or d.get('total')
        if upinfo:
            vod['vod_remarks'] = '更新至%s集' % upinfo if str(upinfo).isdigit() and str(cat) != '1' else str(upinfo)
        # 播放源: playlink_sites + allepidetail (剧集) / playlinks (电影)
        sites = d.get('playlink_sites') or list((d.get('playlinks') or {}).keys())
        allepi = d.get('allepidetail') or {}
        playlinks = d.get('playlinks') or {}
        # 电影: playlinksdetail[site].default_url; 剧集: allepidetail[site][]
        pld = d.get('playlinksdetail') or {}
        lines, play_urls = [], []
        for site in sites:
            if not site:
                continue
            name = self._site_name(site)
            eps = []
            if site in allepi and isinstance(allepi[site], list):
                for ep in allepi[site]:
                    num = str(ep.get('playlink_num') or '')
                    u = ep.get('url') or ''
                    if u:
                        try:
                            nm = '第%02d集' % int(num) if num.isdigit() else ('第%s集' % num or '正片')
                        except Exception:
                            nm = '正片'
                        eps.append('%s$%s' % (nm, u))
            if not eps and site in pld and isinstance(pld[site], dict):
                u = pld[site].get('default_url') or pld[site].get('pageurl') or ''
                if u:
                    eps.append('正片$%s' % u)
            if not eps and site in playlinks and playlinks[site]:
                eps.append('正片$%s' % playlinks[site])
            if not eps:
                continue
            lines.append(name)
            play_urls.append('#'.join(eps))
        if not lines:
            lines, play_urls = ['默认线路'], ['正片$0']
        vod['vod_play_from'] = '$$$'.join(lines)
        vod['vod_play_url'] = '$$$'.join(play_urls)
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        headers = {'User-Agent': UA, 'Referer': self.Host + '/'}
        vid = str(id)
        if not vid.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': headers,
                    'msg': '无效播放地址'}
        raw = self._get('/api/player/resolve', json_data={'playUrl': vid})
        url = ''
        if raw:
            try:
                d = json.loads(raw)
                if d.get('success') and d.get('url'):
                    url = d['url']
                elif d.get('url'):
                    url = d['url']
            except Exception:
                pass
        if not url:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': headers,
                    'msg': '解析失败，请稍后重试或换线路'}
        return {'parse': 0, 'playUrl': '', 'url': url, 'header': headers}

    def localProxy(self, param):
        return [404, 'text/plain', 'not found']
