### cPanel 主机部署 (17970.my-place.us)
- Web 根 = FTP htdocs/，FTP 服务器 ftpupload.net:21
- 站点文件：docs/ 下的页面与数据文件由 Actions 导出后 FTP 推送至 htdocs/
- 站点自包含化：index.html 已移除所有 GitHub 引用（侵权反馈改 mailto、上传 tab 文案去 Issue 化），仓库删除不影响主机运行
- 主机端无 SSH/cPanel 面板可用，更新只能走 FTP 或 GitHub Actions 推送
- update.yml 的 "Sync site to cPanel host (FTP)" 步骤读 secrets CPANEL_FTP_HOST/USER/PASS，用标准库 ftplib 把 docs/ 推到 htdocs/
- GitHub secrets 已配置：CPANEL_FTP_HOST=ftpupload.net、CPANEL_FTP_USER、CPANEL_FTP_PASS

### 运行状态持久化（data 不入库）
- `data/store.json`（曾 22MB）及所有导出 json 已移出 git（.gitignore），站点 `docs/*.json` 运行时生成
- 状态改由 update.yml 的 `actions/cache` 持久化：key `keeper-store-${{ github.run_id }}`，restore-keys 前缀 `keeper-store-`（滚动缓存，每次运行新建 key 并恢复上一轮）
- 缓存过期或丢失时，下次 fetch 会从上游重建库存，可自愈，只是验证进度重来

### 校验分三级 + 失效自动删除
- valid=规则与站点都正常；flaky=站点还在但规则/接口失效（标黄保留）；dead=站点整体不可达
- dead 连续 3 次（fail_limit）后自动删除，并写入 `store["dead"]` 墓碑（dict: key→时间戳），30 天内不再入库，过期允许上游重新带回
- `site_alive()` 对国内证书链不完整站点做降级（verify=False、https→http 回退），避免误判为 dead
- 上游总数统计统一用 `len(store["upstreams"])`

### 音源(music)类型 + T4/猫源上游
- 音源为独立 `music` 类型，导出 `valid_music.json`（[{name,url,version}]），LoXue/LX 与 MusicFree 插件都收
- `parse_music` 按 `kind` 分派：musicfree(plugins.json 的 plugins:[])、lxreadme(README 提取 raw .js)、single(单个 .js)、lxtree(GitHub API 枚举仓库最新版 V* 目录下的 .js，去重全 URL)
- T4 = TVBox 的 type:4 接口配置，直接并入 `tvbox` 类型（ediart/tvbox、tlswch/zzzgit_zzz 的 T4.json）；猫源/肥猫 = Lightconer/tvbox-ysc-config 的 output/feimao.json，并入 `tvbox`
- 影视在线源 = 现有 `videosite` 批量（liu673cn/box 的 hccx 规则目录）
- `loads_lenient` 能解析带 // 注释的 TVBox 配置；`dedup_key` 对 music 按全 URL 去重（同 CDN 多插件）

### 已知坑：agent 注入的 credential helper 500
- 环境用 GIT_CONFIG_KEY_0 强制注入 /app/agent/bin/agent git-credential-helper，git push 时它返回 500 并覆盖 store helper，导致无法推送
- 绕过方案：git remote set-url origin "https://x-access-token:<有效PAT>@github.com/..." 用 URL 内嵌 token，推后还原干净 URL
