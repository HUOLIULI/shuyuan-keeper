#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shuyuan-keeper v3

聚合 10 类资源（书源 / 订阅源 / TVBox / IPTV / 采集接口 / 影视直连站 / 音源 /
磁力影视 / 影视解析 / 影视本地包）。

上游 = 社区已经做过一轮每日验活的聚合仓库 + 发现型站点（yckceo）+
zhuiju 追剧指南（在线观看/磁力/网盘）+ 肥猫 TVBox 仓（影视解析 parses）+
洛雪/MusicFree 音源聚合（音乐解析）。

本仓库在其基础上做二次验真，并按类型分别导出可直接被各 App 订阅的文件：

    docs/valid.json            阅读 Legado 书源
    docs/valid_subscribe.json  阅读 Legado 订阅源
    docs/valid_tvbox.json      TVBox / 影视仓 单仓配置（含 T4 接口配置、猫源/肥猫）
    docs/valid_iptv.m3u        IPTV 播放列表（VLC / Kodi / DIYP / TVBox）
    docs/valid_collect.json    苹果CMS / 空壳影视 采集接口
    docs/valid_videosite.json  drpy/HCCX 规则映射出的可直连影视站（含在线观看站）
    docs/valid_music.json      洛雪 LX / MusicFree 音源（.js 插件订阅，含音乐解析）
    docs/valid_magnet.json    磁力/BT 聚合搜索站 + 网盘搜索站（影视本地包入口）
    docs/valid_vparse.json    TVBox 影视解析接口（parses，按 flag 聚合）
    docs/valid_localpkg.json  影视本地包获取入口（网盘搜索 / 离线包仓库）
"""

import argparse
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
CONFIG = ROOT / "config" / "sources.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULTS = {
    "search_key": "我的",
    "timeout": 10,
    "workers": 12,
    "fail_limit": 3,
    "fetch_gap_days": 8,
    "validate_workers": 16,
    "recheck_hours": {
        "book": 360, "subscribe": 360, "tvbox": 360, "iptv": 360,
        "collect": 360, "videosite": 360, "music": 360,
        "magnet": 360, "vparse": 360, "localpkg": 360,
    },
    "upstreams": [],
    "yckceo_index": [],
    "yckceo_collect_index": [],
}

CONF = {}
UPSTREAMS = []
UPSTREAM_FILES = {}
YCKCEO_INDEX = []
YCKCEO_COLLECT_INDEX = []
YCKCEO_PROBE_LIMIT = 40
SEARCH_KEY = ""
TIMEOUT = 10
WORKERS = 12
FAIL_LIMIT = 3
# 上游拉取周期（天）：每 8 天拉一次，窗口外的 schedule 运行只验证、不拉取
FETCH_GAP_DAYS = 8
# 拉取周期（秒）：默认 8 天，可由 config fetch_gap_days / fetch_gap_hours 覆盖
FETCH_GAP = FETCH_GAP_DAYS * 86400
# 校验并发数：URL 去重后的独立 URL 用线程池并发探活
VALIDATE_WORKERS = 24
RECHECK_HOURS = DEFAULTS["recheck_hours"]
# 校验并发数：URL 去重后的独立 URL 用线程池并发探活
VALIDATE_WORKERS = 24
# 失效条目标墓碑后，多少天内不再重新入库；过期后允许上游再次带回来
TOMBSTONE_DAYS = 30
# 已验证 valid 的源有效期（天）：期内不重复检验，到期后由下次 validate 重新探活
VALID_VALID_DAYS = 15


def load_config():
    global CONF, UPSTREAMS, YCKCEO_INDEX, YCKCEO_COLLECT_INDEX
    global SEARCH_KEY, TIMEOUT, WORKERS
    global FAIL_LIMIT, FETCH_GAP, RECHECK_HOURS, VALIDATE_WORKERS
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        try:
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 读取 {CONFIG} 失败：{exc}")
    CONF = cfg
    UPSTREAMS = cfg.get("upstreams", [])
    UPSTREAM_FILES = {u.get("name", ""): u.get("files", []) for u in UPSTREAMS}
    YCKCEO_INDEX = cfg.get("yckceo_index", [])
    YCKCEO_COLLECT_INDEX = cfg.get("yckceo_collect_index", [])
    SEARCH_KEY = cfg.get("search_key", "我的")
    TIMEOUT = int(cfg.get("timeout", 10))
    WORKERS = int(cfg.get("workers", 12))
    FAIL_LIMIT = int(cfg.get("fail_limit", 3))
    # 拉取周期：优先按天（fetch_gap_days），兼容旧的按小时（fetch_gap_hours）
    if "fetch_gap_days" in cfg:
        FETCH_GAP = int(cfg["fetch_gap_days"]) * 86400
    else:
        FETCH_GAP = int(cfg.get("fetch_gap_hours", FETCH_GAP_DAYS)) * 3600
    RECHECK_HOURS = cfg.get("recheck_hours", DEFAULTS["recheck_hours"])
    VALIDATE_WORKERS = int(cfg.get("validate_workers", 24))


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def empty_store():
    return {
        "sources": [],
        "archived": [],
        "dead": {},
        "last_fetch": 0,
        "discovered": [],
        "upstreams": {},
        "updated_at": None,
    }


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _legacy_subcat(rec):
    """老库存条目缺 subcat 时的按类型/来源兜底（仅补空，不覆盖已有值）。"""
    if rec.get("subcat"):
        return rec.get("subcat")
    stype = rec.get("type") or ""
    src = rec.get("source") or {}
    origin = (rec.get("origins") or [""])[0]
    if stype == "videosite":
        if "zhuiju" in origin:
            return "online_video"
        return "hccx_rule"
    if stype == "music":
        origin_s = origin or ""
        if "音源" in origin_s or "lx" in origin_s.lower():
            return "music_source"
        return "music_parse"
    if stype in ("magnet", "localpkg"):
        return "cloud_search"
    if stype == "vparse":
        return "parse_iface"
    return ""


def load_store():
    path = DATA / "store.json"
    store = empty_store()
    if path.exists():
        try:
            store.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] store.json 损坏，重建：{exc}")
    for key, val in empty_store().items():
        store.setdefault(key, val)
    # 老库存迁移：为缺 subcat 的新类型条目按来源补分类细分（幂等）
    for rec in store.get("sources", []):
        if rec.get("type") in ("videosite", "music", "magnet", "vparse", "localpkg"):
            rec["subcat"] = _legacy_subcat(rec)
    return store


def save_store(store):
    """原子写：先写临时文件再 rename，避免验证中途崩溃时留下半截 store.json 污染 cache。"""
    DATA.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = now_iso()
    target = DATA / "store.json"
    tmp = DATA / "store.json.tmp"
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def domain_key(url):
    clean = (url or "").split("#", 1)[0].strip()
    host = (urlparse(clean).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def origin_of(url):
    """取 URL 的 scheme://host[:port]，用于站点级存活探测。"""
    try:
        p = urlparse((url or "").split("#", 1)[0].strip())
    except Exception:  # noqa: BLE001
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


# site_alive 结果按 origin 缓存：同一轮验证里大量条目探同一主机，只真打一次
_ALIVE_CACHE = {}

# 这类域名永远"活着"（CDN/raw 静态托管）：它们上的 404 是文件没了、不是站点没了，
# 不能据此判 alive → flaky，否则失效音源/T4 接口会被永久标黄而不删除
_ALWAYS_ALIVE_HOSTS = (
    "githubusercontent.com", "jsdelivr.net", "unpkg.com",
    "fastly.net", "cloudflare.com", "akamai.com",
)


def _host_always_alive(url):
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ALWAYS_ALIVE_HOSTS)


