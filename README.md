# shuyuan-keeper

## 免责声明

> 访问本仓库即视为您已知晓并同意 [完整条款](./DISCLAIMER.md)：本仓库仅供个人学习、研究、备份；全部资源版权归原权利人所有；禁止商用、二次分发、搬运；内容随时可能删除，使用风险自负。

**禁止** Fork / 克隆 / 镜像 / 搬运本仓库；**禁止** 售卖、付费传播、引流变现；**禁止** 二次分发或打包转载。侵权反馈请通过站长邮箱提交。

---

把社区已维护的聚合仓库作为上游，聚合 7 类资源，做二次验真后按类型导出，供各 App 直接订阅。

- 书源 / 订阅源：阅读 Legado
- TVBox / 影视仓：单仓配置 JSON（含 T4 接口配置、猫源/肥猫配置）
- IPTV：M3U 播放列表（VLC / Kodi / DIYP / TVBox）
- 采集接口：苹果CMS / 空壳影视
- 影视直连站：drpy/HCCX 规则映射出的可直连影视站
- 音源：洛雪 LX / MusicFree 音源（.js 插件订阅）

## 目录结构

```
shuyuan-keeper/
├── config/sources.json          上游清单与参数
├── scripts/keeper.py            聚合 / 验证 / 导出
├── data/                        运行状态（store.json 不入库，靠 Actions cache 持久化）
├── docs/                        站点页面 index.html（导出 json 运行时生成、不入库）
├── .github/workflows/update.yml 定时任务与 Pages 部署
└── requirements.txt
```

## 本地运行

```bash
cd shuyuan-keeper

# 安装依赖
pip install -r requirements.txt

# 拉取上游（每 8 天一次；窗口内自动跳过）
python scripts/keeper.py fetch

# 拉取且只收新增（已入库条目不重复合并，版本升级仍生效）
python scripts/keeper.py fetch --skip-known

# 强制全量拉取（绕过 8 天窗口）
python scripts/keeper.py fetch --force

# 验证（按类型差异化，默认上限 400 条；有效期 15 天）
python scripts/keeper.py validate --batch 800

# 全量验证（无视 15 天有效期，所有条目重新探活）
python scripts/keeper.py validate --all

# 导出到 data/ 与 docs/
python scripts/keeper.py export

# 查看库存状态
python scripts/keeper.py status
```

本地预览展示页（导出后）：

```bash
cd docs
python -m http.server 8080
```

## 部署到 GitHub Pages

1. 新建仓库并推送本项目。
2. 仓库 Settings → Pages → Build and deployment → Source 选择 `GitHub Actions`。
3. Settings → Actions → General → Workflow permissions 选择 `Read and write permissions`。
4. 手动触发一次 `update-and-deploy` 工作流（默认 force=true），等待 Pages 部署完成。

工作流每天 18:01（北京时间）自动运行一次，拉取上游、验证、导出，并把站点同步到 cPanel 主机与 GitHub Pages。校验状态 `data/store.json` 通过 Actions cache 在多次运行间持久化，生成文件不进入 git。

## 各 App 的订阅链接

部署完成后得到下面这套地址（把 `你的用户名` 和 `仓库` 替换为实际值）：

| 目标 App | 使用的链接 | 在 App 里怎么填 | 更新机制 |
| --- | --- | --- | --- |
| 阅读 Legado（书源） | `https://你的用户名.github.io/仓库/valid.json` | 书源管理 → 右上角 → 网络导入 → 粘贴 | 网络导入是一次性的；较新版 Legado 可在书源管理里开启「订阅书源」定时刷新同一 URL |
| 阅读 Legado（订阅源） | `https://你的用户名.github.io/仓库/valid_subscribe.json` | 我的 → 订阅 → 右上角 → 网络导入 | 订阅页支持自动/手动刷新，每次拉取最新列表 |
| TVBox / 影视仓 | `https://你的用户名.github.io/仓库/valid_tvbox.json` | 设置 → 配置地址 → 粘贴 | 每次启动或点「刷新配置」都会重新拉取 |
| IPTV 播放器（VLC/Kodi/DIYP） | `https://你的用户名.github.io/仓库/valid_iptv.m3u` | 播放列表/直播源设置里填 M3U 地址 | 刷新播放列表时重新加载 |
| 苹果CMS / 空壳影视 | `https://你的用户名.github.io/仓库/valid_collect.json` | 采集接口配置里填 JSON 地址 | 手动更新配置时重新拉取 |
| 洛雪 LX / MusicFree | `https://你的用户名.github.io/仓库/valid_music.json` | 音源列表 / 插件订阅里填下面 JSON 地址 | 每次刷新音源列表时重新拉取 |

GitHub Pages 首页地址：

```
https://你的用户名.github.io/仓库/
```

首页按 7 个标签页展示，每条链接支持复制、下载与二维码，书源与订阅源还带「一键导入阅读APP」按钮。

## 国内访问加速

页面与数据走 jsDelivr 镜像（缓存约 12 小时）：

```
https://cdn.jsdelivr.net/gh/你的用户名/仓库@main/docs/valid_tvbox.json
```

追求实时用 Pages 或 `raw.githubusercontent.com` 直链，追求速度用 jsDelivr。

## 验证策略

上游仓库自身已完成每日验活，本仓库做二次复核，并按类型差异化检测：

| 类型 | 检测方式 | 有效期 |
| --- | --- | --- |
| book / subscribe | HTTP 可达 + searchUrl 探测 | 15 天 |
| tvbox | 配置结构完整性；多仓子项探活 sourceUrl（T4 的 type:4 接口配置走同一逻辑） | 15 天 |
| iptv | 流地址 HEAD / GET 可达 | 15 天 |
| collect | `?ac=list` 返回 JSON | 15 天 |
| videosite | 站点直连可达 | 15 天 |
| music | 音源 .js 文件可达且非 HTML 错误页 | 15 天 |

音源上游按来源形态分四种解析：MusicFree 插件订阅 JSON（`plugins:[]`）、洛雪聚合仓库 README 里的 raw .js 链接、单文件 .js、以及洛雪仓库最新版本目录（形如 `V260817`）下的全部 .js（走 GitHub API 枚举，Actions 里用 `GITHUB_TOKEN` 提高限额）。

复验结果分三级：

| 结果 | 含义 | 处理 |
| --- | --- | --- |
| 绿 valid | 规则与站点都正常 | 正常导出，15 天内不再重复检验 |
| 黄 flaky | 站点还在，仅规则/接口失效 | 标黄保留，不计死亡 |
| 红 dead | 站点整体不可达 | 连续 3 次后自动删除，并记墓碑防止再次入库 |

## 调度节奏

- **上游拉取**：每 8 天一次（`fetch_gap_days=8`），在窗口外自动跳过；拉取时默认 `--skip-known`，只收新增条目，已入库条目不重复合并（版本升级仍由 upstream status 记录体现）。
- **校验窗口**：每天北京时间 18:00 触发（GitHub cron `0 10 * * *` UTC），窗口 18:00 至次日 05:50；**隔一天不校验**——用 `store.last_validate_day` 记录上次校验日期，与今天相隔 ≥ 2 天才再次进入校验。
- **有效期**：valid 条目 15 天内不重复检验，到期后由下次校验重新探活（`recheck_hours=360`）。
- **全量复核**：`validate --all` 无视 15 天有效期、所有条目重新探活，手动触发用于周期性彻底复核。
