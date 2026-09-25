#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shuyuan-keeper v3

聚合 5 类资源（书源 / 订阅源 / TVBox / IPTV / 采集接口）。

上游 = 社区已经做过一轮每日验活的聚合仓库 + 发现型站点（yckceo）。
本仓库在其基础上做二次验真，并按类型分别导出可直接被各 App 订阅的文件：

    docs/valid.json            阅读 Legado 书源
    docs/valid_subscribe.json  阅读 Legado 订阅源
    docs/valid_tvbox.json      TVBox / 影视仓 单仓配置
    docs/valid_iptv.m3u        IPTV 播放列表（VLC / Kodi / DIYP / TVBox）
    docs/valid_collect.json    苹果CMS / 空壳影视 采集接口

CLI:
    python scripts/keeper.py fetch [--force]
    python scripts/keeper.py validate [--batch 400]
    python scripts/keeper.py export
    python scripts/keeper.py status
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

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
    "fetch_gap_hours": 20,
    "validate_minutes": 35,
    "recheck_hours": {"book": 168, "subscribe": 168, "tvbox": 72, "iptv": 72, "collect": 72},
    "upstreams": [],
    "yckceo_index": [],
    "yckceo_collect_index": [],
}

CONF = {}
UPSTREAMS = []
YCKCEO_INDEX = []
YCKCEO_COLLECT_INDEX = []
YCKCEO_PROBE_LIMIT = 40
SEARCH_KEY = ""
TIMEOUT = 10
WORKERS = 12
FAIL_LIMIT = 3
FETCH_GAP = 20 * 3600
VALIDATE_MINUTES = 35
RECHECK_HOURS = DEFAULTS["recheck_hours"]


def load_config():
    global CONF, UPSTREAMS, YCKCEO_INDEX, YCKCEO_COLLECT_INDEX
    global SEARCH_KEY, TIMEOUT, WORKERS
    global FAIL_LIMIT, FETCH_GAP, VALIDATE_MINUTES, RECHECK_HOURS
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        try:
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 读取 {CONFIG} 失败：{exc}")
    CONF = cfg
    UPSTREAMS = cfg.get("upstreams", [])
    YCKCEO_INDEX = cfg.get("yckceo_index", [])
    YCKCEO_COLLECT_INDEX = cfg.get("yckceo_collect_index", [])
    SEARCH_KEY = cfg.get("search_key", "我的")
    TIMEOUT = int(cfg.get("timeout", 10))
    WORKERS = int(cfg.get("workers", 12))
    FAIL_LIMIT = int(cfg.get("fail_limit", 3))
    FETCH_GAP = int(cfg.get("fetch_gap_hours", 20)) * 3600
    VALIDATE_MINUTES = int(cfg.get("validate_minutes", 35))
    RECHECK_HOURS = cfg.get("recheck_hours", DEFAULTS["recheck_hours"])


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def empty_store():
    return {
        "sources": [],
        "archived": [],
        "last_fetch": 0,
        "discovered": [],
        "upstreams": {},
        "updated_at": None,
    }


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    return store