def site_alive(url, use_cache=True):
    """站点级存活：只要主机能建立连接并返回任意 HTTP 响应即算站点还在。

    对证书链不完整的国内站点做降级（verify=False / https→http 回退），
    用于区分「站点整个没了（dead）」和「站点还在、只是某条规则/接口失效（flaky）」。
    结果按 origin 缓存，避免同一主机在大批量验证里被反复探活。
    """
    origin = origin_of(url)
    if not origin:
        return False
    key = origin.lower()
    if use_cache and key in _ALIVE_CACHE:
        return _ALIVE_CACHE[key]
    # CDN/raw 静态托管域名视为常活（其上的失效是文件级、不是站点级）
    if _host_always_alive(origin):
        _ALIVE_CACHE[key] = True
        return True
    candidates = [origin]
    if origin.startswith("https://"):
        candidates.append("http://" + origin[len("https://"):])
    for base in candidates:
        for verify in (True, False):
            try:
                resp = requests.get(base, headers={"User-Agent": UA}, timeout=8,
                                    allow_redirects=True, stream=True, verify=verify)
                resp.close()
                _ALIVE_CACHE[key] = True
                return True
            except Exception:  # noqa: BLE001
                continue
    _ALIVE_CACHE[key] = False
    return False


def dedup_str(rec):
    """把 dedup_key 转成可序列化字符串，用于墓碑集合。"""
    return "|".join(str(x) for x in dedup_key(rec))


def active_tombstones(store):
    """返回仍在保护期内的失效墓碑 key 集合，并顺手把 store["dead"] 规范成 dict。

    旧格式（list）视为已过期；超过 TOMBSTONE_DAYS 的墓碑自动清理，
    给暂时宕机、后来恢复的站点一个重新入库的机会。
    """
    raw = store.get("dead")
    if isinstance(raw, dict):
        items = raw
    else:
        items = {k: "1970-01-01T00:00:00Z" for k in (raw or [])}
    fresh = {k: ts for k, ts in items.items() if _age_hours(ts) < TOMBSTONE_DAYS * 24}
    store["dead"] = fresh
    return set(fresh)


def http_get(url, timeout=8, headers=None, allow_redirects=True, binary=False):
    try:
        resp = requests.get(
            url,
            headers=headers or {"User-Agent": UA},
            timeout=(5, min(timeout, 8)),
            allow_redirects=allow_redirects,
        )
        if resp.status_code == 200:
            if binary:
                return resp.content
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
    except Exception:  # noqa: BLE001
        pass
    return None


def fetch_json_text(url, timeout=40):
    """拉取上游 JSON/文本，做 charset 兜底解码（UTF-8 / GBK / 其他）。

    返回文本；拉取失败返回 None。二进制安全：先读 content，再按 Content-Type
    声明的 charset 依次兜底解码，彻底避免 GBK 等非 UTF-8 上游 JSON 解析失败。
    """
    try:
        resp = requests.get(url, headers={"User-Agent": UA},
                            timeout=(5, min(timeout, 30)), allow_redirects=True)
        if resp.status_code != 200:
            return None
        charset = (resp.encoding or "").strip()
        if not charset:
            ct = (resp.headers.get("Content-Type") or "").lower()
            charset = ct.split("charset=")[-1].strip() if "charset=" in ct else ""
        encodings = []
        if charset and charset.lower() not in ("utf-8", "utf8"):
            encodings.append(charset.lower().replace("_", "-"))
        encodings += ["utf-8", "utf-8-sig", "gbk", "latin-1"]
        seen = set()
        for enc in encodings:
            key = enc.lower().replace("_", "-")
            if key in seen:
                continue
            seen.add(key)
            try:
                return resp.content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return resp.content.decode("latin-1", "replace")
    except Exception:  # noqa: BLE001
        return None


def gh_api(url):
    """GitHub REST 调用；有 GITHUB_TOKEN 时带上以提高限额（Actions 里注入）。"""
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200:
            return resp.json()
    except Exception:  # noqa: BLE001
        pass
    return None


def dedup_key(rec):
    """iptv / music / magnet / vparse / localpkg 用完整 URL 去重
    （同域名多频道、同 CDN 多插件、同站多 flag），其余用域名去重。"""
    if rec["type"] in ("iptv", "music", "magnet", "vparse", "localpkg"):
        return (rec["url"], rec["type"])
    return (rec["domain"], rec["type"])


