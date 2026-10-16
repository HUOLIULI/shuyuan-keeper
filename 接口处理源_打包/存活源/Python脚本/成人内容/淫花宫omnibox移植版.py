#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @name 淫花宫
# @author 梦
# @description 影视站：https://breplc.yhg5.help/ ，四壳(苹果CMS)结构，支持首页、分类、搜索、详情与 m3u8 播放提取（OmniBox版）
# @version 1.0.0

import base64
import html
import json
import os
import re
from urllib.parse import quote, urlencode, urlparse

from spider_runner import OmniBox, run


def split_config_list(value: str):
    return [item.strip() for item in str(value or "").replace(",", ";").split(";") if item.strip()]


# ==================== 配置区域开始 ====================
# 站点基础地址，可用环境变量覆盖。
BASE_URL = str(os.environ.get("YHG_BASE_URL") or "https://breplc.yhg5.help").rstrip("/")
# 站点请求默认 User-Agent。
UA = str(os.environ.get("YHG_UA") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
# 站点语言路径前缀，首页是 /cn/home/web/ 时分类通常也在该前缀下。
LANG_PREFIX = str(os.environ.get("YHG_LANG_PREFIX") or "/cn").rstrip("/")
# 首页路径候选，按顺序尝试直到解析出内容。
HOME_PATH_TEMPLATES = split_config_list(os.environ.get("YHG_HOME_PATHS", "/cn/home/web/;/index.html;/"))
# 分类路径候选模板，按顺序尝试；命中的模板会被缓存复用（需通过分类校验）。
CATEGORY_PATH_TEMPLATES = split_config_list(os.environ.get(
    "YHG_CATEGORY_PATHS",
    "/vodtype/{tid}---page/{pg}.html;/vodtype/{tid}/page/{pg}.html;/vodtype/{tid}.html;/vodshow/{tid}---{pg}---.html;/vodlist/{tid}---{pg}---.html;/show/{tid}/page/{pg}.html",
))
# 搜索路径候选模板。
SEARCH_PATH_TEMPLATES = split_config_list(os.environ.get(
    "YHG_SEARCH_PATHS",
    "/s/{kw}.html;/index.php/vod/search/search/wd/{kw}/page/{pg}.html;/vodsearch/{kw}/page/{pg}.html",
))
# 搜索结果为空时是否尝试苹果CMS 的 POST 搜索。
YHG_SEARCH_POST_FALLBACK = str(os.environ.get("YHG_SEARCH_POST_FALLBACK", "true")).lower() == "true"
# 请求重试次数。
YHG_RETRY = max(0, int(os.environ.get("YHG_RETRY", "2") or 2))
# 分类每页期望条数，用于推断是否还有下一页。
YHG_PAGE_SIZE = max(1, int(os.environ.get("YHG_PAGE_SIZE", "30") or 30))
# 播放页缓存 TTL（秒），减少重复解析。
PLAY_CACHE_EX_SECONDS = max(60, int(os.environ.get("YHG_PLAY_CACHE_EX_SECONDS", "600") or 600))
# 列表接口单页最大返回条数。
YHG_LIST_LIMIT = max(1, int(os.environ.get("YHG_LIST_LIMIT", "200") or 200))
# 分类映射配置。
CATEGORY_MAP = {
    "20": "熟母少妇",
    "21": "网红直播",
    "22": "自拍偷拍",
    "23": "强奸乱伦",
    "24": "高清国产",
    "25": "韩国专区",
    "26": "日本有码",
    "27": "日本无码",
    "28": "欧美情色",
    "29": "动漫卡通",
    "30": "三级伦理",
}
# 分类名称可被环境变量覆盖（分号分隔，形如 "20=电影;21=电视剧"）。
CATEGORY_NAME_OVERRIDES = {
    item.split("=")[0].strip(): item.split("=")[1].strip()
    for item in split_config_list(os.environ.get("YHG_CATEGORIES", ""))
    if "=" in item
}
# 详情页字段标签。
FIELD_LABELS = {
    "导演": "vod_director",
    "主演": "vod_actor",
    "编剧": "vod_writer",
    "地区": "vod_area",
    "制片国家/地区": "vod_area",
    "语言": "vod_lang",
    "上映日期": "vod_pubdate",
    "年份": "vod_year",
    "片长": "vod_remarks",
    "更新日期": "update_date",
    "又名": "vod_subtitle",
    "IMDb": "vod_imdb",
    "类型": "type_name",
}
# 排序过滤映射（苹果CMS by 参数）。
SORT_FILTER_MAP = {
    "综合": "",
    "最新": "time",
    "最热": "hit",
    "评分": "score",
    "评论": "comment",
}
# ==================== 配置区域结束 ====================

DETAIL_PATH_RE = re.compile(r"^(\d+)\.html$")
PLAY_PATH_RE = re.compile(r"/(?:vodplay|vplay|play)/(\d+)-(\d+)-(\d+)\.html", re.I)
PLAY_QUERY_RE = re.compile(r"[?&]vid=(\d+).*?[?&]sid=(\d+).*?[?&]nid=(\d+)", re.I)
# 软 404 标记，用于识别「返回 200 但其实是错误页」的分类/搜索结果。
BAD_PAGE_MARKERS = ("404", "页面不存在", "页面已删除", "已删除", "找不到", "not found", "访问出错")
# 首页 vid 指纹，用于识别「URL 拼错后被重定向到首页」的情况。
HOME_VIDS: frozenset = None
# 已通过校验的分类路径模板缓存：type_id -> template。
CACHE_TEMPLATE_MAP: dict = {}


def abs_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url.lstrip('./')}"


def clean_html(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"<(br|/p|/div|/li)\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("\xa0", " ").replace("\u3000", " ")
    return re.sub(r"\s+", " ", value).strip()


def clean_multiline_html(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(p|div|li)>\s*", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("\xa0", " ").replace("\u3000", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return re.sub(r"\n\s*\n+", "\n", value).strip()


def uniq(seq):
    out = []
    seen = set()
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def is_detail_url(url: str) -> str:
    """返回详情页的 vid，非详情链接返回空串。"""
    path = (urlparse(abs_url(url)).path or "").strip("/")
    m = DETAIL_PATH_RE.match(path)
    return m.group(1) if m else ""


async def log(level: str, message: str):
    try:
        await OmniBox.log(level, message)
    except Exception:
        pass


def decode_body(body) -> str:
    if not isinstance(body, (bytes, bytearray)):
        return str(body or "")
    raw = bytes(body)
    m = re.search(rb'charset\s*=\s*["\']?\s*([a-zA-Z0-9_\-]+)', raw[:4096], re.I)
    enc = m.group(1).decode("ascii", "ignore").lower() if m else ""
    candidates = [enc] if enc else []
    candidates += ["utf-8", "gb18030", "gbk"]
    for cand in candidates:
        if not cand:
            continue
        try:
            return raw.decode(cand)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "ignore")


async def request_text(url: str, referer: str = None, method: str = "GET", data: dict = None) -> str:
    body = urlencode(data, encoding="utf-8") if data else None
    headers = {
        "User-Agent": UA,
        "Referer": referer or f"{BASE_URL}/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    if body:
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    last_err = None
    for attempt in range(YHG_RETRY + 1):
        try:
            res = await OmniBox.request(url, {
                "method": method,
                "headers": headers,
                "body": body,
            })
            status = int(res.get("statusCode") or 0)
            if status != 200:
                raise RuntimeError(f"HTTP {status} @ {url}")
            return decode_body(res.get("body", ""))
        except Exception as e:
            last_err = e
            await log("warn", f"[yhg][request] attempt={attempt + 1} url={url} err={e}")
    raise RuntimeError(f"request failed: {last_err}")


async def get_cached_json(key: str):
    try:
        value = await OmniBox.getCache(key)
        if not value:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return value
    except Exception:
        return None


async def set_cached_json(key: str, value, ex_seconds: int = PLAY_CACHE_EX_SECONDS):
    try:
        await OmniBox.setCache(key, json.dumps(value, ensure_ascii=False), ex_seconds)
    except Exception:
        pass


def search_tag_attr(tag: str, *names) -> str:
    for name in names:
        m = re.search(rf'{re.escape(name)}\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if m and m.group(1).strip():
            return html.unescape(m.group(1).strip())
    return ""


def iter_detail_cards(text: str, type_id: str = "0", type_name: str = ""):
    """按 <a href="/{vid}.html" title="..."> 定位卡片，并在邻近窗口内取封面与备注。

    不再依赖「链接数组下标 == 图片数组下标」这种脆弱配对。
    """
    cards = []
    seen = set()
    for m in re.finditer(r"<a\s([^>]+)>", text, re.I):
        attrs = m.group(1)
        href = search_tag_attr(attrs, "href")
        if not href:
            continue
        vid = is_detail_url(href)
        if not vid or vid in seen:
            continue
        seen.add(vid)

        title = clean_html(search_tag_attr(attrs, "title"))
        close_at = text.find("</a>", m.end())
        inner = text[m.end(): close_at if close_at > 0 else m.end() + 300]
        if not title:
            title = clean_html(inner)

        pic = search_tag_attr(attrs, "data-original", "data-src", "src")
        if not pic:
            img_m = re.search(r"<img\s([^>]+)>", inner + text[close_at if close_at > 0 else m.end():][:400], re.I)
            if img_m:
                pic = search_tag_attr(img_m.group(1), "data-original", "data-src", "src")
        if pic and not pic.startswith("data:"):
            pic = abs_url(pic)

        window = text[m.end(): m.end() + 600]
        remarks = ""
        note_m = re.search(r'class="[^"]*(?:module-item-note|module-item-info|item-note)[^"]*"[^>]*>(.*?)</div>', window, re.S | re.I)
        if note_m:
            remarks = clean_html(note_m.group(1))
        if not remarks:
            score_m = re.search(r'module-item-comment"[^>]*>(.*?)</div>', window, re.S | re.I)
            if score_m:
                remarks = clean_html(score_m.group(1))

        if not title:
            continue
        cards.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_content": "",
            "type_id": str(type_id or "0"),
            "type_name": type_name,
        })
        if len(cards) >= YHG_LIST_LIMIT:
            break
    return cards


def extract_pagecount(text: str, current_page: int) -> int:
    pages = set()
    scope = text
    for marker in ('class="pagination"', 'class="page"', 'class="page-links"', 'class="pagenum"', "mac-page"):
        idx = text.find(marker)
        if idx >= 0:
            scope = text[idx: idx + 3000]
            break
    for m in re.finditer(r"page[/=-](\d+)", scope, re.I):
        try:
            pages.add(int(m.group(1)))
        except (TypeError, ValueError):
            continue
    m = re.search(r"(?:totalpage|pagecount)\D{0,6}(\d+)", scope, re.I)
    if m:
        pages.add(int(m.group(1)))
    if pages:
        return max(max(pages), current_page)
    return current_page + 1


def find_playlist_block(text: str) -> str:
    markers = ("playlist-box", "playlist-list", "stui-content-ul", "module-play-list", "play-list")
    for marker in markers:
        idx = text.lower().find(marker)
        if idx < 0:
            continue
        block = text[idx: idx + 40000]
        end = min([pos for pos in (block.lower().find("vod-list"), block.lower().find("stui-pannel")) if pos > 200] or [len(block)])
        return block[:end]
    return text


def extract_play_episodes(text: str, vid: str):
    """解析剧集列表，返回 [{name, path, sid, nid}]。"""
    block = find_playlist_block(text)
    episodes = []
    seen = set()
    for m in re.finditer(r"<a\s([^>]+)>", block, re.I):
        attrs = m.group(1)
        href = search_tag_attr(attrs, "href")
        if not href:
            continue
        pm = PLAY_PATH_RE.search(href)
        if pm:
            path = href
            sid, nid = pm.group(2), pm.group(3)
        else:
            qm = PLAY_QUERY_RE.search(href)
            if not qm:
                continue
            path = href
            sid, nid = qm.group(2), qm.group(3)
        if not path.startswith(("/", "http")):
            path = f"/{path.lstrip('./')}"
        if path in seen:
            continue
        seen.add(path)
        name = clean_html(search_tag_attr(attrs, "title"))
        if not name:
            close_at = block.find("</a>", m.end())
            name = clean_html(block[m.end(): close_at if close_at > 0 else m.end() + 120])
        if not name:
            name = f"第{sid}集" if sid else "正片"
        episodes.append({
            "name": name,
            "path": path,
            "sid": sid,
            "nid": nid,
        })
    return episodes


def find_info_block(text: str) -> str:
    """定位详情页的影片信息区，避免命中侧边筛选区的同名标签。"""
    for marker in ("stui-content-list", "video-info", "vodlist-content", "detail-content", "module-info-item"):
        idx = text.find(marker)
        if idx >= 0:
            start = max(0, idx - 2000)
            return text[start: idx + 12000]
    return text


def extract_label_value(text: str, label: str, stop: str = r"</li>|</p>|</dd>|<br\s*/?>"):
    m = re.search(rf"{re.escape(label)}\s*[:：]\s*(.*?)(?={stop}|$)", text, re.S)
    return clean_html(m.group(1)) if m else ""


def extract_content(text: str) -> str:
    for pat in (
        r'class="[^"]*(?:stui-content|vod_content|content)[^"]*"[^>]*>(.*?)</div>',
        r"(?:剧情简介|剧情|简介)\s*[:：]\s*(.*?)(?=</li>|</p>|</div>|<br\s*/?>|$)",
    ):
        m = re.search(pat, text, re.S | re.I)
        if m:
            value = clean_multiline_html(m.group(1))
            if value and len(value) > 4 and "剧情简介" not in value[:6]:
                return value
    return ""


def decode_m3u8_payload(value: str) -> str:
    """处理苹果CMS player 的 encrypt/base64 载荷。"""
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw or raw.startswith("http"):
        return raw
    try:
        padding = "=" * (-len(raw) % 4)
        decoded = base64.b64decode(raw + padding).decode("utf-8", "ignore")
    except Exception:
        return raw
    if not decoded:
        return raw
    if "$$$" in decoded:
        decoded = decoded.split("$$$")[0]
    if "|" in decoded and not decoded.startswith("http"):
        decoded = decoded.rsplit("|", 1)[-1]
    return decoded.strip()


def extract_play_url(text: str) -> str:
    """从播放页 HTML 中提取真实 m3u8 / mp4 直链。"""
    m = re.search(r"player_[a-zA-Z0-9_]+\s*\(\s*['\"]?(\{.*?\})\s*\)\s*;?", text, re.S)
    if m:
        try:
            config = json.loads(m.group(1))
            if config.get("url"):
                return decode_m3u8_payload(config["url"])
            if config.get("url_next"):
                return decode_m3u8_payload(config["url_next"])
        except Exception:
            pass
    m = re.search(r"(?:var\s+)?(?:play_?url|playUrl|playurl|video_?url)\s*=\s*['\"]([^'\"]+)['\"]", text, re.I)
    if m:
        return decode_m3u8_payload(m.group(1))
    m = re.search(r'"url"\s*:\s*"(https?://[^"\\]+)"', text, re.I)
    if m:
        return decode_m3u8_payload(m.group(1))
    m = re.search(r"""['"](https?://[^'"\s<>]+\.(?:m3u8|mp4|flv|ts)[^'"\s<>]*)['"]""", text, re.I)
    if m:
        return m.group(1).strip().replace("\\/", "/")
    m = re.search(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*", text, re.I)
    if m:
        return m.group(0).strip().replace("\\/", "/")
    return ""


def build_filters():
    sort_values = [{"name": name, "value": name} for name in SORT_FILTER_MAP.keys()]
    return {
        tid: [{"key": "sort", "name": "排序", "init": "综合", "value": sort_values}]
        for tid in CATEGORY_MAP.keys()
    }


def resolve_type_name(type_id: str) -> str:
    type_id = str(type_id or "")
    return CATEGORY_NAME_OVERRIDES.get(type_id) or CATEGORY_MAP.get(type_id) or ""


def expand_templates(templates, lang_prefix: str = LANG_PREFIX):
    """把配置的模板展开为候选列表：原样优先，再补充语言前缀变体。"""
    out = []
    for item in templates or []:
        item = str(item or "").strip()
        if item:
            out.append(item)
    prefix = str(lang_prefix or "").rstrip("/")
    if prefix:
        for item in list(out):
            if not item.startswith(prefix):
                variant = f"{prefix}{item}" if item.startswith("/") else f"{prefix}/{item}"
                out.append(variant)
    return uniq(out)


def template_supports_page(template: str) -> bool:
    return "{pg}" in template or "{page}" in template


def is_bad_page(text: str) -> bool:
    m = re.search(r"<title[^>]*>(.*?)</title>", str(text or ""), re.S | re.I)
    title = clean_html(m.group(1)) if m else ""
    return any(marker in title for marker in BAD_PAGE_MARKERS)


def page_head_scope(text: str) -> str:
    """取标题/h1/面包屑等位置信息，用于判断当前页面归属。"""
    parts = []
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    if m:
        parts.append(clean_html(m.group(1)))
    m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
    if m:
        parts.append(clean_html(m.group(1)))
    for pat in (r'(?:breadcrumb|面包屑|位置|当前位置)(.{0,400}?)</div>', r'<div class="position"[^>]*>(.*?)</div>'):
        m = re.search(pat, text, re.S | re.I)
        if m:
            parts.append(clean_html(m.group(1)))
    return " ".join(part for part in parts if part)


def check_category_page(text: str, type_id: str) -> bool:
    """校验抓到的页面确实属于该分类，而不是首页、软 404 或其它分类。"""
    if is_bad_page(text):
        return False
    scope = page_head_scope(text)
    name = resolve_type_name(type_id)
    if not name:
        return True
    if name in scope:
        return True
    others = [n for tid, n in CATEGORY_MAP.items() if tid != str(type_id) and n and n in scope]
    if others:
        return False
    return True


def vid_fingerprint(cards) -> frozenset:
    return frozenset(str(card.get("vod_id")) for card in (cards or []) if card.get("vod_id"))


def vid_overlap(cards, vids: frozenset) -> float:
    """当前结果与首页指纹的重合度，用于识别被重定向到首页的请求。"""
    current = vid_fingerprint(cards)
    if not current or not vids:
        return 0.0
    return len(current & vids) / len(current)


async def get_home_vids() -> frozenset:
    global HOME_VIDS
    if HOME_VIDS is not None:
        return HOME_VIDS
    for template in HOME_PATH_TEMPLATES or ["/"]:
        try:
            text = await request_text(abs_url(template))
        except Exception as e:
            await log("warn", f"[yhg][home-fingerprint] path={template} err={e}")
            continue
        vids = vid_fingerprint(iter_detail_cards(text))
        if vids:
            HOME_VIDS = vids
            break
    if HOME_VIDS is None:
        HOME_VIDS = frozenset()
    return HOME_VIDS


def build_category_url(template: str, type_id: str, page: int, filters: dict) -> str:
    path = template.format(tid=type_id, pg=page, page=page)
    query = {}
    by = SORT_FILTER_MAP.get(str((filters or {}).get("sort") or "综合"), "")
    if by:
        query["by"] = by
    for key, value in (filters or {}).items():
        if key == "sort" or value in (None, ""):
            continue
        query[key] = value
    if query:
        path = f"{path}?{urlencode(query)}"
    return abs_url(path)


def build_search_url(template: str, keyword: str, page: int) -> str:
    return abs_url(template.format(kw=quote(keyword), pg=page, page=page))


async def home(params, context):
    global HOME_VIDS
    try:
        await log("info", "[yhg][home] start")
        classes = [
            {"type_id": tid, "type_name": resolve_type_name(tid)}
            for tid in CATEGORY_MAP.keys()
        ]
        cards = []
        for template in HOME_PATH_TEMPLATES or ["/"]:
            url = abs_url(template)
            try:
                text = await request_text(url)
            except Exception as e:
                await log("warn", f"[yhg][home] path={template} err={e}")
                continue
            cards = iter_detail_cards(text)
            if cards:
                break
        if HOME_VIDS is None:
            HOME_VIDS = vid_fingerprint(cards)
        await log("info", f"[yhg][home] cards={len(cards)}")
        return {"class": classes, "filters": build_filters(), "list": cards[:YHG_PAGE_SIZE]}
    except Exception as e:
        await log("error", f"[yhg][home] {e}")
        return {"class": [], "filters": {}, "list": []}


async def category(params, context):
    try:
        type_id = str(params.get("categoryId") or params.get("typeId") or "20")
        page = max(1, int(params.get("page") or 1))
        filters = params.get("filters") or {}
        type_name = resolve_type_name(type_id)

        templates = expand_templates(CATEGORY_PATH_TEMPLATES)
        if page > 1:
            # 不含翻页占位符的模板在第 2 页会返回第 1 页内容，直接排除。
            page_templates = [t for t in templates if template_supports_page(t)]
            templates = page_templates or templates
        if type_id in CACHE_TEMPLATE_MAP:
            cached = CACHE_TEMPLATE_MAP[type_id]
            if cached in templates:
                templates = [cached] + [t for t in templates if t != cached]

        home_vids = await get_home_vids()
        cards = []
        used_url = ""
        used_template = ""
        pagecount = page + 1
        fallback_cards = []
        for template in templates:
            url = build_category_url(template, type_id, page, filters)
            try:
                text = await request_text(url)
            except Exception as e:
                await log("warn", f"[yhg][category] template={template} url={url} err={e}")
                continue
            candidate = iter_detail_cards(text, type_id, type_name)
            if not candidate:
                continue
            overlap = vid_overlap(candidate, home_vids)
            if overlap >= 0.8:
                await log("warn", f"[yhg][category] reject home-like page template={template} url={url} overlap={overlap:.2f}")
                continue
            if not check_category_page(text, type_id):
                await log("warn", f"[yhg][category] reject mismatched page template={template} url={url} head={page_head_scope(text)[:80]}")
                if not fallback_cards:
                    fallback_cards = candidate
                continue
            cards = candidate
            used_url = url
            used_template = template
            pagecount = extract_pagecount(text, page)
            break

        if not cards and fallback_cards:
            await log("warn", f"[yhg][category] no verified template for tid={type_id}, fallback to unverified result")
            cards = fallback_cards
        if used_template:
            CACHE_TEMPLATE_MAP[type_id] = used_template
        else:
            CACHE_TEMPLATE_MAP.pop(type_id, None)
        await log("info", f"[yhg][category] tid={type_id} page={page} filters={filters} template={used_template} url={used_url} count={len(cards)}")

        has_more = len(cards) >= YHG_PAGE_SIZE
        pagecount = max(page, pagecount) if has_more else page
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": YHG_PAGE_SIZE,
            "total": page * YHG_PAGE_SIZE + (1 if has_more else 0),
            "list": cards,
        }
    except Exception as e:
        await log("error", f"[yhg][category] {e}")
        return {"page": 1, "pagecount": 1, "limit": YHG_PAGE_SIZE, "total": 0, "list": []}


async def search(params, context):
    try:
        keyword = str(params.get("keyword") or params.get("wd") or "").strip()
        page = max(1, int(params.get("page") or 1))
        if not keyword:
            return {"page": 1, "pagecount": 1, "limit": YHG_PAGE_SIZE, "total": 0, "list": []}
        await log("info", f"[yhg][search] keyword={keyword} page={page}")

        cards = []
        home_vids = await get_home_vids()
        for template in expand_templates(SEARCH_PATH_TEMPLATES):
            url = build_search_url(template, keyword, page)
            try:
                text = await request_text(url)
            except Exception as e:
                await log("warn", f"[yhg][search] template={template} err={e}")
                continue
            candidate = iter_detail_cards(text)
            if not candidate:
                continue
            if not is_bad_page(text) and vid_overlap(candidate, home_vids) < 0.8:
                cards = candidate
                break
            await log("warn", f"[yhg][search] reject non-search page template={template} url={url}")

        if not cards and YHG_SEARCH_POST_FALLBACK:
            try:
                text = await request_text(
                    f"{BASE_URL}/index.php/vod/search/search/",
                    method="POST",
                    data={"wd": keyword, "submit": "搜索"},
                )
                cards = iter_detail_cards(text)
            except Exception as e:
                await log("warn", f"[yhg][search] post fallback failed: {e}")

        has_more = len(cards) >= YHG_PAGE_SIZE and page > 0
        await log("info", f"[yhg][search] count={len(cards)}")
        return {
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": YHG_PAGE_SIZE,
            "total": len(cards),
            "list": cards,
        }
    except Exception as e:
        await log("error", f"[yhg][search] {e}")
        return {"page": 1, "pagecount": 1, "limit": YHG_PAGE_SIZE, "total": 0, "list": []}


async def detail(params, context):
    try:
        video_id = str(params.get("videoId") or "").strip()
        vid = is_detail_url(video_id) or re.sub(r"\D", "", video_id)
        if not vid:
            return {"list": []}
        url = abs_url(f"/{vid}.html")
        await log("info", f"[yhg][detail] url={url}")
        text = await request_text(url)
        if is_bad_page(text) and not extract_play_episodes(text, vid):
            await log("warn", f"[yhg][detail] bad page, treat as not found: {url}")
            return {"list": []}

        title = ""
        for pat in (r'<h1[^>]*class="[^"]*stui-pannel-title[^"]*"[^>]*>(.*?)</h1>', r"<h1[^>]*>(.*?)</h1>", r"<title>(.*?)</title>"):
            m = re.search(pat, text, re.S | re.I)
            if m:
                title = clean_html(m.group(1)).split("_")[0].strip()
                if title:
                    break
        title = title or vid

        pic = ""
        m = re.search(r"<img\s([^>]*class=\"[^\"]*(?:stui-thumb-original|vod-thumb|poster)[^\"]*\"[^>]*)>", text, re.S | re.I)
        if not m:
            m = re.search(r"<img\s([^>]+)>", text, re.S | re.I)
        if m:
            pic = abs_url(search_tag_attr(m.group(1), "data-original", "data-src", "src"))

        info_block = find_info_block(text)
        info = {}
        for label, key in FIELD_LABELS.items():
            info[key] = extract_label_value(info_block, label)

        type_id = ""
        type_m = re.search(rf'类型\s*[:：].*?href="[^"]*?/vodtype/(\d+)\.html"', info_block, re.S)
        if type_m:
            type_id = type_m.group(1)
        type_name = info.get("type_name", "") or resolve_type_name(type_id)
        if not type_id and type_name:
            for tid, name in CATEGORY_MAP.items():
                if name and name in type_name:
                    type_id = tid
                    break

        sources = []
        episodes = extract_play_episodes(text, vid)
        direct_urls = uniq(re.findall(r"""['"](https?://[^'"\s<>]+\.m3u8[^'"\s<>]*)['"]""", text, re.I))
        if episodes:
            source_episodes = []
            for ep in episodes:
                play_meta = {
                    "kind": "page",
                    "path": ep["path"],
                    "name": ep["name"],
                    "vid": vid,
                    "sid": ep["sid"],
                    "nid": ep["nid"],
                }
                source_episodes.append({
                    "name": ep["name"],
                    "playId": json.dumps(play_meta, ensure_ascii=False),
                })
            sources.append({"name": "在线播放", "episodes": source_episodes})
        elif direct_urls:
            source_episodes = []
            for i, play_url in enumerate(direct_urls, start=1):
                name = f"第{i}集" if len(direct_urls) > 1 else "播放"
                source_episodes.append({
                    "name": name,
                    "playId": json.dumps({"kind": "url", "url": play_url, "name": name}, ensure_ascii=False),
                })
            sources.append({"name": "直链", "episodes": source_episodes})

        await log("info", f"[yhg][detail] title={title} sources={len(sources)} episodes={sum(len(s.get('episodes', [])) for s in sources)}")

        item = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": info.get("vod_remarks", ""),
            "vod_year": info.get("vod_year", ""),
            "vod_area": info.get("vod_area", ""),
            "vod_lang": info.get("vod_lang", ""),
            "vod_director": info.get("vod_director", ""),
            "vod_actor": info.get("vod_actor", ""),
            "vod_writer": info.get("vod_writer", ""),
            "vod_subtitle": info.get("vod_subtitle", ""),
            "vod_imdb": info.get("vod_imdb", ""),
            "vod_pubdate": info.get("vod_pubdate", ""),
            "update_date": info.get("update_date", ""),
            "vod_content": extract_content(info_block),
            "type_id": type_id,
            "type_name": type_name,
            "vod_play_sources": sources,
        }
        return {"list": [item]}
    except Exception as e:
        await log("error", f"[yhg][detail] {e}")
        return {"list": []}


