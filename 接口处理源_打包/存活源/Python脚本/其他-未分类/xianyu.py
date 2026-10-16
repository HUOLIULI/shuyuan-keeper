# -*- coding: utf-8 -*-
"""
TVBox PySpider —— 咸鱼影视 (www.jxw888.cn)
适配: TVBox / 影视TV / CatVodTV 系的 csp_PySpider / PySpider / py
纯标准库实现(urllib / re, 盒子上不用装任何第三方库)。

数据来源:
  首页推荐   GET /
  分类列表   GET /list/{tid}.html          第 1 页
             GET /list/{tid}-{pg}.html     第 N 页   (每页 21 条)
  年份筛选   上面地址后挂 ?y=2026
  搜索       GET /?wd={关键词}&pg={页}      (每页 50 条)
  播放页     GET /detail/{id}-{集}-{线路}.html
             -> 页面里内嵌 const VOD = {...}
                VOD.lines[] = [{"name":"ffm3u8","eps":[{"t":"第01集","u":"https://.../index.m3u8"}, ...]}, ...]
                一次就能拿到所有线路 + 每一集的 m3u8 直链。
"""

import re
import json
import requests
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "咸鱼影视"

    def init(self, extend=""):
        super().init(extend)
        # ========== 只需修改这里 ==========
        self.site_url = "https://www.jxw888.cn"
        # =================================
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G975F) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.site_url,
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        self.sess = requests.Session()
        self.page_size = 21
        self.search_size = 50
        self.max_episodes = 800
        self.timeout = 20

        # 线路名美化
        self.line_names = {
            "ffm3u8": "非凡", "dyttm3u8": "高清", "lzm3u8": "量子",
            "jsm3u8": "极速", "wsym3u8": "快捷", "wsm3u8": "快捷",
            "bfzym3u8": "暴风", "tkm3u8": "天空", "kdm3u8": "酷点",
            "wjm3u8": "无尽", "hdm3u8": "高清2",
        }
        self.line_order = ["dyttm3u8", "wsym3u8", "wsm3u8", "ffm3u8",
                           "jsm3u8", "lzm3u8"]

        self.cats = [
            ("1", "电影片"), ("2", "连续剧"), ("3", "综艺片"), ("4", "动漫片"),
            ("35", "电影解说"), ("36", "体育"), ("46", "短剧"), ("6", "动作片"),
            ("7", "喜剧片"), ("8", "爱情片"), ("9", "科幻片"), ("10", "恐怖片"),
            ("11", "剧情片"), ("12", "战争片"), ("20", "记录片"), ("47", "动画电影"),
        ]
        self.years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020",
                      "2019", "2018", "2017", "2016", "2015", "2010", "2005", "2000"]

    def fetch(self, url, timeout=None, referer=None):
        try:
            h = dict(self.headers)
            if referer:
                h["Referer"] = referer
            return self.sess.get(url, headers=h, timeout=timeout or self.timeout,
                                 verify=False)
        except Exception:
            return None

    def _abs(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.site_url + u
        return self.site_url + "/" + u

    def _esc(self, s):
        return (s or "").replace("#", " ").replace("$", " ").strip()

    # ---------- 卡片解析 ----------
    def _cards(self, html):
        out = []
        seen = set()
        for m in re.finditer(
                r'<a class="card"[^>]*href="(/detail/(\d+)\.html)"[^>]*>(.*?)</a>',
                html or "", re.S):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            inner = m.group(3)

            pic, alt = "", ""
            mi = re.search(r'<img[^>]+src="([^"]+)"[^>]*?(?:alt="([^"]*)")?',
                           inner, re.S)
            if mi:
                pic = self._abs(mi.group(1))
                alt = (mi.group(2) or "").strip()

            nm = re.search(r'<div class="nm">([^<]{0,120})</div>', inner)
            name = (nm.group(1).strip() if nm else "") or alt
            if not name:
                continue

            rk = re.search(r'<b>([^<]{0,40})</b>', inner)
            sub = re.search(r'<div class="rm">([^<]{0,60})</div>', inner)

            year, cls = "", ""
            if sub:
                parts = [p.strip() for p in sub.group(1).split("·")]
                if parts:
                    year = parts[0]
                if len(parts) > 1:
                    cls = parts[1]

            v = {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": rk.group(1).strip() if rk else "",
            }
            if year:
                v["vod_year"] = year
            if cls:
                v["vod_class"] = cls
            out.append(v)
        return out

    def _page_count(self, html, pg, got):
        m = re.search(r'(\d+)\s*/\s*(\d+)\s*</a>', html or "")
        if m:
            total_pg = int(m.group(2)) if m.group(2).isdigit() else 0
            if total_pg > 0:
                return total_pg
        return pg + 1 if got >= self.page_size else pg

    # ---------- 从播放页抠 const VOD = {...} ----------
    def _extract_vod(self, html):
        i = (html or "").find("const VOD")
        if i < 0:
            return None
        i += len("const VOD")
        while i < len(html) and html[i] in " \t\r\n=":
            i += 1
        if i >= len(html) or html[i] != "{":
            return None
        depth, instr, esc, start = 0, False, False, i
        while i < len(html):
            c = html[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(html[start:i + 1])
                        except Exception:
                            return None
            i += 1
        return None

    def _sort_lines(self, lines):
        ordered, rest = [], []
        for i, ln in enumerate(lines or []):
            if not isinstance(ln, dict):
                continue
            code = (ln.get("name") or "").strip().lower()
            if code in self.line_order:
                ordered.append((self.line_order.index(code), i, ln))
            else:
                rest.append((i, ln))
        ordered.sort(key=lambda x: (x[0], x[1]))
        return [x[2] for x in ordered] + [x[1] for x in rest]

    # ========== 首页分类 ==========
    def homeContent(self, filter):
        cate_list = [{"type_name": n, "type_id": t} for t, n in self.cats]
        filters = {}
        if filter:
            for t, _n in self.cats:
                filters[t] = [{
                    "key": "y", "name": "年份",
                    "value": [{"n": "全部", "v": ""}] +
                             [{"n": x, "v": x} for x in self.years],
                }]
        return {"class": cate_list, "filters": filters}

    def homeVideoContent(self):
        res = self.fetch(self.site_url + "/")
        out = []
        if res and res.ok:
            out = self._cards(res.text)
        return {"list": out}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        tid = re.sub(r"[^0-9]", "", str(tid or "1")) or "1"

        url = f"{self.site_url}/list/{tid}.html" if pg <= 1 \
            else f"{self.site_url}/list/{tid}-{pg}.html"
        y = (extend or {}).get("y") or (extend or {}).get("year") or ""
        if y:
            url += "?y=" + requests.utils.quote(str(y), safe="")

        video_list = []
        pagecount = pg
        res = self.fetch(url)
        if res and res.ok:
            html = res.text
            video_list = self._cards(html)
            pagecount = self._page_count(html, pg, len(video_list))

        total = pagecount * self.page_size if pagecount > pg or len(video_list) >= self.page_size else 0
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": total,
        }

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = f"{self.site_url}/?wd={requests.utils.quote(key or '', safe='')}"
        if pg > 1:
            url += f"&pg={pg}"

        video_list = []
        res = self.fetch(url)
        if res and res.ok:
            video_list = self._cards(res.text)

        return {
            "list": video_list,
            "page": pg,
            "pagecount": pg + 1 if len(video_list) >= self.search_size else pg,
            "limit": self.search_size,
            "total": len(video_list),
        }

    # ========== 详情页 ==========
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0]).strip()
        if "$" in vid:
            vid = vid.split("$")[-1]
        vid = re.sub(r"[^0-9]", "", vid)
        if not vid:
            return {"list": []}

        # 播放页内嵌 VOD JSON: 一次拿到所有线路 + 每一集直链
        d = None
        for u in (f"/detail/{vid}-1-0.html",
                  f"/detail/{vid}-1-1.html",
                  f"/detail/{vid}-1.html"):
            res = self.fetch(self.site_url + u,
                             referer=f"{self.site_url}/detail/{vid}.html")
            if res and res.ok:
                d = self._extract_vod(res.text)
                if d and d.get("lines"):
                    break
            d = None

        lines = self._sort_lines((d or {}).get("lines") or [])

        vod = {
            "vod_id": vid,
            "vod_name": (d or {}).get("name") or "",
            "vod_pic": self._abs((d or {}).get("pic") or ""),
            "vod_remarks": (d or {}).get("remarks") or "",
            "vod_year": str((d or {}).get("year") or ""),
            "vod_area": (d or {}).get("area") or "",
            "vod_actor": (d or {}).get("actor") or "",
            "vod_director": (d or {}).get("director") or "",
            "vod_content": (d or {}).get("content") or "",
        }

        play_from_list, play_url_list = [], []

        for ln in lines:
            if not isinstance(ln, dict):
                continue
            eps = ln.get("eps") or []
            if not eps:
                continue
            items, seen = [], set()
            for e in eps[:self.max_episodes]:
                if not isinstance(e, dict):
                    continue
                u = (e.get("u") or "").strip()
                if not u.startswith("http") or u in seen:
                    continue
                seen.add(u)
                t = self._esc(e.get("t")) or f"第{len(items) + 1}集"
                items.append(f"{t}${u}")
            if not items:
                continue
            code = (ln.get("name") or "").strip()
            play_from_list.append(self.line_names.get(code.lower(), code or "线路"))
            play_url_list.append("#".join(items))

        # 兜底: 未抠到直链, 用详情页拿到选集页面地址
        if not play_from_list:
            res = self.fetch(f"{self.site_url}/detail/{vid}.html")
            if res and res.ok:
                html = res.text
                if not vod["vod_name"]:
                    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
                    if m:
                        vod["vod_name"] = re.sub(r"<[^>]+>", "",
                                                 m.group(1)).strip()
                if not vod["vod_pic"]:
                    m = re.search(r'property="og:image" content="([^"]+)"', html)
                    if m:
                        vod["vod_pic"] = self._abs(m.group(1))
                eps = []
                for m in re.finditer(
                        r'href="(/detail/%s-(\d+)-(\d+)\.html)"' % vid, html):
                    eps.append(f"第{m.group(2)}集${self.site_url}{m.group(1)}")
                if eps:
                    play_from_list = ["站点播放页"]
                    play_url_list = ["#".join(eps[:self.max_episodes])]

        if not play_from_list:
            return {"list": []}

        vod["vod_play_from"] = "$$$".join(play_from_list)
        vod["vod_play_url"] = "$$$".join(play_url_list)
        return {"list": [vod]}

    # ========== 播放解析 ==========
    def playerContent(self, flag, pid, vipFlags):
        raw = (pid or "").strip()
        if "$" in raw and raw.count("$") == 1 \
                and not raw.split("$")[0].startswith("http"):
            raw = raw.split("$")[-1]

        header = {"User-Agent": self.headers["User-Agent"],
                  "Referer": self.site_url + "/"}

        # 详情页给的已经是 m3u8 直链, 直接播
        if raw.startswith("http"):
            return {"parse": 0, "playUrl": "", "url": raw, "header": header}

        # 兜底: 交给壳的 webview
        return {"parse": 1, "playUrl": "", "url": self._abs(raw),
                "header": header}