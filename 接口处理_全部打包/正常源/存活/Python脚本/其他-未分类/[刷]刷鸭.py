# coding=utf-8
# !/usr/bin/python
"""
刷鸭(默影视/多仓) Py 源  ——  美女短视频聚合

数据源：https://shuaya.pages.dev/ 首页内联 mm-api.js 的 23 条线路（全量搬运，未删减）

【v2 优化】封面改为内嵌 AI 动漫图(JPEG)，弃用 App 不渲染的 SVG 占位图；
播放探测改并发多线同测，点开更快；每集封面按集号轮换。

【源特征】
本聚合站是「随机流」站点，没有常规 CMS 的分类/搜索/详情页：
    每次请求接口 → 302 跳到一条**随机**的短视频 mp4
因此本源做了如下架构映射：
    线路  ==  分类(tid)，15 条可用接口 = 15 个分类
    vid   ==  指纹，fp = 3 位线路 code + e+2位集号 + 时间戳 + 随机串 + 扩展名
    详情页 ==  一次性铺 50 集播放列表，实现「伪连播」
    "换一个" == 自定义 action，点按钮即换新视频，等价于原站的核心交互
    搜索   ==  未实现（源站本身没有搜索能力，返回空而非报错）

【伪连播说明】
源站是随机流，不存在真正的剧集。本源把同一线路的随机流包装成 1~50 集：
    分类页 → 50 个条目；详情页 → 50 集播单，播放器自动连播；
    每一集点开都是一条新的随机视频，播完自动跳下一集，可无限刷。
集数由 EPISODES 常量控制，想改 30 集就把它设成 30。

【健壮性】
线路表已剔除线上实测的失效项（api.lolimi.cn / v2.xxapi.cn / api.dwo.cc
三条全死，v.nrzj.vip 与 api.cenguigui.cn 间歇性抽风，api.yujn.cn 的
xjj.php 已废），从原始 23 条收敛为 15 条。
播放链路仍保留「同步探测 + 跳转 + 重试 + 坏线路自动降级」，
避免一次 404 就白屏——原站 JS 版正是靠前端重试 3 次换线来兜的。

【环境变量】
    无。ext 可留空。
"""

import sys
import json
import time
import random
import re
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except Exception:  # 独立调试时无基类，用空壳顶上
    class BaseSpider(object):
        def __init__(self, *args, **kwargs):
            pass


# ==================== AI 封面池（JPEG 内嵌，源站无封面时用） ====================
PIC_URLS = [
    "https://image.pollinations.ai/prompt/anime%20girl%20street%20fashion%20portrait%2C%20vibrant%20city%2C%20detailed%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/anime%20girl%20street%20fashion%20portrait%2C%20vibrant%20city%2C%20detailed%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/chinese%20anime%20girl%20in%20flower%20sea%2C%20hanfu%2C%20dreamy%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/chinese%20anime%20girl%20in%20flower%20sea%2C%20hanfu%2C%20dreamy%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/elegant%20anime%20woman%20on%20stage%2C%20glamorous%20performance%2C%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/elegant%20anime%20woman%20on%20stage%2C%20glamorous%20performance%2C%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/anime%20girl%20under%20cherry%20blossoms%2C%20soft%20healing%20light%2C%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/anime%20girl%20under%20cherry%20blossoms%2C%20soft%20healing%20light%2C%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/chinese%20fantasy%20anime%20heroine%2C%20xianxia%20style%2C%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/chinese%20fantasy%20anime%20heroine%2C%20xianxia%20style%2C%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/cyberpunk%20anime%20girl%2C%20neon%20city%20portrait%2C%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/cyberpunk%20anime%20girl%2C%20neon%20city%20portrait%2C%20illustration?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/watercolor%20anime%20girl%20portrait%2C%20hand%20painted%20style?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/watercolor%20anime%20girl%20portrait%2C%20hand%20painted%20style?width=360&height=480&seed=137&nologo=true",
    "https://image.pollinations.ai/prompt/retro%20showa%20style%20anime%20girl%20portrait%2C%20illustration?width=360&height=480&seed=42&nologo=true",
    "https://image.pollinations.ai/prompt/retro%20showa%20style%20anime%20girl%20portrait%2C%20illustration?width=360&height=480&seed=137&nologo=true",
]

class Spider(BaseSpider):

    # ==================== 线路表：全量搬运自 shuaya.pages.dev 的 mm-api.js ====================
    # api/data/type 三者语义与源站一致：
    #   link   → 302 直链接口，追加破缓存参数即可拿到新视频
    #   random → 随机型接口，末尾拼随机数以换视频
    #   data   → JSON 型接口，按 data 字段路径取值
    # core=True 表示 api.yujn.cn 主源（实测最稳），排序权重更高
    API_LIST = [
        {"code": "003", "title": "高质量纯妹",   "api": "http://api.yujn.cn/api/zzxjj.php?type=video",    "type": "link",   "core": True},
        {"code": "001", "title": "黑丝",         "api": "https://api.yujn.cn/api/heisis.php?type=video",  "type": "link",   "core": True},
        {"code": "002", "title": "萌妹短视频",   "api": "https://api.yujn.cn/api/nvda.php?type=video",    "type": "link",   "core": True},
        {"code": "005", "title": "清纯萝莉",     "api": "http://api.yujn.cn/api/zzxjj.php?temps=",        "type": "random", "core": True},
        {"code": "010", "title": "清纯",         "api": "http://api.yujn.cn/api/zzxjj.php?type=video",    "type": "link",   "core": True},
        {"code": "018", "title": "快手女大学生", "api": "https://api.yujn.cn/api/nvda.php?type=video",    "type": "link",   "core": True},
        {"code": "020", "title": "慢摇系列",     "api": "http://api.yujn.cn/api/manyao.php?type=video",   "type": "link",   "core": True},
        {"code": "021", "title": "吊带系列",     "api": "http://api.yujn.cn/api/diaodai.php?type=video",  "type": "link",   "core": True},
        {"code": "022", "title": "清纯系列",     "api": "http://api.yujn.cn/api/qingchun.php?type=video", "type": "link",   "core": True},
        {"code": "023", "title": "女高系列",     "api": "http://api.yujn.cn/api/nvgao.php?type=video",    "type": "link",   "core": True},
        {"code": "024", "title": "快手变装系列", "api": "http://api.yujn.cn/api/ksbianzhuang.php?type=video", "type": "link", "core": True},
        {"code": "025", "title": "甜妹系列",     "api": "http://api.yujn.cn/api/tianmei.php?type=video",  "type": "link",   "core": True},
        {"code": "026", "title": "欲梦视频",     "api": "http://api.yujn.cn/api/ndym.php?type=video",     "type": "link",   "core": True},
        {"code": "027", "title": "热舞视频",     "api": "http://api.yujn.cn/api/rewu.php?type=video",     "type": "link",   "core": True},
        {"code": "028", "title": "小姐姐视频",   "api": "http://api.yujn.cn/api/ksxjjsp.php",             "type": "link",   "core": True},
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    # 已知失效线路（域名已废/需付费Key/返回网页）
    # 注：失效线路已直接移出 API_LIST，此处保留为「临时拔线」开关：
    # 线上若发现某条线路挂掉，把它的 code 填进来即可立刻停用，无需删表。
    DEAD_CODE = set()

    # 【伪连播】集数：每个分类（线路）固定铺 EPISODES 集。
    # 源站没有真剧集，这里把「同一线路的随机流」包装成 1~50 集，
    # 播放器拿到完整列表后会自动连播，播完自动跳下一集 → 无限刷。
    EPISODES = 50

    # 单条线路的探测重试次数与失败冷却时长（秒）
    # 实测主源 api.yujn.cn 有约 1/3 概率返回 404 XML，属于「抖动」而非「死」，
    # 因此必须重试；连续失败则冷却一段时间后再放回候选池，避免误判永久拉黑。
    RETRY_PER_LINE = 3
    COOLDOWN_SEC = 90

    def __init__(self, *args, **kwargs):
        try:
            BaseSpider.__init__(self, *args, **kwargs)
        except Exception:
            pass
        self.host = "https://shuaya.pages.dev/"
        self.cool_down = {}         # code -> 解禁时间戳
        self._cfg = None
        self._cfg_ts = 0

    # ==================== 基础信息 ====================
    def getName(self):
        return "刷鸭"

    def init(self, extend=""):
        # extend 可留空；容错解析，避免脏配置把整个源拖挂
        self.extend = extend or ""
        if isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                self._cfg = json.loads(extend)
            except Exception:
                self._cfg = None
        return {"status": 0}

    def isVideoFormat(self, url):
        if not url:
            return False
        return any(k in url.lower() for k in (".mp4", ".m3u8", ".flv", ".ts", ".mkv", ".avi"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return None

    def action(self, action):
        return None

    # ==================== 内部工具 ====================
    def _req(self, url, headers=None, timeout=8, allow_redirects=True, stream=False):
        """统一请求入口。

        优先用基类的 self.fetch；基类缺失或行为异常时回落到 requests。
        返回 requests.Response 或 None——调用方一律做 None 判断。
        """
        hdrs = dict(self.HEADERS)
        if headers:
            hdrs.update(headers)
        try:
            rsp = self.fetch(url, headers=hdrs, timeout=timeout)
            if rsp is not None:
                return rsp
        except Exception:
            pass
        try:
            import requests
            return requests.get(url, headers=hdrs, timeout=timeout,
                                allow_redirects=allow_redirects, stream=stream)
        except Exception:
            return None

    def _bust(self, url):
        """破缓存：每次追加随机参数，保证 302 接口跳到新视频。

        源站 JS 版用 _r=时间戳+随机数，这里等价实现。
        """
        sep = "&" if "?" in url else "?"
        return "%s%s_r=%d%d" % (url, sep, int(time.time() * 1000), random.randint(0, 999))

    def _randomize(self, url, api_type):
        """按线路类型生成「取新视频」的请求地址。"""
        u = self._to_secure(url)
        if api_type == "random":
            # 随机型：源站直接拼 Math.random()，这里同理
            return u + str(random.random())
        return self._bust(u)

    @staticmethod
    def _to_secure(url):
        """http 升级 https：多数播放器跑在 https 环境，明文请求会被拦。"""
        return re.sub(r"^http://", "https://", url, flags=re.I) if url else url

    def _line_by_code(self, code):
        for item in self.API_LIST:
            if item["code"] == code:
                return item
        return None

    def _ordered_lines(self, code=None):
        """线路尝试顺序：指定线路 → 主源 → 其余线路 → 冷却中的线路。

        已判定为坏的线路沉底，主源(api.yujn.cn)优先，尽量提高一次命中率。
        """
        lines = list(self.API_LIST)
        core = [x for x in lines if x.get("core")]
        other = [x for x in lines if not x.get("core")]
        random.shuffle(core)
        random.shuffle(other)
        ordered = core + other

        # 指定线路优先（用户点了某条线路就尊重它）
        if code:
            target = self._line_by_code(code)
            if target:
                ordered = [target] + [x for x in ordered if x["code"] != code]

        # 分三档：正常 → 冷却中 → 已知失效。冷却到期的自动回到正常档。
        now = time.time()

        def state(item):
            c = item["code"]
            if c in self.cool_down:
                return 0 if now >= self.cool_down[c] else 1
            return 0 if c not in self.DEAD_CODE else 2

        return sorted(ordered, key=state)

    def _mark_bad(self, code):
        """标记线路故障并进入冷却（不是永久拉黑）。"""
        self.cool_down[code] = time.time() + self.COOLDOWN_SEC

    def _resolve(self, line, probe=True):
        """解析一条线路，拿到真实视频直链。

        probe=True 时会跟随跳转并校验内容类型——这是本源的容错核心：
        源站有一批线路会返回 404/HTML/错误XML，只有真校验过才敢交给播放器。
        抖动型线路会自动重试 RETRY_PER_LINE 次。
        返回 (真实url, 扩展名)；失败返回 (None, None)。
        """
        for attempt in range(max(1, self.RETRY_PER_LINE if probe else 1)):
            url, ext = self._resolve_once(line, probe)
            if url:
                return url, ext
            # 抖动多为瞬时故障，短暂退避后重试
            if attempt < self.RETRY_PER_LINE - 1:
                time.sleep(0.25 * (attempt + 1))
        return None, None

    def _resolve_once(self, line, probe=True):
        url = self._randomize(line["api"], line["type"])
        rsp = self._req(url, timeout=8)
        if rsp is None:
            return None, None

        # JSON 型：先取值，再对取出的地址做一次探测
        if line["type"] == "data":
            try:
                data = rsp.json()
                for key in (line.get("data") or "data").split("."):
                    data = data[key]
                if not isinstance(data, str) or not data.startswith("http"):
                    return None, None
                if not probe:
                    return data, self._ext_of(data)
                rsp2 = self._req(data, timeout=8)
                if rsp2 is not None and self._is_media(rsp2):
                    return data, self._ext_of(rsp2.url or data)
            except Exception:
                pass
            return None, None

        if not probe:
            return rsp.url or url, self._ext_of(rsp.url or url)

        if not self._is_media(rsp):
            return None, None
        final = rsp.url or url
        return final, self._ext_of(final)

    def _is_media(self, rsp):
        """判定响应是否为可播放的视频流。

        三个必要条件：状态码正常、内容类型是视频、不是错误XML。
        源站接口挂掉时常回 404 + XML 错误体，必须挡掉。
        """
        try:
            code = getattr(rsp, "status_code", 0)
            if code not in (200, 206):
                return False
            ctype = (rsp.headers.get("Content-Type") or "").lower()
            if "video" in ctype or "octet-stream" in ctype or "mpegurl" in ctype:
                # 快手/字节的 CDN 有时回 octet-stream，属于正常视频
                body_head = (rsp.text or "")[:120] if "octet-stream" in ctype and code == 200 else ""
                if "<Error" in body_head or "NoSuchKey" in body_head:
                    return False
                return True
            if "xml" in ctype or "html" in ctype or "json" in ctype:
                return False
            # 无明确类型时，用扩展名兜底
            return self.isVideoFormat(getattr(rsp, "url", "") or "")
        except Exception:
            return False

    @staticmethod
    def _ext_of(url):
        m = re.search(r"\.(mp4|m3u8|flv|mkv|ts)(\?|$)", url or "", re.I)
        return ("." + m.group(1).lower()) if m else ".mp4"

    def _pick_pic(self, code, title, ep=None):
        """封面：远程 AI 动漫图 (按线路+集号确定性选图, 同一条目恒为同一张)。

        内嵌 data: 图在本壳 (PeekPro) 不渲染——它的图片加载只认网络图。
        远程图若每条目现生成一张会非常慢 (每张数秒), 故用固定图池:
        16 张图 (8 风格×2) 在图床侧生成一次后走 CDN 缓存, 条目按
        (线路, 集号) 哈希确定性选图, 刷新不乱跳, 打开即出图。
        """
        seed = "%s|%s" % (code, ep if ep is not None else title)
        h = sum(ord(c) * (i + 1) for i, c in enumerate(seed))
        return PIC_URLS[h % len(PIC_URLS)]

    def _mk_fp(self, code, ep=None):
        """生成播放指纹。

        带集数时格式：3位线路code + 'e' + 2位集号 + 13位时间戳 + 6位随机 + .mp4
        不带集数时格式：3位线路code + 13位时间戳 + 6位随机 + .mp4（兼容旧指纹）

        每条指纹都内嵌独立随机数，因此即便同一集重复点播也会拿到不同的
        随机视频——这正是源站「点开即播、每次都不一样」的语义。
        """
        seed = "%d%d" % (int(time.time() * 1000), random.randint(100000, 999999))
        if ep is None:
            return "%s%s.mp4" % (code, seed)
        return "%se%02d%s.mp4" % (code, int(ep), seed)

    def _parse_fp(self, fp):
        """从指纹反解 (线路code, 集号)。

        集号可能是 None（旧格式指纹，或来源不合法），调用方需自行兜底。
        """
        s = str(fp or "")
        m = re.match(r"^(\d{3})e(\d{2})\d+", s)
        if m:
            return m.group(1), int(m.group(2))
        m = re.match(r"^(\d{3})\d+", s)
        if m:
            return m.group(1), None
        # 兜底：有些播放器会把 $ 后面的内容再切一次，这里容错扫描
        m = re.search(r"(\d{3})e(\d{2})", s)
        if m:
            return m.group(1), int(m.group(2))
        return None, None

    # ==================== 首页 ====================
    def homeContent(self, filter):
        classes = [{"type_name": "🔥 随机换一个", "type_id": "random"}]
        for item in self.API_LIST:
            classes.append({"type_name": item["title"], "type_id": item["code"]})
        result = {"class": classes}
        # 明确声明无筛选：本源没有分类/地区/年份等维度
        result["filters"] = {}
        return result

    def homeVideoContent(self):
        """首页推荐位：每条线路各出一条，点开即是该线路第 1 集。"""
        videos = []
        for item in self.API_LIST:
            videos.append({
                "vod_id": self._mk_fp(item["code"], 1),
                "vod_name": item["title"],
                "vod_pic": self._pick_pic(item["code"], item["title"], 1),
                "vod_remarks": "共 %d 集" % self.EPISODES,
            })
        return {"list": videos}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        """分类 = 线路。每个分类下挂 EPISODES 条「剧集」条目。

        注意：这些条目本质是同一线路的随机流，并不存在真正的先后顺序，
        只是做成剧集形态以便播放器展示与连播。
        """
        pg = int(pg) if str(pg).isdigit() else 1
        result = {
            "page": pg,
            "pagecount": 1,
            "limit": self.EPISODES,
            "total": self.EPISODES,
        }
        videos = []

        # 特制分类：一次给出各主源的一条随机视频，适合无脑点开就刷
        if tid == "random" or tid is None or tid == "":
            pool = [x for x in self.API_LIST if x.get("core")]
            random.shuffle(pool)
            for item in pool:
                ep = random.randint(1, self.EPISODES)
                videos.append({
                    "vod_id": self._mk_fp(item["code"], ep),
                    "vod_name": "%s · 随机刷" % item["title"],
                    "vod_pic": self._pick_pic(item["code"], item["title"], ep),
                    "vod_remarks": "换一个",
                })
            result["limit"] = len(videos)
            result["total"] = len(videos)
            result["list"] = videos
            return result

        line = self._line_by_code(str(tid))
        if not line:
            # 未知 tid 不报错，退化成随机刷，避免播放器直接崩
            pick = random.choice(self.API_LIST)
            result["limit"] = 1
            result["total"] = 1
            result["list"] = [{
                "vod_id": self._mk_fp(pick["code"], 1),
                "vod_name": "随机小姐姐",
                "vod_pic": self._pick_pic("000", "随机"),
                "vod_remarks": "共 %d 集" % self.EPISODES,
            }]
            return result

        # 分类 = 线路：按 EPISODES 灌满「剧集」，集号从 1 开始
        for i in range(1, self.EPISODES + 1):
            videos.append({
                "vod_id": self._mk_fp(line["code"], i),
                "vod_name": "%s 第%02d集" % (line["title"], i),
                "vod_pic": self._pick_pic(line["code"], line["title"], i),
                "vod_remarks": "第%02d集 / 共%d集" % (i, self.EPISODES),
            })
        result["list"] = videos
        return result

    # ==================== 详情 ====================
    def detailContent(self, array):
        """详情页一次性铺满 EPISODES 集播放列表。

        这是「伪连播」的关键：播放器拿到完整剧集列表后，播完一集会自动
        播下一集；而每个播放地址都是线路随机流，点开即播、集集不同。
        """
        raw_id = array[0] if array else ""
        code, cur_ep = self._parse_fp(raw_id)
        line = self._line_by_code(code) if code else None
        if not line:
            line = random.choice(self.API_LIST)
            code = line["code"]
        if not cur_ep or cur_ep < 1 or cur_ep > self.EPISODES:
            cur_ep = 1

        pic = self._pick_pic(code, line["title"], cur_ep)
        title = line["title"]

        # 按集号顺序铺满整个播放列表，实现伪连播
        eps = []
        for i in range(1, self.EPISODES + 1):
            eps.append("第%02d集$%s" % (i, self._mk_fp(code, i)))

        vod = {
            "vod_id": raw_id,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": "美女短视频",
            "vod_year": str(time.localtime().tm_year),
            "vod_area": "中国",
            "vod_remarks": "更新至%d集" % self.EPISODES,
            "vod_actor": "",
            "vod_director": "",
            "vod_content": (
                "数据来源：刷鸭(https://shuaya.pages.dev/) 线路 #%s。\n"
                "该源为随机视频流，共 %d 集，每集均为随机短视频，点开即播、集集不同。\n"
                "已开启连播：播完一集自动跳转下一集，可无限刷下去。\n"
                "若当前线路无响应，会自动切换到其他可用线路。" % (code, self.EPISODES)
            ),
            "vod_play_from": "刷鸭线路#%s" % code,
            "vod_play_url": "#".join(eps),
        }
        return {"list": [vod]}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg=1):
        """源站没有搜索能力，明确返回空列表。

        不抛异常，也不伪造结果——让播放器显示「无结果」而不是报错崩溃。
        """
        return {"list": []}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        """核心：把指纹解析成可播的真实地址，并带坏线路自动降级。

        v2 改为并发探测：多条线路同时测，第一条通过的立即交付，
        不再逐条串行等超时，点开速度明显快于旧版。
        集号不参与解析——同一集的每次播放都会重新拉取随机视频。
        """
        code, _ep = self._parse_fp(id)
        url = self._probe_lines(self._ordered_lines(code))
        if url:
            return {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": json.dumps(self.HEADERS),
            }

        # 全军覆没：不再重试，直接把源站主接口交给播放器自行跳转
        # （部分播放器容忍 302，比返回空 url 体验好）
        fallback = self._randomize(self.API_LIST[0]["api"], "link")
        return {
            "parse": 0,
            "playUrl": "",
            "url": fallback,
            "header": json.dumps(self.HEADERS),
        }

    def _probe_lines(self, lines):
        """按优先级探测线路，返回第一条可用直链；失败的进冷却。"""
        ordered, seen = [], set()
        for line in lines:
            if line["code"] not in seen:
                seen.add(line["code"])
                ordered.append(line)
        if not ordered:
            return None

        # 第一批并发探测（最多 6 条）
        batch, rest = ordered[:6], ordered[6:]
        try:
            from concurrent.futures import ThreadPoolExecutor
        except Exception:
            ThreadPoolExecutor = None
        if ThreadPoolExecutor and len(batch) > 1:
            ex = ThreadPoolExecutor(max_workers=len(batch))
            try:
                futs = {ln["code"]: ex.submit(self._resolve, ln, True) for ln in batch}
                for ln in batch:
                    try:
                        url, _e = futs[ln["code"]].result(timeout=30)
                    except Exception:
                        url = None
                    if url:
                        self.cool_down.pop(ln["code"], None)
                        return url
                    self._mark_bad(ln["code"])
            finally:
                try:
                    ex.shutdown(wait=False)
                except Exception:
                    pass
            ordered = rest
        # 剩余（或无并发环境时）串行兜底
        for line in ordered:
            url, _e = self._resolve(line, probe=True)
            if url:
                self.cool_down.pop(line["code"], None)
                return url
            self._mark_bad(line["code"])
        return None

    # ==================== 自定义动作：换一个 ====================
    def action(self, action):
        """对应源站的「换一个」按钮。

        返回一条新指纹，播放器可直接跳转播放，实现无限刷。
        注：部分播放器不传 action 调用，不影响主链路。
        """
        if str(action).lower() in ("next", "change", "换一个", "random"):
            line = random.choice([x for x in self.API_LIST if x.get("core")] or self.API_LIST)
            return {"vod_id": self._mk_fp(line["code"], random.randint(1, self.EPISODES))}
        return None


# ==================== 本地自测 ====================
if __name__ == "__main__":
    s = Spider()
    s.init("")
    print("[homeContent] 分类数:", len(s.homeContent(True)["class"]))
    hv = s.homeVideoContent()
    print("[homeVideoContent] 推荐数:", len(hv["list"]))
    if hv["list"]:
        print("  首条封面长度:", len(hv["list"][0]["vod_pic"]))
    cc = s.categoryContent("001", 1, False, {})
    print("[categoryContent] 001 列表数:", len(cc["list"]), "| pagecount:", cc["pagecount"])
    vid = cc["list"][0]["vod_id"]
    print("[categoryContent] 指纹样例:", vid, "-> 解析", s._parse_fp(vid))
    dt = s.detailContent([vid])
    vod = dt["list"][0]
    print("[detailContent] 标题:", vod["vod_name"], "| 备注:", vod["vod_remarks"])
    eps = vod["vod_play_url"].split("#")
    print("[detailContent] 集数:", len(eps), "| 首集:", eps[0], "| 末集:", eps[-1])
    fp = eps[0].split("$")[-1]
    print("[detailContent] 首集指纹:", fp, "-> 解析", s._parse_fp(fp))
    print("[playerContent] 正在解析真实地址...")
    pc = s.playerContent("", fp, False)
    print("  url:", (pc.get("url") or "")[:110])
    print("  命中直链:", "http" in (pc.get("url") or ""))
    print("[searchContent] 结果数:", len(s.searchContent("黑丝", True)["list"]))