async def play(params, context):
    try:
        raw_play_id = params.get("playId")
        flag = str(params.get("flag") or "")
        await log("info", f"[yhg][play] flag={flag} rawPlayId={raw_play_id}")
        meta = raw_play_id if isinstance(raw_play_id, dict) else json.loads(str(raw_play_id or "{}"))
        kind = str(meta.get("kind") or "")

        if kind == "url":
            return {
                "urls": [{"name": meta.get("name") or "播放", "url": str(meta.get("url") or "").strip()}],
                "flag": flag or "直链",
                "header": {"User-Agent": UA, "Referer": f"{BASE_URL}/"},
                "parse": 0,
            }

        if kind == "page":
            path = str(meta.get("path") or "").strip()
            play_url = abs_url(path)
            cache_key = f"yhg:play:{play_url}"
            cached = await get_cached_json(cache_key)
            if cached:
                return {
                    "urls": [{"name": meta.get("name") or "播放", "url": cached}],
                    "flag": flag or "在线播放",
                    "header": {"User-Agent": UA, "Referer": play_url},
                    "parse": 0,
                }
            text = await request_text(play_url, referer=f"{BASE_URL}/{meta.get('vid') or ''}.html")
            real_url = extract_play_url(text)
            if real_url:
                await set_cached_json(cache_key, real_url)
                return {
                    "urls": [{"name": meta.get("name") or "播放", "url": real_url}],
                    "flag": flag or "在线播放",
                    "header": {"User-Agent": UA, "Referer": play_url},
                    "parse": 0,
                }
            await log("warn", f"[yhg][play] no playable url, fallback to page: {play_url}")
            return {
                "urls": [{"name": meta.get("name") or "原始页面", "url": play_url}],
                "flag": flag or "在线播放",
                "header": {"User-Agent": UA, "Referer": f"{BASE_URL}/"},
                "parse": 1,
            }

        return {"urls": [], "flag": flag, "parse": 0}
    except Exception as e:
        await log("error", f"[yhg][play] {e}")
        return {"urls": [], "flag": str(params.get('flag') or ''), "parse": 0}


if __name__ == "__main__":
    run({"home": home, "category": category, "detail": detail, "search": search, "play": play})