def save_store(store):
    DATA.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = now_iso()
    (DATA / "store.json").write_text(
        json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def domain_key(url):
    clean = (url or "").split("#", 1)[0].strip()
    host = (urlparse(clean).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def http_get(url, timeout=25, headers=None, allow_redirects=True):
    try:
        resp = requests.get(
            url,
            headers=headers or {"User-Agent": UA},
            timeout=(10, min(timeout, 25)),
            allow_redirects=allow_redirects,
        )
        if resp.status_code == 200:
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
    except Exception:  # noqa: BLE001
        pass
    return None


def dedup_key(rec):
    """iptv 用完整 URL 去重（同域名多频道），其余用域名去重。"""
    if rec["type"] == "iptv":
        return (rec["url"], rec["type"])
    return (rec["domain"], rec["type"])


def coerce_version(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    """TVBox 配置：多仓 {storeHouse:[...]} 或单仓 {spider,sites,lives,parses}。"""
    if isinstance(text, str):
        try:
            text = json.loads(text)
        except Exception:  # noqa: BLE001
            return []
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


# --------------------------------------------------------------------------- #
# 合并入库
# --------------------------------------------------------------------------- #
def merge_items(store, items, stype, origin):
    existing = {dedup_key(r): r for r in store["sources"]}
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
        extra = {k: item[k] for k in ("spider", "sub_config", "kind") if k in item}
        entry.update(extra)

        if not entry["domain"] and stype != "iptv":
            entry["domain"] = entry["url"] or entry["name"]

        key = dedup_key(entry)
        rec = existing.get(key)
        if rec is None:
            store["sources"].append(entry)
            existing[key] = entry
            new_n += 1
            continue

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
    return new_n, upd_n


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def fetch_yckceo_book(store):
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
        new_n, _ = merge_items(store, items, stype, "yckceo")
        total += new_n
        time.sleep(1)
    return total


def fetch_yckceo_collect(store):
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
        new_n, _ = merge_items(store, items, "collect", "yckceo")
        total += new_n
        time.sleep(1)
    return total


def cmd_fetch(force=False):
    store = load_store()
    gap = time.time() - (store.get("last_fetch") or 0)
    if not force and gap < FETCH_GAP:
        print(f"[skip] 距上次拉取 {gap / 3600:.1f}h，跳过（--force 可强制）")
        return

    total_new = 0
    print(f"[info] 上游 {len(UPSTREAMS)} 个 + yckceo 发现（书源 {len(YCKCEO_INDEX)} 页 / 采集 {len(YCKCEO_COLLECT_INDEX)} 页）")
    for up in UPSTREAMS:
        raw = http_get(up["url"], timeout=40)
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
        except Exception as exc:  # noqa: BLE001
            status.update(ok=False, last=now_iso(), count=0, msg=f"解析失败:{exc}",
                          daily=up.get("verify_daily", False))
            print(f"  [err]  {up['name']}: {exc}")
            continue

        new_n, upd_n = merge_items(store, items, up["type"], up["name"])
        status.update(ok=True, last=now_iso(), count=len(items),
                      msg=f"+{new_n}/~{upd_n}", daily=up.get("verify_daily", False))
        total_new += new_n
        print(f"  [ok]   {up['name']}({up['type']}): {len(items)}条, 新增{new_n}")
        time.sleep(1)

    total_new += fetch_yckceo_book(store)
    total_new += fetch_yckceo_collect(store)
    store["last_fetch"] = time.time()
    save_store(store)
    alive = sum(1 for v in store["upstreams"].values() if v.get("ok"))
    print(f"[done] 上游 {alive}/{len(UPSTREAMS)}，新增 {total_new}，"
          f"库存 {len(store['sources'])}")


# --------------------------------------------------------------------------- #
# validate（按类型差异化）
# --------------------------------------------------------------------------- #
def check_book(rec):
    src = rec.get("source") or {}
    base = (src.get("bookSourceUrl") or rec.get("url") or "").split("#", 1)[0]
    if not base.startswith(("http://", "https://")):
        return False
    try:
        resp = requests.get(base, headers={"User-Agent": UA}, timeout=TIMEOUT,
                            allow_redirects=True)
        if resp.status_code >= 400:
            return False
    except Exception:  # noqa: BLE001
        return False

    search_url = (src.get("searchUrl") or "").strip()
    template = search_url.split(",", 1)[0]
    if template and "{{key}}" in template:
        probe = template.replace("{{key}}", requests.utils.quote(SEARCH_KEY))
        try:
            resp = requests.get(probe, headers={"User-Agent": UA}, timeout=TIMEOUT)
            return resp.status_code < 400
        except Exception:  # noqa: BLE001
            return False
    return True


def check_tvbox(rec):
    """TVBox 站点条目：有可探测 URL 就探活，结构性条目（无 URL）视为有效。"""
    src = rec.get("source") or {}
    sub = rec.get("sub_config") or ""
    if sub:
        return http_get(sub, timeout=TIMEOUT) is not None
    url = (src.get("api") or src.get("searchUrl") or rec.get("url") or "").strip()
    if not url:
        # 多仓子项、或仅有 key/ext 的结构性条目，无独立 URL 可探活
        return True
    if url.startswith(("http://", "https://")):
        return http_get(url, timeout=TIMEOUT) is not None
    return False


def check_iptv(rec):
    url = rec.get("url") or ""
    if not url.startswith(("http://", "https://")):
        return url.startswith(("rtmp://", "rtsp://")) or url.startswith(("rtp://", "udp://"))
    try:
        resp = requests.head(url, headers={"User-Agent": UA}, timeout=8,
                             allow_redirects=True)
        if resp.status_code < 400:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=8, stream=True)
        chunk = next(resp.iter_content(1024), b"")
        code = resp.status_code
        resp.close()
        return code == 200 and len(chunk) > 0
    except Exception:  # noqa: BLE001
        return False


def check_collect(rec):
    url = (rec.get("url") or "").rstrip("/") + "/?ac=list"
    is_xml = "/at/xml/" in url or url.endswith(".xml")
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if resp.status_code != 200:
            return False
        text = resp.text.lstrip()
        if is_xml:
            return text.startswith("<?xml") and ("<video" in text or "<list" in text)
        data = json.loads(text)
        return isinstance(data, dict) and ("class" in data or "list" in data)
    except Exception:  # noqa: BLE001
        return False


CHECKERS = {
    "book": check_book,
    "subscribe": check_book,
    "tvbox": check_tvbox,
    "iptv": check_iptv,
    "collect": check_collect,
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


def cmd_validate(batch=400, types=None):
    store = load_store()
    targets = []
    for rec in store["sources"]:
        if types and rec["type"] not in types:
            continue
        hours = RECHECK_HOURS.get(rec["type"], 168)
        if rec.get("status") == "pending" or _age_hours(rec.get("last_check")) >= hours:
            targets.append(rec)
    targets = targets[:batch]
    if not targets:
        print("[done] 无待验证条目")
        return

    print(f"[info] 本轮 {len(targets)} 条")
    started = time.time()
    ok_n = fail_n = 0
    chunk_size = 60
    for i in range(0, len(targets), chunk_size):
        if time.time() - started > VALIDATE_MINUTES * 60:
            print("[stop] 软时限到，剩余条目下轮继续")
            break
        chunk = targets[i:i + chunk_size]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [(rec, pool.submit(CHECKERS.get(rec["type"], check_book), rec))
                       for rec in chunk]
            for rec, future in futures:
                try:
                    ok = bool(future.result())
                except Exception:  # noqa: BLE001
                    ok = False
                rec["last_check"] = now_iso()
                if ok:
                    rec["status"] = "valid"
                    rec["fail_count"] = 0
                    ok_n += 1
                else:
                    rec["fail_count"] = rec.get("fail_count", 0) + 1
                    fail_n += 1
                    if rec["fail_count"] >= FAIL_LIMIT:
                        rec["status"] = "invalid"
                    elif rec["status"] != "pending":
                        rec["status"] = "flaky"

    dead = [r for r in store["sources"] if r["status"] == "invalid"]
    if dead:
        store["archived"].extend(dead)
        store["sources"] = [r for r in store["sources"] if r["status"] != "invalid"]
        print(f"[arch] {len(dead)} 条归档")

    save_store(store)
    print(f"[done] 存活 {ok_n} / 失败 {fail_n}，耗时 {time.time() - started:.0f}s")


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


def cmd_export():
    store = load_store()
    cats = {"book": [], "subscribe": [], "tvbox": [], "iptv": [], "collect": []}
    tvbox_records = []
    for rec in store["sources"]:
        if rec["status"] not in ("valid", "flaky"):
            continue
        stype = rec["type"]
        if stype == "iptv":
            cats["iptv"].append({"name": rec["name"], "url": rec["url"]})
        elif stype == "tvbox":
            tvbox_records.append(rec)
        else:
            cats[stype].append(rec.get("source"))
    cats["tvbox"] = build_tvbox_config(tvbox_records)

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
    stats = {
        "total": len(store["sources"]) + len(store["archived"]),
        "valid_book": len(cats["book"]),
        "valid_subscribe": len(cats["subscribe"]),
        "valid_tvbox": len(cats["tvbox"].get("sites", [])),
        "valid_iptv": len(seen_streams),
        "valid_collect": len(cats["collect"]),
        "archived": len(archived),
        "upstreams_alive": sum(1 for v in store["upstreams"].values() if v.get("ok")),
        "upstreams_total": len(UPSTREAMS) + 1,
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
        "archive.json": json.dumps(archived, ensure_ascii=False, indent=1),
        "stats.json": json.dumps(stats, ensure_ascii=False, indent=1),
        "upstreams.json": json.dumps(store["upstreams"], ensure_ascii=False, indent=1),
    }
    for base in (DATA, DOCS):
        base.mkdir(parents=True, exist_ok=True)
        for filename, content in payloads.items():
            (base / filename).write_text(content, encoding="utf-8")
    print(f"[done] {stats}")


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
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--batch", type=int, default=400)
    p_validate.add_argument("--type", action="append", dest="vtypes",
                            help="只验证指定类型，可多次传参（book/subscribe/tvbox/iptv/collect）")
    sub.add_parser("export")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "fetch":
        cmd_fetch(args.force)
    elif args.cmd == "validate":
        cmd_validate(args.batch, args.vtypes or None)
    elif args.cmd == "export":
        cmd_export()
    elif args.cmd == "status":
        cmd_status()


if __name__ == "__main__":
    main()