def coerce_version(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


_JSON_COMMENT_RE = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', re.S)


def strip_json_comments(text):
    """去掉 JSON 里的 // 与 /* */ 注释（TVBox 配置常见脏格式）。"""
    return _JSON_COMMENT_RE.sub(lambda m: m.group(1) or "", text)


def loads_lenient(text):
    """尽量解析 JSON；失败时先去注释再试。"""
    if isinstance(text, (dict, list)):
        return text
    if isinstance(text, (bytes, bytearray)):
        # 上游可能返回非 UTF-8（如 GBK）或二进制：逐编码兜底
        for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                text = text.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = text.decode("latin-1", "replace")
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        try:
            return json.loads(strip_json_comments(text))
        except Exception:  # noqa: BLE001
            return None


# --------------------------------------------------------------------------- #
# 各类型解析器
# --------------------------------------------------------------------------- #
def parse_book(text, origin):
    """Legado 书源 / 订阅源：JSON 数组；也兼容「多个 JSON 数组直接拼接」的脏格式。"""
    if isinstance(text, dict):
        text = [text]
    if isinstance(text, list):
        items = []
        for src in text:
            if not isinstance(src, dict):
                continue
            url = src.get("bookSourceUrl") or src.get("sourceUrl") or ""
            name = src.get("bookSourceName") or src.get("sourceName") or ""
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                items.append({"url": url, "name": name, "raw": src})
        return items

    if not isinstance(text, str):
        return []

    decoder = json.JSONDecoder()
    pos = 0
    length = len(text)
    items = []
    while True:
        while pos < length and text[pos] in " \t\r\n":
            pos += 1
        if pos >= length:
            break
        try:
            value, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        pos = end
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            continue
        for src in value:
            if not isinstance(src, dict):
                continue
            url = src.get("bookSourceUrl") or src.get("sourceUrl") or ""
            name = src.get("bookSourceName") or src.get("sourceName") or ""
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                items.append({"url": url, "name": name, "raw": src})
    return items


def parse_tvbox(text, origin):
    """TVBox 配置：多仓 {storeHouse:[...]} 或单仓 {spider,sites,lives,parses}；容忍 // 注释。"""
    if isinstance(text, str):
        text = loads_lenient(text)
    items = []
    if not isinstance(text, dict):
        return items

    if "storeHouse" in text:
        for wh in text.get("storeHouse", []) or []:
            if not isinstance(wh, dict):
                continue
            src_url = wh.get("sourceUrl") or ""
            name = wh.get("sourceName") or src_url or "多仓子项"
            items.append(
                {
                    "url": src_url or name,
                    "name": name,
                    "raw": wh,
                    "sub_config": src_url,
                }
            )
        return items

    spider = text.get("spider", "") or ""
    for site in text.get("sites", []) or []:
        if not isinstance(site, dict):
            continue
        site_url = site.get("api") or site.get("searchUrl") or site.get("ext") or ""
        items.append(
            {
                "url": site_url,
                "name": site.get("name") or site.get("key") or "",
                "raw": site,
                "spider": spider,
                "kind": site.get("type", 0),
            }
        )
    return items


def parse_videosite(text, origin):
    """影视直连站：从 hccx 规则 JSON 的 `主页url` 字段抽出远端站点。"""
    home = re.findall(r'"主页url"\s*:\s*"([^"]+)"', text)
    items = []
    seen = set()
    for u in home:
        u = u.strip()
        if not u.startswith(("http://", "https://")):
            continue
        if u in seen:
            continue
        seen.add(u)
        items.append({"url": u, "name": origin, "raw": {"url": u, "name": origin},
                      "subcat": "hccx_rule"})
    return items


def parse_m3u(text):
    """M3U 文本：#EXTINF 属性行 + 紧随其后的一个 URL 行。"""
    items = []
    if not text:
        return items
    current_name = ""
    current_attrs = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', line))
            current_attrs = attrs
            tail = line.split(",", 1)
            current_name = tail[1].strip() if len(tail) > 1 else ""
        elif not line.startswith("#"):
            if line.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                items.append(
                    {
                        "url": line,
                        "name": current_name or domain_key(line),
                        "raw": {"url": line, "name": current_name, **current_attrs},
                    }
                )
            current_name = ""
            current_attrs = {}
    return items


def parse_collect(text, origin):
    """采集接口 JSON：数组（元素含 url/api）；也兼容 yoyo.json 的 {list:[...]} 包裹。"""
    if isinstance(text, str):
        try:
            text = json.loads(text)
        except Exception:  # noqa: BLE001
            text = [
                {"url": line.strip()}
                for line in text.splitlines()
                if line.strip().startswith("http") and "api.php" in line
            ]
    if isinstance(text, dict):
        text = text.get("list") or text.get("data") or text.get("sites") or [text]
    items = []
    if not isinstance(text, list):
        return items
    for src in text:
        if not isinstance(src, dict):
            if isinstance(src, str) and src.startswith("http") and "api.php" in src:
                items.append({"url": src, "name": domain_key(src), "raw": {"url": src}})
            continue
        url = src.get("url") or src.get("api") or src.get("apiurl") or ""
        if not isinstance(url, str):
            continue
        name = src.get("name") or src.get("title") or domain_key(url)
        if url.startswith(("http://", "https://")):
            items.append({"url": url, "name": name, "raw": src})
    return items


def parse_music(raw, up):
    """音源/音乐解析上游解析，按 up.kind 分派：

    - musicfree：MusicFree 插件订阅 JSON（{plugins:[{name,url,...}]}）
    - lxreadme ：markdown 里提取 raw .js 音源链接（洛雪聚合仓库 README）
    - single   ：上游 URL 本身就是一个 .js 音源
    - musicflat：GitHub 仓库根目录平铺 .js（up.url 指向单文件时走 single；
                  指向仓库时由 fetch 侧调 git tree 枚举，本函数处理 raw 文件）
    """
    kind = up.get("kind") or "single"
    origin = up.get("name") or "音源"
    src_url = up.get("url") or ""
    items = []

    if kind == "musicfree":
        # MusicFree 插件订阅：音乐解析类（subcat=music_parse）
        data = loads_lenient(raw)
        if isinstance(data, dict):
            plugins = data.get("plugins") or data.get("data") or []
        elif isinstance(data, list):
            plugins = data
        else:
            plugins = []
        for p in plugins or []:
            if not isinstance(p, dict):
                continue
            purl = p.get("url") or p.get("src") or ""
            if not str(purl).startswith(("http://", "https://")):
                continue
            name = p.get("name") or domain_key(purl)
            items.append(
                {"url": purl, "name": name,
                 "raw": {"name": name, "url": purl, "version": p.get("version") or ""},
                 "subcat": "music_parse"}
            )
        return items

    if kind == "lxreadme":
        # 洛雪聚合 README 提取的 .js 音源：音乐解析类（subcat=music_parse）
        name = origin
        seen = set()
        for line in (raw or "").splitlines():
            m = re.match(r"^\s*#{2,4}\s*(.+?)\s*$", line)
            if m:
                name = m.group(1).strip()
            for u in re.findall(r"https://raw\.githubusercontent\.com/[^\s\)\]\"'`]+?\.js", line):
                if u in seen:
                    continue
                seen.add(u)
                items.append({"url": u, "name": name, "raw": {"name": name, "url": u},
                              "subcat": "music_parse"})
        return items

    # single：URL 即一个音源文件（subcat=music_source）
    if src_url.startswith(("http://", "https://")):
        name = origin
        m = re.search(r"/([^/]+)\.js(?:\?|$)", src_url)
        if m:
            name = f"{origin}·{m.group(1)}"
        items.append({"url": src_url, "name": name, "raw": {"name": name, "url": src_url},
                      "subcat": "music_source"})
    return items


def parse_zhuiju(raw, up):
    """zhuiju 追剧指南 resources.json：{resources:[{id,name,url,category,tags[]}] }。

    按 up.kind（形如 "online_video" / "magnet_search" / "cloud_search"）过滤，
    并把 subcat 写到条目上供 UI 分类细分。
    """
    data = loads_lenient(raw)
    if not isinstance(data, dict):
        return []
    res = data.get("resources")
    if not isinstance(res, list):
        return []
    want_cat = up.get("kind") or ""
    # kind 形如 "zhuiju·online_video"：取 · 后的真实 category 值
    if want_cat.startswith("zhuiju·"):
        want_cat = want_cat.split("·", 1)[1]
    origin = up.get("name") or "zhuiju"
    items = []
    for r in res:
        if not isinstance(r, dict):
            continue
        if want_cat and r.get("category") != want_cat:
            continue
        url = r.get("url") or ""
        if not str(url).startswith(("http://", "https://")):
            continue
        name = r.get("name") or domain_key(url)
        items.append({
            "url": url,
            "name": name,
            "raw": {
                "name": name, "url": url,
                "category": r.get("category") or "",
                "summary": r.get("summary") or r.get("summary_short") or "",
                "tags": r.get("tags") or [],
            },
            "subcat": r.get("category") or want_cat or "",
        })
    return items


def parse_tvbox_parses(raw, up):
    """TVBox 配置仓的 parses[]：取 type:1 且 url 非 Demo/Web 占位的真实解析接口。"""
    data = loads_lenient(raw)
    if not isinstance(data, dict):
        return []
    origin = up.get("name") or "tvbox_parses"
    items = []
    seen = set()
    for p in data.get("parses") or []:
        if not isinstance(p, dict):
            continue
        purl = str(p.get("url") or "")
        # 跳过 TVBox 内置占位（Demo/Web 聚合）与非 http(s) 值
        if p.get("type") in (0, 3) or purl in ("", "Demo", "Web"):
            continue
        if not purl.startswith(("http://", "https://")):
            continue
        if purl in seen:
            continue
        seen.add(purl)
        flags = (p.get("ext") or {}).get("flag") if isinstance(p.get("ext"), dict) else None
        name = p.get("name") or "解析"
        items.append({
            "url": purl,
            "name": f"{origin}·{name}" if flags else name,
            "raw": {"name": name, "url": purl, "flags": flags or [], "origin": origin},
            "subcat": "parse_iface",
        })
    return items


def parse_localpkg(raw, up):
    """影视本地包获取入口：up.url 本身即一个搜索/聚合站 URL。"""
    url = up.get("url") or ""
    if not url.startswith(("http://", "https://")):
        return []
    # 网盘搜索/聚合站入口统一 subcat=cloud_search，供 UI 细分
    return [{
        "url": url,
        "name": up.get("name") or domain_key(url),
        "raw": {"name": up.get("name") or domain_key(url), "url": url,
                "subcat": "cloud_search"},
        "subcat": "cloud_search",
    }]


def _ver_num(text):
    m = re.search(r"(\d{6})", text)
    return int(m.group(1)) if m else -1


def fetch_music_tree(repo_url, origin, dir_filter=None):
    """从 GitHub 仓库枚举音源：取指定顶层目录（或自动取最新 V* 目录）下的 *.js。

    dir_filter: 可选，指定要取的顶层目录名（如 "V260907"）；不传时自动取
    版本号最大的 V* 目录。仓库根目录平铺 .js（无 V* 目录）则全收。
    """
    m = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", repo_url or "")
    if not m:
        print(f"  [warn] {origin}: 不是 GitHub 仓库地址，跳过")
        return []
    owner, repo = m.groups()
    info = gh_api(f"https://api.github.com/repos/{owner}/{repo}")
    if not info:
        print(f"  [warn] {origin}: GitHub API 不可用（限额或网络），跳过")
        return []
    branch = info.get("default_branch", "main")
    tree = gh_api(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if not tree:
        return []
    blobs = [t for t in tree.get("tree", [])
             if t.get("type") == "blob" and t["path"].endswith(".js")]
    if not blobs:
        return []
    if dir_filter:
        blobs = [b for b in blobs if b["path"].split("/")[0] == dir_filter]
        if not blobs:
            print(f"  [warn] {origin}: 目录 {dir_filter} 无 .js，跳过")
            return []
    else:
        tops = {b["path"].split("/")[0] for b in blobs}
        vers = sorted([t for t in tops if _ver_num(t) >= 0], key=_ver_num)
        if vers:
            newest = vers[-1]
            blobs = [b for b in blobs if b["path"].split("/")[0] == newest]
    items = []
    for b in blobs:
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{b['path']}"
        label = b["path"].rsplit("/", 1)[-1][:-3]
        items.append({"url": raw, "name": f"{origin}·{label}",
                      "raw": {"name": label, "url": raw},
                      "subcat": "music_parse"})
    return items


# --------------------------------------------------------------------------- #
# 合并入库
# --------------------------------------------------------------------------- #
def merge_items(store, items, stype, origin, skip_known=False):
    """合并入库。

    skip_known=True 时只收新增条目，已拉取过的不再重复合并（版本升级仍生效），
    用于「只拉取新增部分，已拉取过的不再重复入库」。
    版本升级由 upstream status 记录的 count 变化体现，不影响库存条目。
    """
    existing = {dedup_key(r): r for r in store["sources"]}
    tombstones = active_tombstones(store)
    new_n = upd_n = 0
    for item in items:
        url = item.get("url") or ""
        dom = domain_key(url) if isinstance(url, str) else ""
        name = item.get("name") or ""
        if not url and not name:
            continue

        entry = {
            "source": item.get("raw", {}),
            "domain": dom,
            "type": stype,
            "url": url,
            "name": name,
            "status": "pending",
            "fail_count": 0,
            "last_check": None,
            "origins": [origin],
        }
        extra = {k: item[k] for k in ("spider", "sub_config", "kind", "subcat") if k in item}
        entry.update(extra)

        if not entry["domain"] and stype != "iptv":
            entry["domain"] = entry["url"] or entry["name"]

        key = dedup_key(entry)
        if dedup_str(entry) in tombstones:
            # 已被判定失效并删除，除非明显更新否则不再入库
            continue
        rec = existing.get(key)
        if rec is not None:
            if skip_known:
                # 已拉取过：只补 origins，不重合并、不覆盖、不重置校验状态
                if origin not in rec["origins"]:
                    rec["origins"].append(origin)
                continue
            # 非 skip 模式：版本升级或条目失效时重置为待验证
            if origin not in rec["origins"]:
                rec["origins"].append(origin)
            old_v = coerce_version((rec.get("source") or {}).get("lastUpdateTime"))
            new_v = coerce_version((entry.get("source") or {}).get("lastUpdateTime"))
            if new_v > old_v or (rec.get("status") == "invalid" and new_v >= old_v):
                origins = rec["origins"]
                rec.update(entry)
                rec["origins"] = origins
                rec["status"] = "pending"
                rec["fail_count"] = 0
                upd_n += 1
            continue
        # 新条目入库
        store["sources"].append(entry)
        existing[key] = entry
        new_n += 1
    return new_n, upd_n


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def fetch_yckceo_book(store, skip_known=False):
    """yckceo 书源/订阅源：index.html 里列出 /content/id/{id}.html，对应 /json/id/{id}.json。

    封顶 YCKCEO_PROBE_LIMIT 个发现项，避免反爬站点拖慢整体拉取。
    """
    found = set()
    for page in YCKCEO_INDEX:
        html = http_get(page)
        if html:
            for match in re.finditer(r"/yuedu/(shuyuan|shuyuans|rss|rsss)/content/id/(\d+)", html):
                found.add(
                    f"https://www.yckceo.com/yuedu/{match.group(1)}/json/id/{match.group(2)}.json"
                )
        time.sleep(1)

    if found:
        ordered = sorted(found)
        capped = ordered[:YCKCEO_PROBE_LIMIT]
        store["discovered"] = capped
        found = set(capped)
    elif store["discovered"]:
        found = set(store["discovered"])

    total = 0
    for url in sorted(found):
        raw = http_get(url, timeout=20)
        if not raw:
            continue
        items = parse_book(raw, "yckceo")
        stype = "subscribe" if "/yuedu/rss" in url else "book"
        new_n, _ = merge_items(store, items, stype, "yckceo", skip_known=skip_known)
        total += new_n
        time.sleep(1)
    return total


def fetch_yckceo_collect(store, skip_known=False):
    """yckceo 采集源发现型站点：从索引页里提取 api.php 采集接口 URL。"""
    if not YCKCEO_COLLECT_INDEX:
        return 0
    found = set()
    for page in YCKCEO_COLLECT_INDEX:
        html = http_get(page)
        if html:
            for match in re.findall(r"https?://[^\s\"'<>()\u4e00-\u9fff]+api\.php/provide/vod", html):
                found.add(match)
        time.sleep(1)

    total = 0
    for url in sorted(found)[:YCKCEO_PROBE_LIMIT]:
        items = [{"url": url, "name": domain_key(url), "raw": {"url": url, "name": domain_key(url)}}]
        new_n, _ = merge_items(store, items, "collect", "yckceo", skip_known=skip_known)
        total += new_n
        time.sleep(1)
    return total


def fetch_videosite_batch(dir_url, origin):
    """批量拉取 hccx 规则目录：枚举目录下所有 *.json 规则，逐个抽 `主页url` 映射成影视站。

    优先用 GitHub contents API 列目录；API 失败时回退到 config 里 `files` 白名单。
    """
    import time as _time
    items = []
    seen = set()

    def collect_rule(content_url, label):
        text = http_get(content_url, timeout=20)
        if not text:
            return
        for home in parse_videosite(text, label):
            url = home["url"]
            if url in seen:
                continue
            seen.add(url)
            home["name"] = f"{origin}·{label}"
            home.setdefault("subcat", "hccx_rule")
            items.append(home)
        _time.sleep(0.2)

    m = re.match(
        r"https://raw\.githubusercontent\.com/([\w.-]+)/([\w.-]+)/(\w+)/(.*)", dir_url
    )
    if m:
        owner, repo, branch, sub = m.groups()
        api = f"https://api.github.com/repos/{owner}/{repo}/contents/{sub}?ref={branch}"
        listing = http_get(api, timeout=20)
        entries = []
        if listing:
            try:
                entries = json.loads(listing)
            except Exception:  # noqa: BLE001
                entries = []
            if isinstance(entries, dict):
                entries = [entries]
        # API 失败则回退到 config 白名单 files
        if not entries:
            raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{sub}"
            for fname in UPSTREAM_FILES.get(origin, []):
                collect_rule(f"{raw_base}/{fname}", fname)
            return items
        for ent in entries:
            if not isinstance(ent, dict):
                continue
            name = ent.get("name", "")
            if not name.endswith(".json"):
                continue
            content_url = ent.get("download_url")
            if not content_url:
                continue
            collect_rule(content_url, name)
    return items


def cmd_fetch(force=False, skip_known=False):
    """拉取上游。

    - 非 force 时按 FETCH_GAP（8 天）判断是否跳过。
    - skip_known：只入库新增条目，已拉取过的不再重复合并（版本升级仍生效）。
    """
    store = load_store()
    gap = time.time() - (store.get("last_fetch") or 0)
    if not force and gap < FETCH_GAP:
        print(f"[skip] 距上次拉取 {gap / 86400:.1f}d，未到 {FETCH_GAP_DAYS} 天周期，跳过（--force 可强制）")
        return
    mode = "只收新增" if skip_known else "全量"
    total_new = 0
    print(f"[info] 上游 {len(UPSTREAMS)} 个 + yckceo 发现（{mode}模式，书源 {len(YCKCEO_INDEX)} 页 / 采集 {len(YCKCEO_COLLECT_INDEX)} 页）")
    for up in UPSTREAMS:
        # batch videosite 不依赖 raw（URL 是目录），单独处理
        if up["type"] == "videosite" and up.get("batch"):
            status = store["upstreams"].setdefault(up["name"], {})
            try:
                items = fetch_videosite_batch(up["url"], up["name"])
                new_n, upd_n = merge_items(store, items, "videosite", up["name"], skip_known=skip_known)
                status.update(ok=True, last=now_iso(), count=len(items),
                              msg=f"+{new_n}/~{upd_n}", daily=up.get("verify_daily", False))
                total_new += new_n
                print(f"  [ok]   {up['name']}(videosite·batch): {len(items)}条, 新增{new_n}")
                time.sleep(1)
            except Exception as exc:  # noqa: BLE001
                status.update(ok=False, last=now_iso(), count=0, msg=f"解析失败:{exc}",
                              daily=up.get("verify_daily", False))
                print(f"  [err]  {up['name']}: {exc}")
            continue

        # music lxtree 走 GitHub API 枚举仓库，不直接 fetch raw
        if up["type"] == "music" and up.get("kind") == "lxtree":
            status = store["upstreams"].setdefault(up["name"], {})
            try:
                # dir_filter：指定要取的顶层目录（如 V260907）；不传则自动取最新 V* 目录
                items = fetch_music_tree(up["url"], up["name"], dir_filter=up.get("dir_filter"))
                new_n, upd_n = merge_items(store, items, "music", up["name"], skip_known=skip_known)
                status.update(ok=bool(items), last=now_iso(), count=len(items),
                              msg=f"+{new_n}/~{upd_n}", daily=up.get("verify_daily", False))
                total_new += new_n
                print(f"  [ok]   {up['name']}(music·tree{up.get('dir_filter','')}): {len(items)}条, 新增{new_n}")
                time.sleep(1)
            except Exception as exc:  # noqa: BLE001
                status.update(ok=False, last=now_iso(), count=0, msg=f"解析失败:{exc}",
                              daily=up.get("verify_daily", False))
                print(f"  [err]  {up['name']}: {exc}")
            continue

        # music musicflat：GitHub 仓库根目录平铺 .js，用 contents API 枚举
        if up["type"] == "music" and up.get("kind") == "musicflat":
            status = store["upstreams"].setdefault(up["name"], {})
            try:
                m = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", up.get("url") or "")
                if not m:
                    raise ValueError("musicflat 需指向 GitHub 仓库地址")
                owner, repo = m.groups()
                info = gh_api(f"https://api.github.com/repos/{owner}/{repo}")
                if not info:
                    raise ValueError("GitHub API 不可用")
                branch = info.get("default_branch", "main")
                contents = gh_api(f"https://api.github.com/repos/{owner}/{repo}/contents/?ref={branch}")
                items = []
                for f in contents or []:
                    if isinstance(f, dict) and f.get("name", "").endswith(".js"):
                        curl_ = f.get("download_url") or ""
                        if curl_.startswith("http"):
                            items.append({"url": curl_,
                                          "name": f"{up['name']}·{f['name'][:-3]}",
                                          "raw": {"name": f["name"][:-3], "url": curl_},
                                          "subcat": "music_parse"})
                new_n, upd_n = merge_items(store, items, "music", up["name"], skip_known=skip_known)
                status.update(ok=bool(items), last=now_iso(), count=len(items),
                              msg=f"+{new_n}/~{upd_n}", daily=up.get("verify_daily", False))
                total_new += new_n
                print(f"  [ok]   {up['name']}(music·flat): {len(items)}条, 新增{new_n}")
                time.sleep(1)
            except Exception as exc:  # noqa: BLE001
                status.update(ok=False, last=now_iso(), count=0, msg=f"解析失败:{exc}",
                              daily=up.get("verify_daily", False))
                print(f"  [err]  {up['name']}: {exc}")
            continue

        # 二进制安全拉取并做 charset 兜底解码，避免非 UTF-8（GBK 等）上游 JSON 解析失败
        raw = fetch_json_text(up["url"], timeout=40)
        status = store["upstreams"].setdefault(up["name"], {})
        if not raw:
            status.update(ok=False, last=now_iso(), count=0, msg="HTTP失败",
                          daily=up.get("verify_daily", False))
            print(f"  [dead] {up['name']}")
            continue

        items = []

        try:
            if up["type"] in ("book", "subscribe"):
                items = parse_book(raw, up["name"])
            elif up["type"] == "tvbox":
                items = parse_tvbox(raw, up["name"])
            elif up["type"] == "iptv":
                items = parse_m3u(raw)
            elif up["type"] == "collect":
                url = up.get("url", "")
                # maccms 直连接口本身就是一个采集源条目
                if "api.php" in url or "provide/vod" in url:
                    items = [
                        {
                            "url": url,
                            "name": up["name"],
                            "raw": {"url": url, "name": up["name"]},
                        }
                    ]
                else:
                    items = parse_collect(raw, up["name"])
            elif up["type"] == "videosite":
                if up.get("kind") == "online_video":
                    # 在线观看站（zhuiju online_video）：并入 videosite，subcat=online
                    items = parse_zhuiju(raw, up)
                elif up.get("batch"):
                    # 批量模式：上游 URL 指向 hccx 规则目录，自动枚举目录下 json 规则
                    items = fetch_videosite_batch(up["url"], up["name"])
                else:
                    items = parse_videosite(raw, up["name"])
            elif up["type"] == "music":
                items = parse_music(raw, up)
            elif up["type"] == "magnet":
                # 磁力/BT/网盘搜索（zhuiju magnet_search / cloud_search）
                items = parse_zhuiju(raw, up)
            elif up["type"] == "vparse":
                items = parse_tvbox_parses(raw, up)
            elif up["type"] == "localpkg":
                items = parse_localpkg(raw, up)
        except Exception as exc:  # noqa: BLE001
            status.update(ok=False, last=now_iso(), count=0, msg=f"解析失败:{exc}",
                          daily=up.get("verify_daily", False))
            print(f"  [err]  {up['name']}: {exc}")
            continue

        new_n, upd_n = merge_items(store, items, up["type"], up["name"], skip_known=skip_known)
        status.update(ok=True, last=now_iso(), count=len(items),
                      msg=f"+{new_n}/~{upd_n}", daily=up.get("verify_daily", False))
        total_new += new_n
        print(f"  [ok]   {up['name']}({up['type']}): {len(items)}条, 新增{new_n}")
        time.sleep(1)

    total_new += fetch_yckceo_book(store, skip_known=skip_known)
    total_new += fetch_yckceo_collect(store, skip_known=skip_known)
    store["last_fetch"] = time.time()
    save_store(store)
    alive = sum(1 for v in store["upstreams"].values() if v.get("ok"))
    print(f"[done] 上游 {alive}/{len(UPSTREAMS)}，新增 {total_new}，"
          f"库存 {len(store['sources'])}")


# --------------------------------------------------------------------------- #
# validate（按类型差异化）
# --------------------------------------------------------------------------- #
def _rule_status(site_ok, rule_ok):
    """统一判定：规则通过=valid；规则失效但站点在=flaky；站点没了=dead。"""
    if rule_ok:
        return "valid"
    return "flaky" if site_ok else "dead"


def check_book(rec):
    src = rec.get("source") or {}
    base = (src.get("bookSourceUrl") or rec.get("url") or "").split("#", 1)[0]
    if not base.startswith(("http://", "https://")):
        return "dead"
    site_ok = site_alive(base)

    search_url = (src.get("searchUrl") or "").strip()
    template = search_url.split(",", 1)[0]
    if template and "{{key}}" in template:
        probe = template.replace("{{key}}", requests.utils.quote(SEARCH_KEY))
        try:
            resp = requests.get(probe, headers={"User-Agent": UA}, timeout=TIMEOUT,
                                verify=False)
            rule_ok = resp.status_code < 400
        except Exception:  # noqa: BLE001
            rule_ok = False
        return _rule_status(site_ok, rule_ok)
    return "valid" if site_ok else "dead"


def check_tvbox(rec):
    """TVBox 站点条目：有可探测 URL 就探活，结构性条目（无 URL）视为有效。"""
    src = rec.get("source") or {}
    sub = rec.get("sub_config") or ""
    target = sub or (src.get("api") or src.get("searchUrl") or rec.get("url") or "").strip()
    if not target:
        # 多仓子项、或仅有 key/ext 的结构性条目，无独立 URL 可探活
        return "valid"
    if not target.startswith(("http://", "https://")):
        return "dead"
    if http_get(target, timeout=TIMEOUT) is not None:
        return "valid"
    # CDN/raw 静态托管（jsdelivr/raw.githubusercontent 等）上探不到 = 资源本身没了，
    # 不是"站点还在只是接口失效"，应判死以便自动删除，避免永久标黄
    if _host_always_alive(target):
        return "dead"
    return "flaky" if site_alive(target) else "dead"


def check_iptv(rec):
    url = rec.get("url") or ""
    if not url.startswith(("http://", "https://")):
        return "valid" if url.startswith(("rtmp://", "rtsp://", "rtp://", "udp://")) else "dead"
    try:
        resp = requests.head(url, headers={"User-Agent": UA}, timeout=(4, 4),
                             allow_redirects=True)
        if resp.status_code < 400:
            return "valid"
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=(4, 4), stream=True)
        chunk = next(resp.iter_content(1024), b"")
        code = resp.status_code
        resp.close()
        if code == 200 and len(chunk) > 0:
            return "valid"
    except Exception:  # noqa: BLE001
        pass
    # 流本身取不到；若主机（域名）还在，只算规则/流失效（黄），否则站点没了（红）
    return "flaky" if site_alive(url) else "dead"


def check_collect(rec):
    url = (rec.get("url") or "").rstrip("/")
    if not url.startswith(("http://", "https://")):
        return "dead"
    probe = url + "/?ac=list"
    is_xml = "/at/xml/" in probe or probe.endswith(".xml")
    rule_ok = False
    try:
        resp = requests.get(probe, headers={"User-Agent": UA}, timeout=15)
        if resp.status_code == 200:
            text = resp.text.lstrip()
            if is_xml:
                rule_ok = text.startswith("<?xml") and ("<video" in text or "<list" in text)
            else:
                data = json.loads(text)
                rule_ok = isinstance(data, dict) and ("class" in data or "list" in data)
    except Exception:  # noqa: BLE001
        rule_ok = False
    # 接口规则失效但站点还能打开 → 黄；站点也没了 → 红
    return _rule_status(site_alive(url), rule_ok)


def check_videosite(rec):
    """影视直连站：站点能打开即有效（无独立规则层）。"""
    url = rec.get("url") or ""
    if not url.startswith(("http://", "https://")):
        return "dead"
    try:
        resp = requests.head(url, headers={"User-Agent": UA}, timeout=8,
                             allow_redirects=True, verify=False)
        if resp.status_code < 400:
            return "valid"
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=8, stream=True,
                            verify=False)
        chunk = next(resp.iter_content(512), b"")
        resp.close()
        if resp.status_code == 200 and len(chunk) > 0:
            return "valid"
    except Exception:  # noqa: BLE001
        pass
    return "valid" if site_alive(url) else "dead"


