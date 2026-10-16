# coding=utf-8
"""
1905影视 —— TVBox / FongMi / OK影视 / WebHomeTV / PeekPro影视 Python Spider
源站: https://www.1905dsj.com
"""

import sys
import re
import json
import base64
from urllib.parse import quote, unquote, urljoin

import requests

sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


class Spider(_BaseSpider):

    def getName(self):
        return "1905影视"

    def init(self, extend=""):
        self.host = "https://www.1905dsj.com"
        self.timeout = 20
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self._classes = [
            {"type_id": "dianying",  "type_name": "电影"},
            {"type_id": "dianshiju", "type_name": "电视剧"},
            {"type_id": "zongyi",    "type_name": "综艺"},
            {"type_id": "dongman",   "type_name": "动漫"},
            {"type_id": "duanju",    "type_name": "短剧"},
        ]

        self._areas = [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"},
            {"n": "香港", "v": "香港"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "其他", "v": "其他"},
        ]

        self._years = [{"n": "全部", "v": ""}] + [
            {"n": str(y), "v": str(y)} for y in range(2026, 2014, -1)
        ]

        self._sorts = [
            {"n": "时间", "v": ""},
            {"n": "人气", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]

    # ------------------------------------------------------------ 请求工具
    def _get(self, url):
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""

    def _abs(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.host + url
        return urljoin(self.host + "/", url)

    @staticmethod
    def _strip_tags(s):
        return re.sub(r"<[^>]+>", "", s or "").strip()

    # ------------------------------------------------------------ 列表解析
    def _parse_list(self, html):
        items = []
        if not html:
            return items

        seen = set()

        # 匹配每个 <a class="...hl-item-thumb...">...</a> 卡片
        pattern = re.compile(
            r'<a\b[^>]*\bclass="[^"]*hl-item-thumb[^"]*"[^>]*>[\s\S]*?</a>',
            re.S
        )

        for m in pattern.finditer(html):
            card = m.group(0)

            # href: /vod/detail/id/{id}.html
            hm = re.search(r'\bhref="(/vod/detail/id/(\d+)\.html)"', card)
            if not hm:
                continue
            href = hm.group(1)
            vid = hm.group(2)

            # 标题：优先 title 属性
            title = ""
            tm = re.search(r'\btitle="([^"]*)"', card)
            if tm:
                title = tm.group(1).strip()
            if not title:
                tm = re.search(r'<img[^>]+alt="([^"]*)"', card)
                if tm:
                    title = tm.group(1).strip()
            if not title:
                continue

            # 封面：优先 data-original
            pic = ""
            pm = re.search(r'\bdata-original="([^"]+)"', card)
            if not pm:
                pm = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"', card)
            if pm and pm.group(1) and not pm.group(1).startswith("data:"):
                pic = self._abs(pm.group(1))

            # 备注：<span class="hl-lc-1 remarks">xx</span>
            remark = ""
            nm = re.search(r'class="[^"]*remarks[^"]*"[^>]*>([^<]*)<', card)
            if nm:
                remark = nm.group(1).strip()

            if vid in seen:
                continue
            seen.add(vid)

            items.append({
                "vod_id":      self._abs(href),
                "vod_name":    title,
                "vod_pic":     pic,
                "vod_remarks": remark,
            })

        return items

    # ------------------------------------------------------------ 首页
    def homeContent(self, filter):
        filters = {}
        for c in self._classes:
            filters[c["type_id"]] = [
                {"key": "area", "name": "地区", "value": self._areas},
                {"key": "year", "name": "年份", "value": self._years},
                {"key": "sort", "name": "排序", "value": self._sorts},
            ]
        return {"class": self._classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._parse_list(html)}

    # ------------------------------------------------------------ 分类
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1

        area = ""
        year = ""
        sort = ""
        if isinstance(extend, dict):
            area = extend.get("area", "") or ""
            year = extend.get("year", "") or ""
            sort = extend.get("sort", "") or ""

        parts = []
        if area:
            parts.append("area/" + quote(area))
        if year:
            parts.append("year/" + str(year))
        if sort:
            parts.append("by/" + str(sort))
        parts.append("id/" + tid)
        if page > 1:
            parts.append("page/{}".format(page))

        url = self.host + "/vod/show/" + "/".join(parts) + ".html"
        html = self._get(url)
        vlist = self._parse_list(html)

        return {
            "list":      vlist,
            "page":      page,
            "pagecount": page + 1 if vlist else page,
            "limit":     len(vlist) if vlist else 20,
            "total":     999999,
        }

    # ------------------------------------------------------------ 搜索
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1

        url = "{}/vod/search.html?wd={}".format(self.host, quote(key))
        if page > 1:
            url += "&page={}".format(page)

        html = self._get(url)
        vlist = self._parse_list(html)

        return {
            "list":      vlist,
            "page":      page,
            "pagecount": page + 1 if vlist else page,
            "limit":     len(vlist) if vlist else 20,
            "total":     999999,
        }

    # ------------------------------------------------------------ 详情
    def _parse_play_lines(self, html):
        """解析线路名 + 选集"""
        # 1) 线路名：<a class="hl-tabs-btn" alt="线路名">
        line_names = {}
        idx = 1
        for m in re.finditer(
                r'<a[^>]*class="[^"]*hl-tabs-btn[^"]*"[^>]*alt="([^"]+)"', html):
            line_names[idx] = m.group(1).strip()
            idx += 1

        # 2) 选集：/vod/play/id/{vid}/sid/{sid}/nid/{nid}.html
        play_links = {}
        for m in re.finditer(
                r'<a[^>]*href="(/vod/play/id/\d+/sid/(\d+)/nid/(\d+)\.html)"[^>]*>([^<]*)</a>',
                html, re.S):
            href = m.group(1)
            sid = int(m.group(2))
            nid = int(m.group(3))
            name = m.group(4).strip()
            play_links.setdefault(sid, {})[nid] = {
                "name": name,
                "href": href,
            }

        # 3) 组装
        lines = []
        for sid in sorted(play_links.keys()):
            eps = []
            for nid in sorted(play_links[sid].keys()):
                ep = play_links[sid][nid]
                eps.append({
                    "name": ep["name"] or "第{}集".format(nid),
                    "url":  self._abs(ep["href"]),
                })
            if eps:
                name = line_names.get(sid, "线路{}".format(sid))
                lines.append({"name": name, "eps": eps})
        return lines

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        html = self._get(vod_id)
        if not html:
            return {"list": []}

        # ---------------- 标题 ----------------
        title = ""
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            title = self._strip_tags(m.group(1))
        if not title:
            m = re.search(r'<span[^>]*class="[^"]*hl-dc-head[^"]*"[^>]*>([^<]+)<', html)
            if m:
                title = m.group(1).strip()
        if not title:
            m = re.search(r'og:title"\s*content="([^"]+)"', html)
            if m:
                title = m.group(1).split("-")[0].split("|")[0].strip()

        # ---------------- 封面 ----------------
        cover = ""
        m = re.search(r'hl-dc-pic[\s\S]{0,400}?data-original="([^"]+)"', html)
        if not m:
            m = re.search(
                r'<span[^>]*class="[^"]*hl-item-thumb[^"]*"[^>]*data-original="([^"]+)"',
                html)
        if not m:
            m = re.search(r'og:image"\s*content="([^"]+)"', html)
        if m:
            cover = self._abs(m.group(1))

        # ---------------- 简介 ----------------
        intro = ""
        m = re.search(r'hl-content-text[^>]*><em>([\s\S]*?)</em>', html)
        if m:
            intro = self._strip_tags(m.group(1))
        if not intro:
            m = re.search(r'name="description"\s*content="([^"]*)"', html)
            if m:
                intro = m.group(1).strip()

        # ---------------- 元信息 ----------------
        clean_html = re.sub(r'<script[\s\S]*?</script>', '', html)
        actor_info = ""
        dir_info = ""
        note_info = ""
        year_info = ""
        area_info = ""
        type_info = ""
        for li in re.findall(r'<li[^>]*>[\s\S]*?</li>', clean_html):
            txt = self._strip_tags(li)
            txt = re.sub(r"\s+", " ", txt).strip()
            if not txt:
                continue
            if "主演" in txt:
                actor_info = re.sub(r"^.*主演[：:]\s*", "", txt).strip()
            elif "导演" in txt:
                dir_info = re.sub(r"^.*导演[：:]\s*", "", txt).strip()
            elif "更新" in txt or "状态" in txt:
                note_info = re.sub(r"^.*[：:]\s*", "", txt).strip()
            elif "年份" in txt:
                year_info = re.sub(r"^.*年份[：:]\s*", "", txt).strip()
            elif "地区" in txt:
                area_info = re.sub(r"^.*地区[：:]\s*", "", txt).strip()
            elif "类型" in txt:
                type_info = re.sub(r"^.*类型[：:]\s*", "", txt).strip()

        # 兜底：从 player_aaaa 的 vod_data 中取
        if not actor_info:
            m = re.search(r'"vod_actor"\s*:\s*"([^"]*)"', html)
            if m:
                actor_info = m.group(1)
        if not dir_info:
            m = re.search(r'"vod_director"\s*:\s*"([^"]*)"', html)
            if m:
                dir_info = m.group(1)
        if not type_info:
            m = re.search(r'"vod_class"\s*:\s*"([^"]*)"', html)
            if m:
                type_info = m.group(1)

        # ---------------- 线路 / 选集 ----------------
        lines = self._parse_play_lines(html)

        play_from = []
        play_url = []
        circled = "①②③④⑤⑥⑦⑧⑨⑩"
        for i, line in enumerate(lines):
            if i < len(circled):
                new_name = "线路" + circled[i]
            else:
                new_name = "线路" + str(i + 1)
            play_from.append(new_name)
            play_url.append("#".join(
                "{}${}".format(ep["name"], ep["url"]) for ep in line["eps"]
            ))

        vod = {
            "vod_id":        vod_id,
            "vod_name":      title,
            "vod_pic":       cover,
            "vod_content":   intro,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }
        if dir_info:
            vod["vod_director"] = dir_info
        if actor_info:
            vod["vod_actor"] = actor_info
        if year_info:
            vod["vod_year"] = year_info
        if area_info:
            vod["vod_area"] = area_info
        if type_info:
            vod["vod_type"] = type_info
        if note_info:
            vod["vod_remarks"] = note_info

        return {"list": [vod]}

    # ------------------------------------------------------------ 播放
    @staticmethod
    def _is_media_url(url):
        return bool(re.search(
            r"\.(m3u8|mp4|flv|mkv|ts|avi|m4a|mp3)(\?|#|$)", url or "", re.I))

    def _extract_from_player_json(self, html):
        """从播放页的 player_aaaa 变量里提取真实地址"""
        url = ""

        m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', html)
        raw = None
        if m:
            raw = m.group(1)
        else:
            m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*;', html)
            if m:
                raw = m.group(1)

        if raw:
            try:
                data = json.loads(raw)
                url = data.get("url", "") or ""
                enc = data.get("encrypt", 0) or 0
                try:
                    enc = int(enc)
                except Exception:
                    enc = 0

                if enc == 1 and url:
                    try:
                        url = unquote(url)
                    except Exception:
                        pass
                elif enc == 2 and url:
                    try:
                        url = base64.b64decode(url).decode("utf-8", "ignore")
                        url = unquote(url)
                    except Exception:
                        pass
            except Exception:
                pass

        if url:
            url = url.replace("\\/", "/").replace("\\u002f", "/")

        # 兜底：直接在页面里找 m3u8 / mp4
        if not url:
            m = re.search(r'(https?://[^\s"\'\\<>]+?\.m3u8[^\s"\'\\<>]*)', html, re.I)
            if not m:
                m = re.search(r'(https?://[^\s"\'\\<>]+?\.mp4[^\s"\'\\<>]*)', html, re.I)
            if m:
                url = m.group(1).replace("\\/", "/")

        return url

    def playerContent(self, flag, id, vipFlags):
        url = id

        if not self._is_media_url(url):
            html = self._get(url)
            real = self._extract_from_player_json(html)
            if real:
                url = real

        header = {
            "User-Agent": self.headers["User-Agent"],
            "Referer":    self.host + "/",
        }
        return {
            "parse":   0,
            "playUrl": "",
            "url":     url,
            "header":  json.dumps(header),
        }

    # ------------------------------------------------------------ 其它
    def isVideoFormat(self, url):
        return self._is_media_url(url)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass