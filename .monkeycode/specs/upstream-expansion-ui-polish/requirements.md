# 上游补全与 UI 优化（feature: upstream-expansion-ui-polish）

## 调研结论（可用上游清单）

### 1. 在线观看（并入 `videosite` 类型，加 `subcat=online` 细分）
- **upstream**: `laoma2053/awesome-zhuiju-free` → `resources/resources.json`
  - category=`online_video` 共 52 条：`{name, url, summary, tags[]}`
  - 新增解析器 `parse_zhuiju(raw, origin, cat_filter)`，按 `category` 过滤
  - 导出物并入 `valid_videosite.json`（每条带 `subcat: "online"`，与 hccx 规则的 `subcat: "direct"` 区分）
  - 分类细分：在线观看标签页内加「类别」chips（在线播放 / 直连站 / 网盘搜索），按 `subcat` 筛选

### 2. 磁力影视（新增 type `magnet`）
- **upstream**: `laoma2053/awesome-zhuiju-free` → `resources/resources.json`
  - category=`magnet_search`（16 条磁力/BT 聚合站）+ category=`cloud_search`（4 条网盘搜索）→ 均归 `magnet` 类型
  - 导出物 `valid_magnet.json`
  - 分类细分：类别 chips（磁力/BT、网盘搜索），源格式统一为 `聚合搜索站`
  - 校验：`check_site_alive`（http_get 可达即 valid，不可达 flaky/dead）

### 3. 影视解析（新增 type `vparse`）
- **upstream**: `Lightconer/tvbox-ysc-config/output/*` 里 `parses[]` 字段
  - 4k.json（parses 17）/ feimao.json（4）/ ouge.json（11）/ wangerxiao.json（4）= 共 36 条
  - 新增解析器 `parse_tvbox_parses(raw, origin)`：只取 `parses[]` 里 `type:1` 且 `url` 不是 `Demo`/`Web` 的条目
  - 导出物 `valid_vparse.json`（`[{name, url, flags[]}]`）
  - 分类细分：按 `ext.flag` 集合自动归并主题（爱腾芒 / 优酷 / 全网聚合等）；源格式统一 `TVBox 解析接口`
  - 校验：对 `url` 尾部拼一个测试 URL 做 `http_get`，返回 200 即 valid

### 4. 音乐解析（并入 `music` 类型，加 `subcat=parse` 细分）
- **upstream**:
  - `guoyue2010/lxmusic-` → `V260907/`（洛雪最新，18 条 .js）— lxtree 模式，需扩展 `fetch_music_tree` 支持指定目录（非自动取最新 V*）
  - `wzh15802/lxmusic`（根目录 15 条 .js）— musicfree/lx 直接 flat .js，新增 `kind=musicflat`
  - `Huibq/keep-alive` → `Music_Free/`（5 条 .js + allPlugins.json）— musicfree 模式
  - 导出物并入 `valid_music.json`（带 `subcat: "parse"`，与现有音源 `subcat: "source"` 区分）
  - 分类细分：类别 chips（洛雪源 / MusicFree 插件 / 聚合接口）；源格式 `.js 音源插件`

### 5. 影视本地包（新增 type `localpkg`）
- **upstream**: 网盘搜索站（kkso.net / zhuiju.us / gugeso.com 等，来自 zhuiju `cloud_search`）
  - 这些是「在线网盘搜索/聚合站」，属于"影视本地包"的获取入口
  - 导出物 `valid_localpkg.json`
  - 分类细分：类别 chips（网盘搜索 / 离线包仓库）；源格式 `搜索站`
  - 校验：`http_get` 可达即 valid

## 上游补全清单（新增 ~12 个 upstream 条目）

| 名称 | url | type | kind | 预计条数 |
|------|-----|------|------|---------|
| 在线观看·zhuiju在线 | raw.../laoma2053/awesome-zhuiju-free/main/resources/resources.json | videosite | zhuiju·online_video | 52 |
| 磁力·zhuiju磁力 | raw.../laoma2053/awesome-zhuiju-free/main/resources/resources.json | magnet | zhuiju·magnet_search | 16 |
| 磁力·zhuiju网盘 | raw.../laoma2053/awesome-zhuiju-free/main/resources/resources.json | magnet | zhuiju·cloud_search | 4 |
| 影视解析·肥猫4k | raw.../Lightconer/tvbox-ysc-config/main/output/4k.json | vparse | tvbox_parses | 17 |
| 影视解析·肥猫ouge | raw.../Lightconer/tvbox-ysc-config/main/output/ouge.json | vparse | tvbox_parses | 11 |
| 影视解析·肥猫wangerxiao | raw.../Lightconer/tvbox-ysc-config/main/output/wangerxiao.json | vparse | tvbox_parses | 4 |
| 音乐解析·guoyue洛雪 | https://github.com/guoyue2010/lxmusic- | music | lxtree(指定目录V260907) | 18 |
| 音乐解析·wzh flat | https://raw.githubusercontent.com/wzh15802/lxmusic | music | musicflat | 15 |
| 音乐解析·Huibq MusicFree | raw.../Huibq/keep-alive/master/Music_Free/allPlugins.json | music | musicfree | ~5 |
| 本地包·kkso | https://kkso.net/ | localpkg | site_alive | 1 |
| 本地包·zhuiju.us | https://www.zhuiju.us/ | localpkg | site_alive | 1 |
| 本地包·gugeso | https://gugeso.com/ | localpkg | site_alive | 1 |

## UI 优化清单

### 分类展示（合并 + 细分）
- 每个资源类型标签页顶部加 **类别 chips**（从 `subcat` / `category` 聚合，可合并）
- 标签页内加 **源格式说明行**（`parses` = TVBox 解析接口、`.js` = 音源插件等）
- 同上游重复条目合并（`dedup_key` 已按 url+type 去重）
- 搜索框支持 `name/url/subcat` 三字段联合搜索
- 表格列：# / 名称 / **类别**（badge）/ 地址 / 操作（复制）
- 每个标签页右下角显示「共 N 条（M 绿 / K 黄）」

### 界面美化（保持深空霓虹玻璃拟态主题）
- chips 圆角 999px + hover 发光 + 选中霓虹边框
- 类别 badge 按类型配色（magnet=橙、vparse=紫、music=绿、localpkg=蓝）
- 表格 hover 行高亮 + 复制按钮悬浮放大
- 统计卡 `stat` 加 icon + 渐变数字（现有已实现，保留）
- 标签页 active 态加顶部渐变条
- 响应式：<560px 时 chips 横滑（`overflow-x:auto`）

### 标签页结构（8 个）
| tab | 类型 | 文件 |
|-----|------|------|
| 书源 | book | valid.json |
| 订阅源 | subscribe | valid_subscribe.json |
| TVBox | tvbox | valid_tvbox.json |
| IPTV | iptv | valid_iptv.m3u |
| 采集 | collect | valid_collect.json |
| 影视直连站 | videosite（含 online） | valid_videosite.json |
| 音源 | music（含 parse） | valid_music.json |
| 磁力 | magnet | valid_magnet.json |
| 影视解析 | vparse | valid_vparse.json |
| 本地包 | localpkg | valid_localpkg.json |
| + 用户上传 | upload | - |

（共 10 个资源 tab + 1 个上传 tab）

## 数据模型扩展

```json
// store.sources 每条新增字段
{
  "type": "magnet",        // book/subscribe/tvbox/iptv/collect/videosite/music/magnet/vparse/localpkg
  "url": "...",
  "name": "...",
  "subcat": "magnet_search", // 类别细分：
                             //   videosite = hccx_rule / online_video
                             //   music     = music_source / music_parse
                             //   magnet    = magnet_search / cloud_search
                             //   localpkg  = cloud_search
                             //   vparse    = parse_iface
  "kind": "site_alive",     // 源格式标识（tvbox_parses/musicflat/lxtree/...）
  "source": {...},          // 原始 raw
  "status": "pending"
}

// 导出物（统一带 subcat + origin）
// valid_magnet.json:   [{name, url, subcat, origin, flags[]}]
// valid_vparse.json:   [{name, url, subcat:"parse_iface", origin, flags[]}]
// valid_localpkg.json: [{name, url, subcat:"cloud_search", origin}]
// valid_videosite.json: 展开 source 字段 + subcat（hccx_rule/online_video）+ origin
// valid_music.json:     展开 source 字段 + subcat（music_source/music_parse）+ origin
```

> subcat 兜底规则：旧库存条目缺 subcat 时由 `_legacy_subcat` 按 type + origin 名迁移补齐
> （幂等，不覆盖已有值）；导出侧 `build_flat_config` 把 `site_alive/空` 归并到 `cloud_search`。

## keeper.py 改动点
1. `recheck_hours` 加 `magnet/vparse/localpkg` 3 个 key（各 360h）
2. `CHECKERS` 加 `check_magnet`（site_alive）、`check_vparse`（http_get url+test）、`check_localpkg`（site_alive）
3. 解析器 `parse_zhuiju` / `parse_tvbox_parses` / `parse_localpkg` 三个新函数（均写 subcat）
4. `dedup_key`：magnet/vparse/localpkg 用 url+type；videosite/music 维持现状
5. `build_flat_config`（磁力/本地包/解析）+ `_flat`（videosite/music 展开 source）导出新 json，统一带 subcat/origin
6. `cmd_export` 加 3 个新导出物 + stats 加 3 个新计数
7. `load_store` 加 `_legacy_subcat` 迁移：为新 5 类条目补 subcat（幂等）