def check_music(rec):
    """音源文件：直接探测 .js 可达且非 HTML 错误页。"""
    url = rec.get("url") or ""
    if not url.startswith(("http://", "https://")):
        return "dead"
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=(5, 8), stream=True,
                            verify=False)
        chunk = next(resp.iter_content(512), b"")
        code = resp.status_code
        resp.close()
        if code == 200 and len(chunk) > 0:
            head = chunk.decode("utf-8", "ignore").lstrip().lower()
            if not head.startswith("<!doctype") and "<html" not in head[:200]:
                return "valid"
    except Exception:  # noqa: BLE001
        pass
    return "dead"


def check_vparse(rec):
    """影视解析接口：对 URL 尾部拼一个测试 URL 做 http_get，返回 200 即有效。

    解析接口形如 http://xxx/json/qingfeng.php?url= 或 https://xxx/api/?key=xx&url=，
    直接 GET 末尾 url= 即可验证接口是否还活着。
    """
    url = (rec.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return "dead"
    # 接口若已自带 ?url= 参数则直接 GET；否则拼上占位
    probe = url if "?" in url or url.endswith("=") else url + "?url="
    if http_get(probe, timeout=10) is not None:
        return "valid"
    # 主机还在但接口 404/5xx = 规则失效（flaky）；主机没了 = dead
    return "flaky" if site_alive(url) else "dead"


def check_magnet(rec):
    """磁力/BT/网盘搜索聚合站：站点可达即有效（无独立规则层）。"""
    url = (rec.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return "dead"
    return "valid" if site_alive(url) else "dead"


def check_localpkg(rec):
    """影视本地包获取入口（网盘搜索/离线包仓库）：站点可达即有效。"""
    url = (rec.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return "dead"
    return "valid" if site_alive(url) else "dead"


CHECKERS = {
    "book": check_book,
    "subscribe": check_book,
    "tvbox": check_tvbox,
    "iptv": check_iptv,
    "collect": check_collect,
    "videosite": check_videosite,
    "music": check_music,
    "vparse": check_vparse,
    "magnet": check_magnet,
    "localpkg": check_localpkg,
}


def _age_hours(last_check):
    if not last_check:
        return 10 ** 9
    try:
        ts = datetime.strptime(last_check, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
        return (time.time() - ts) / 3600
    except Exception:  # noqa: BLE001
        return 10 ** 9


# 同一次验证进程内，同一 URL 只真打一次网络（site_alive 已按 origin 缓存，
# 这里是 URL 粒度去重，避免大量同域名条目重复请求），结果按 URL 复用。
def _dedup_by_url(targets):
    """targets 里同一 URL 只保留一条送探活；返回 (unique, url→idx) 供回写。"""
    unique = []
    url_map = {}
    for idx, rec in enumerate(targets):
        url = (rec.get("url") or "").strip()
        if not url:
            continue
        if url in url_map:
            continue
        url_map[url] = idx
        unique.append(rec)
    return unique, url_map


def cmd_validate(batch=400, types=None, all_=False):
    global _ALIVE_CACHE
    _ALIVE_CACHE = {}
    store = load_store()
    # 按类型分桶后轮转取 batch 条：避免新入库的小类型（如 music）
    # 排在 15000+ 条后面而永远进不了验证窗口
    buckets = {}
    for rec in store["sources"]:
        if types and rec["type"] not in types:
            continue
        hours = RECHECK_HOURS.get(rec["type"], 360)
        if all_:
            # 全量模式：无视 15 天有效期，所有条目都重新探活
            buckets.setdefault(rec["type"], []).append(rec)
        elif rec.get("status") == "pending" or _age_hours(rec.get("last_check")) >= hours:
            # 正常模式：仅待验证或有效期（15 天）已到的条目
            buckets.setdefault(rec["type"], []).append(rec)
    targets = []
    while len(targets) < batch and any(buckets.values()):
        for recs in buckets.values():
            if recs:
                targets.append(recs.pop(0))
            if len(targets) >= batch:
                break
    if not targets:
        print("[done] 无待验证条目")
        return

    print(f"[info] 本轮 {len(targets)} 条" + ("（全量）" if all_ else ""))
    started = time.time()
    ok_n = yellow_n = dead_n = 0
    # 同一 URL 只真打一次网络：先按 URL 去重送探活，再用线程池并发探测，
    # 把结果回写到同 URL 的所有条目。site_alive 已按 origin 缓存，
    # 这里是 URL 粒度去重，避免大量同域名条目重复请求。
    unique = _dedup_by_url(targets)[0]
    url_verdicts = {}

    def _probe(rec):
        url = (rec.get("url") or "").strip()
        try:
            verdict = CHECKERS.get(rec["type"], check_book)(rec)
        except Exception:  # noqa: BLE001
            verdict = "dead"
        if verdict not in ("valid", "flaky", "dead"):
            verdict = "valid" if verdict else "dead"
        return url, verdict

    with ThreadPoolExecutor(max_workers=VALIDATE_WORKERS) as pool:
        for url, verdict in pool.map(_probe, unique):
            url_verdicts[url] = verdict

    for rec in targets:
        url = (rec.get("url") or "").strip()
        verdict = url_verdicts.get(url)
        if verdict is None:
            # 无 url 条目（结构性条目）直接探
            try:
                verdict = CHECKERS.get(rec["type"], check_book)(rec)
            except Exception:  # noqa: BLE001
                verdict = "dead"
            if verdict not in ("valid", "flaky", "dead"):
                verdict = "valid" if verdict else "dead"
        rec["last_check"] = now_iso()
        if verdict == "valid":
            rec["status"] = "valid"
            rec["fail_count"] = 0
            ok_n += 1
        elif verdict == "flaky":
            # 站点还活着，只是规则/接口失效：标黄，不计死亡次数
            rec["status"] = "flaky"
            yellow_n += 1
        else:  # dead：站点整个没了
            rec["fail_count"] = rec.get("fail_count", 0) + 1
            dead_n += 1
            if rec["fail_count"] >= FAIL_LIMIT:
                rec["status"] = "invalid"
            elif rec["status"] != "pending":
                rec["status"] = "flaky"

    # 失效：自动删除（不再堆积归档），并记墓碑避免下次 fetch 又被重新拉进来
    dead = [r for r in store["sources"] if r["status"] == "invalid"]
    if dead:
        tombstones = active_tombstones(store)
        stamp = now_iso()
        for r in dead:
            tombstones.add(dedup_str(r))
        store["dead"] = {k: stamp for k in tombstones}
        removed = {dedup_str(r) for r in dead}
        store["sources"] = [r for r in store["sources"] if dedup_str(r) not in removed]
        print(f"[del] 失效自动删除 {len(dead)} 条（墓碑保护 {TOMBSTONE_DAYS} 天）")

    save_store(store)
    print(f"[done] 绿 {ok_n} / 黄 {yellow_n} / 红(站点不可达) {dead_n}，耗时 {time.time() - started:.0f}s")


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def build_tvbox_config(records):
    config = {"spider": "", "sites": [], "lives": [], "parses": []}
    seen = set()
    for rec in records:
        src = rec.get("source") or {}
        if not isinstance(src, dict):
            continue
        if not config["spider"] and rec.get("spider"):
            config["spider"] = rec["spider"]
        if not config["spider"] and src.get("spider"):
            config["spider"] = src["spider"]
        api = src.get("api") or src.get("searchUrl") or ""
        marker = (src.get("key") or "") + "|" + (rec.get("name") or "") + "|" + api
        if marker in seen:
            continue
        seen.add(marker)
        if src.get("api") or src.get("searchUrl") or src.get("key"):
            config["sites"].append(src)
        for live in src.get("lives", []) or []:
            config["lives"].append(live)
        for parse in src.get("parses", []) or []:
            config["parses"].append(parse)
    return config


def build_flat_config(records):
    """扁平导出：每条输出 {name, url, subcat, origin, flags}（磁力/本地包/解析通用）。

    subcat 优先取条目自带值；本地包/磁力上游未细分时统一归到 cloud_search。
    """
    out = []
    seen = set()
    for rec in records:
        subcat = rec.get("subcat") or "cloud_search"
        # 旧库存 localpkg 用过 site_alive 细分，统一归并到 cloud_search（网盘搜索入口）
        if subcat in ("site_alive", ""):
            subcat = "cloud_search"
        key = (rec.get("url") or "", subcat)
        if key in seen:
            continue
        seen.add(key)
        src = rec.get("source") or {}
        out.append({
            "name": rec.get("name") or domain_key(rec.get("url") or ""),
            "url": rec.get("url") or "",
            "subcat": subcat,
            "origin": (rec.get("origins") or [""])[0],
            "flags": src.get("flags") if isinstance(src, dict) else [],
        })
    return out


def cmd_export():
    store = load_store()
    cats = {"book": [], "subscribe": [], "tvbox": [], "iptv": [], "collect": [],
            "videosite": [], "music": [], "magnet": [], "vparse": [], "localpkg": []}
    tvbox_records = []
    for rec in store["sources"]:
        if rec["status"] not in ("valid", "flaky"):
            continue
        stype = rec["type"]
        if stype == "iptv":
            cats["iptv"].append({"name": rec["name"], "url": rec["url"]})
        elif stype == "tvbox":
            tvbox_records.append(rec)
        elif stype in ("magnet", "vparse", "localpkg", "videosite", "music"):
            cats[stype].append(rec)
        else:
            cats[stype].append(rec.get("source"))
    cats["tvbox"] = build_tvbox_config(tvbox_records)
    cats["magnet"] = build_flat_config(cats["magnet"])
    cats["vparse"] = build_flat_config(cats["vparse"])
    cats["localpkg"] = build_flat_config(cats["localpkg"])

    def _flat(rec):
        """videosite/music 扁平化：展开原始 source 字段 + subcat（缺省按类型兜底）。"""
        src = rec.get("source") or {}
        # 展开 source 原始字段（name/url/version/bookSourceUrl...），去掉内部 raw 包裹
        out = {}
        if isinstance(src, dict):
            for k, v in src.items():
                if k != "raw":
                    out[k] = v
        out.setdefault("name", rec.get("name") or domain_key(rec.get("url") or ""))
        out.setdefault("url", rec.get("url") or "")
        sub = rec.get("subcat") or src.get("subcat") or (
            "music_source" if rec.get("type") == "music" else "hccx_rule")
        out["subcat"] = sub
        out["origin"] = (rec.get("origins") or [""])[0]
        return out

    cats["videosite"] = [_flat(r) for r in cats["videosite"]]
    cats["music"] = [_flat(r) for r in cats["music"]]

    # iptv → m3u
    m3u_lines = ["#EXTM3U"]
    seen_streams = set()
    for stream in cats["iptv"]:
        if stream["url"] in seen_streams:
            continue
        seen_streams.add(stream["url"])
        m3u_lines.append(f'#EXTINF:-1,{stream["name"]}')
        m3u_lines.append(stream["url"])
    m3u_text = "\n".join(m3u_lines) + "\n"

    archived = [r.get("source") for r in store["archived"]]
    flaky_n = sum(1 for r in store["sources"] if r.get("status") == "flaky")
    stats = {
        "total": len(store["sources"]) + len(store["archived"]),
        "valid_book": len(cats["book"]),
        "valid_subscribe": len(cats["subscribe"]),
        "valid_tvbox": len(cats["tvbox"].get("sites", [])),
        "valid_iptv": len(seen_streams),
        "valid_collect": len(cats["collect"]),
        "valid_videosite": len(cats["videosite"]),
        "valid_music": len(cats["music"]),
        "valid_magnet": len(cats["magnet"]),
        "valid_vparse": len(cats["vparse"]),
        "valid_localpkg": len(cats["localpkg"]),
        "flaky": flaky_n,
        "archived": len(archived),
        # 历史失效条目总数（含仍在 30 天保护期内的墓碑）
        "dead_removed": len(store.get("dead") or {}),
        "upstreams_alive": sum(1 for v in store["upstreams"].values() if v.get("ok")),
        "upstreams_total": len(store["upstreams"]),
        "updated_at": now_iso(),
    }

    payloads = {
        "valid.json": json.dumps(cats["book"], ensure_ascii=False, indent=1),
        "valid_subscribe.json": json.dumps(cats["subscribe"], ensure_ascii=False, indent=1),
        "valid_tvbox.json": json.dumps(cats["tvbox"], ensure_ascii=False, indent=1),
        "valid_iptv.m3u": m3u_text,
        "valid_collect.json": json.dumps(
            [c for c in cats["collect"] if isinstance(c, dict)],
            ensure_ascii=False, indent=1,
        ),
        "valid_videosite.json": json.dumps(cats["videosite"], ensure_ascii=False, indent=1),
        "valid_music.json": json.dumps(cats["music"], ensure_ascii=False, indent=1),
        "valid_magnet.json": json.dumps(cats["magnet"], ensure_ascii=False, indent=1),
        "valid_vparse.json": json.dumps(cats["vparse"], ensure_ascii=False, indent=1),
        "valid_localpkg.json": json.dumps(cats["localpkg"], ensure_ascii=False, indent=1),
        "archive.json": json.dumps(archived, ensure_ascii=False, indent=1),
        "stats.json": json.dumps(stats, ensure_ascii=False, indent=1),
        "upstreams.json": json.dumps(store["upstreams"], ensure_ascii=False, indent=1),
    }
    for base in (DATA, DOCS):
        base.mkdir(parents=True, exist_ok=True)
        for filename, content in payloads.items():
            (base / filename).write_text(content, encoding="utf-8")
    print(f"[done] {stats}")


def cmd_ingest(submit_dir=None, types=None):
    """入库用户上传条目：扫描 data/user_submit/{type}.json（或目录内所有 json）。

    每个文件 = 该分类下用户上传的条目（结构同 parse_* 输出，或 [url, name] 数组）。
    逐条按类型校验，标 valid/flaky/invalid，有效/flaky 并入 store，invalid 归档。
    输出各条红黄绿结果 JSON 到 stdout，供页面 / Issue 草案复用。
    """
    base = Path(submit_dir) if submit_dir else (DATA / "user_submit")
    store = load_store()
    if not base.exists():
        print(f"[warn] {base} 不存在，无用户上传条目")
        results = []
    else:
        files = sorted(base.glob("*.json"))
        if types:
            files = [f for f in files if f.stem in types]
        results = []
        total_new = 0
        for path in files:
            stype = path.stem
            if stype not in CHECKERS:
                print(f"[skip] 未知分类 {stype}")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"[err]  {path.name}: {exc}")
                continue
            items = []
            if isinstance(payload, dict):
                for k in ("items", "sources", "list", "data", "sites"):
                    if isinstance(payload.get(k), list):
                        items = payload[k]
                        break
                else:
                    items = [payload]
            elif isinstance(payload, list):
                items = payload
            parsed = []
            for it in items:
                if isinstance(it, dict) and ("url" in it or "name" in it or "bookSourceUrl" in it or "api" in it):
                    raw = it
                    url = it.get("url") or it.get("api") or it.get("bookSourceUrl") or ""
                    name = it.get("name") or it.get("title") or it.get("bookSourceName") or ""
                    parsed.append({"url": url, "name": name, "raw": raw})
                elif isinstance(it, str) and it.startswith(("http://", "https://")):
                    parsed.append({"url": it, "name": domain_key(it), "raw": {"url": it}})
            if not parsed:
                print(f"[empty] {path.name}")
                continue
            new_n, upd_n = merge_items(store, parsed, stype, "user")
            total_new += new_n
            checked = []
            for rec in store["sources"]:
                if "user" not in rec.get("origins", []):
                    continue
                if rec["type"] != stype:
                    continue
                verdict = CHECKERS[stype](rec)
                if verdict not in ("valid", "flaky", "dead"):
                    verdict = "valid" if verdict else "dead"
                rec["last_check"] = now_iso()
                if verdict == "valid":
                    rec["status"] = "valid"
                    rec["fail_count"] = 0
                    color = "green"
                elif verdict == "flaky":
                    rec["status"] = "flaky"
                    color = "yellow"
                else:
                    was_valid = rec.get("status") == "valid"
                    rec["fail_count"] = rec.get("fail_count", 0) + 1
                    if rec["fail_count"] >= FAIL_LIMIT:
                        rec["status"] = "invalid"
                        color = "red"
                    elif was_valid:
                        rec["status"] = "flaky"
                        color = "yellow"
                    else:
                        rec["status"] = "pending"
                        color = "yellow"
                checked.append({
                    "name": rec.get("name"), "url": rec.get("url"),
                    "status": rec["status"], "color": color,
                })
            dead = [r for r in store["sources"] if r["status"] == "invalid" and "user" in r.get("origins", [])]
            if dead:
                tombstones = active_tombstones(store)
                stamp = now_iso()
                for r in dead:
                    tombstones.add(dedup_str(r))
                store["dead"] = {k: stamp for k in tombstones}
                removed = {dedup_str(r) for r in dead}
                store["sources"] = [r for r in store["sources"] if dedup_str(r) not in removed]
            results.append({
                "file": path.name, "type": stype,
                "items": len(parsed), "new": new_n, "checked": checked,
            })
            print(f"  [ok] {path.name}({stype}): {len(parsed)}条, 新增{new_n}")
        save_store(store)
    print(f"[done] 用户上传入库完成, 新增 {total_new if base.exists() else 0}")
    print(json.dumps(results, ensure_ascii=False, indent=1))


def cmd_status():
    store = load_store()
    from collections import Counter

    by_type = {}
    for rec in store["sources"]:
        by_type.setdefault(rec["type"], []).append(rec)
    for stype, recs in sorted(by_type.items()):
        counter = Counter(r["status"] for r in recs)
        print(f"{stype}: {len(recs)}条 {dict(counter)}")
    alive = sum(1 for v in store["upstreams"].values() if v.get("ok"))
    print(f"归档 {len(store['archived'])}，上游 {alive}/{len(store['upstreams'])}")


def main():
    load_config()
    parser = argparse.ArgumentParser(description="shuyuan-keeper v3")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--force", action="store_true")
    p_fetch.add_argument("--skip-known", dest="skip_known", action="store_true",
                        help="只入库新增条目，已拉取过的不再重复合并")
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--batch", type=int, default=400)
    p_validate.add_argument("--type", action="append", dest="vtypes",
                            help="只验证指定类型，可多次传参（book/subscribe/tvbox/iptv/collect）")
    p_validate.add_argument("--all", dest="validate_all", action="store_true",
                            help="全量验证：无视 15 天有效期，所有条目重新探活")
    sub.add_parser("export")
    sub.add_parser("status")
    p_ingest = sub.add_parser("ingest", help="入库用户上传条目")
    p_ingest.add_argument("--dir", default=None, help="user_submit 目录（默认 data/user_submit）")
    p_ingest.add_argument("--type", action="append", dest="itypes", help="只处理指定分类")
    args = parser.parse_args()

    if args.cmd == "fetch":
        cmd_fetch(args.force, args.skip_known)
    elif args.cmd == "validate":
        cmd_validate(args.batch, args.vtypes or None, all_=args.validate_all)
    elif args.cmd == "export":
        cmd_export()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "ingest":
        cmd_ingest(args.dir, args.itypes or None)


if __name__ == "__main__":
    main()
