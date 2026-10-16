/*
@header({
  title: '魔法盒子',
  lang: 'dr3',
  searchable: 2, filterable: 1, quickSearch: 0,
})

【魔法盒子 dr3 移植】—— 对照 魔法盒子.py 逐环节对译
- 站点不是普通影视站，是聚合器：l98.cn 把 25 个 TVBox 源包成一套 JSON API，
  home/category/search/detail 全是 POST JSON，主链路零 HTML 可爬，不需要 pdfa/pdfh
- 三个内置分支原样保留：奇优影院(HTML) / 趣看看短剧(阿里云VOD) / 麒麟视频(苹果CMS)，
  这三块的列表解析沿用 py 的正则（列表 class 是 col-md-\d+ 这类变体，选择器写不了）

l98 API 约定（全部 POST JSON，Content-Type/Origin 必带）：
  /api/tvbox/home      {api: 'tvbox-py://hema', filter: true}
  /api/tvbox/category  {api, tid, page, filter: true, extend: {}}
  /api/search          {api, keyword}
  /api/detail          {api, ids: [realId]}
  响应 {success, data}；data 出现 type_id=guard 或「资源维护中」= 站点维护中 → 等 0.5s 重试一次

分类与播放链路：
  影视推荐   多源首页轮询穿插（py 的 homeVideoContent），筛选 = 按来源过滤，客户端分页
  芸芸音乐/独播库  走 l98 分类 API；首页大（≥40 条/页）时一页直达，否则 3 页聚一次翻页
  麒麟视频   网页列表 + /api.php/provide/vod 详情与搜索，播放是 qlys.cc m3u8 直链
  奇优影院   纯 HTML；播放：/play/ 页 → iframe → player/api.php?url=&sign=&t=，兜底正则抓直链
  趣看看短剧 play_auth 解码 → 阿里云 GetPlayInfo（HMAC-SHA1 签名）→ 取最高清晰度直链
  l98 直链   /api/tvbox/play/ 里 tvbox_ep_xxx 的 base64 壳解出真 m3u8，零解析直出

修掉/收敛的原版问题：
1) 原版有两处变量名被打码成了 ***：REC_KEY = "***"、categoryContent 里「*** = self._recommend_list()」，
   Python 直接语法错误，「影视推荐」分类整个不可用。移植改回 rec。
2) 原版搜索缓存被原地追加内置分支结果，翻回第 1 页会越并越多；改成每次现拼、不碰缓存。
3) 原版 _multi_source 实例变量跨调用漂移（home 设 True、category 开头清 False），
   聚合流备注里的来源名时有时无；改成 card() 显式传参：推荐/搜索恒带来源前缀，单源分类不带。
4) 原版给未挂面板的源也生成筛选配置、运行时回写 SUB_CLASS，全是死配置；收敛成只配 6 个一级分类。
5) 推荐流原版 3 秒预算强杀慢源；JS 里换 Promise.all 等全部返回（每源自带 8s 超时），
   结果稳定但最坏会多等几秒。
6) POST 四路兜底（postJson/post/fetch/urllib）收敛成 req 一处：JS 宿主只有一个网络口子；
   API_SOURCES 定义未用、localProxy/isVideoFormat 等宿主兼容方法 dr3 用不上，均去掉。

移植假设（宿主能力，出错只改对应一处）：
- POST 走 ctx.lib.net.req(url, {method: 'POST', body, data, headers, timeout}) 返回 {content}，
  body/data 两个字段都带上，宿主认哪个用哪个
- setTimeout 可用（sleep 只用在 guard 重试和详情重试两处）
- 无 crypto/atob：SHA1 / HMAC-SHA1 / Base64 / UTF-8 全部纯 JS 手写，见「纯 JS 加密件」一节

已知边界：
- 免费聚合站，源可用性随站点波动；guard 只重试一次，再失败就空列表。
- 趣看看签名是纯 JS 实现，若签名失败只有该分支解析不出（其它分支不受影响）。
- 搜索聚合单源 20 条、总量 200 条；内置分支结果只并入第 1 页（py 原版行为）。
- 播放解析不出直链时交播放器嗅探（parse:1），l98 壳地址嗅探不一定出画面。
*/

// ═══ 常量 ═══

const HOST = 'http://l98.cn'
const UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/120.0.0.0 Mobile Safari/537.36'
const HEADERS = {'User-Agent': UA, Referer: HOST + '/'}
const TIMEOUT = 12000
const REC_TIMEOUT = 8000
const CAT_TIMEOUT = 10000
const SEARCH_TIMEOUT = 5000

const DIRECT_PLAY = true
const DETAIL_FALLBACK = true
const FALLBACK_TRY = 4

// 自适应分页：源首页 ≥40 条时一步到位，否则一次 TVBox 翻页聚合 3 个源分页
const CAT_PAGES = 3
const CAT_MIN_ITEMS = 40
const CAT_MAX = 120

// 搜索聚合：只打这几个源（SEARCH_ALL = true 则全量 25 个源）
const SEARCH_ALL = false
const SEARCH_ONLY = [
    'source-37dc8f3871', 'wencai', 'tv', 'j4k', 'source-0ad659640c', 'hema',
]
const SEARCH_PER_SRC = 20
const SEARCH_MAX = 200
const SEARCH_LIMIT = 20
// true = 只留真命中；false = 不筛；'auto' = 真命中 ≥5 条才只留真命中
const SEARCH_STRICT = 'auto'

// 推荐聚合：这些源各取前 10 条轮询穿插
const REC_SOURCES = [
    'hema', 'wencai', 'tv', 'j4k',
    'source-37dc8f3871', 'source-0ad659640c',
]
const REC_PER_SRC = 10
const REC_LIMIT = 20

// 缓存三档（py 是 300s 一档、分支里 600/1800 散落，归一下）
const CACHE_TTL = 5 * 60 * 1000
const DETAIL_TTL = 10 * 60 * 1000
const PLAY_TTL = 30 * 60 * 1000

// ═══ 聚合源清单 ═══

// type 决定 api 协议头：tvbox-py:// / tvbox-js://
const SOURCES = [
    {key: 'hema', name: '河马短剧', type: 'py'},
    {key: 'yunyun', name: '芸芸音乐', type: 'js'},
    {key: 'source-37dc8f3871', name: '独播库', type: 'py'},
    {key: 'source-8ee56df12f', name: '歪比影视', type: 'py'},
    {key: 'source-b5552441f5', name: '云端影视', type: 'py'},
    {key: 'source-681f32793f', name: '金牌影视', type: 'py'},
    {key: 'tv', name: '爱瓜TV', type: 'py'},
    {key: 'wencai', name: '文才影视T3', type: 'py'},
    {key: 'jumi', name: '剧迷影视', type: 'py'},
    {key: 'j4k', name: '极影4K', type: 'js'},
    {key: 'source-4eb17c91b4', name: '三秋影视', type: 'py'},
    {key: 'source-0ad659640c', name: '泥巴影视', type: 'py'},
    {key: 'source-e2baa3717e', name: '网易影像', type: 'py'},
    {key: 'source-05849e86e9', name: '飞流视频', type: 'py'},
    {key: 'jd4k', name: 'JD4K', type: 'js'},
    {key: 'source-90e25e2716', name: '布布影视', type: 'py'},
    {key: 'source-aa4f0ed30b', name: '奇优动漫', type: 'py'},
    {key: 'source-d1867dcc71', name: '悟圣短剧', type: 'py'},
    {key: 'source-cd6cd838d1', name: '喜福短剧', type: 'py'},
    {key: 'source-c6eef9d264', name: '星芽短剧', type: 'py'},
    {key: 'source-984a66ab13', name: '央视卫视', type: 'py'},
    {key: 'source-b3e87ad824', name: '西饭短剧', type: 'py'},
    {key: 'source-616fbcbf9e', name: '瓜子APP', type: 'py'},
    {key: 'source-d6c318599c', name: '蛋蛋奇', type: 'py'},
    {key: 'source-cb4888cc81', name: '剧OK影视', type: 'py'},
]

const SOURCE_API = {}
const SOURCE_NAME = {}
for (const s of SOURCES) {
    SOURCE_API[s.key] = 'tvbox-' + s.type + '://' + s.key
    SOURCE_NAME[s.key] = s.name
}

// 内置分支 key（不走 l98 API，自己实现的三个）
const EXTRA_KEYS = ['qiyou', 'qukkan', 'qilin']
// 原版这行被打码成 REC_KEY = "***"，整个推荐分类跟着报废；实际值就是 rec
const REC_KEY = 'rec'

// ═══ 分类与筛选（声明式，交给 dr3 面板）═══

// 一级分类：s_ 前缀 = 走 l98 聚合；rec/qilin/qiyou/qukkan 是内置分支
const CLASSES = [
    {id: 's_rec', name: '影视推荐'},
    {id: 's_yunyun', name: '芸芸音乐'},
    {id: 's_source-37dc8f3871', name: '独播库'},
    {id: 's_qilin', name: '麒麟视频'},
    {id: 's_qiyou', name: '奇优影院'},
    {id: 's_qukkan', name: '趣看看短剧'},
]

// 麒麟的年份/地区选项
const QILIN_YEARS = [{n: '全部', v: ''}].concat(
    Array.from({length: 27}, (_, i) => {
        const y = String(2026 - i)
        return {n: y, v: y}
    }))

const QILIN_AREAS = [{n: '全部', v: ''}].concat([
    '大陆', '香港', '台湾', '美国', '日本', '韩国', '英国', '法国', '德国',
    '泰国', '印度', '俄罗斯', '加拿大', '澳大利亚', '新加坡',
].map((a) => ({n: a, v: a})))

// 只给 6 个一级分类配筛选；原版给没挂面板的源也生成配置，属于死代码
const FILTERS = {
    // 推荐流是 6 个源轮询出来的，来源筛选就是在这份列表上过滤
    s_rec: [
        {key: 'src', name: '来源', value: [
            {n: '全部', v: ''},
            ...REC_SOURCES.map((k) => ({n: SOURCE_NAME[k] || k, v: k})),
        ]},
    ],
    s_yunyun: [
        {key: 'tid', name: '分类', value: [
            {n: '推荐', v: ''},
            {n: '推荐歌单', v: 'recommend'}, {n: '排行榜', v: 'toplist'},
            {n: '热门歌单', v: 'hot'}, {n: '热门歌手', v: 'artist'},
        ]},
    ],
    's_source-37dc8f3871': [
        {key: 'tid', name: '分类', value: [
            {n: '推荐', v: ''},
            {n: '连续剧', v: '2'}, {n: '综艺', v: '3'},
            {n: '电影', v: '1'}, {n: '动漫', v: '4'},
        ]},
    ],
    s_qiyou: [
        {key: 'tid', name: '分类', value: [
            {n: '电影', v: '1'}, {n: '电视剧', v: '2'},
            {n: '动漫', v: '3'}, {n: '综艺', v: '4'},
        ]},
    ],
    s_qukkan: [
        {key: 'tid', name: '分类', value: [
            {n: '全部短剧', v: 'all'},
            {n: '现代言情', v: '1'}, {n: '爽剧', v: '3'}, {n: '都市', v: '4'},
            {n: '逆袭', v: '5'}, {n: '甜宠', v: '6'}, {n: '女强', v: '7'},
            {n: '虐恋', v: '13'}, {n: '古代言情', v: '16'}, {n: '玄幻', v: '23'},
        ]},
        {key: 'by', name: '排序', value: [
            {n: '综合', v: ''}, {n: '最新', v: 'time'}, {n: '最热', v: 'hot'},
        ]},
    ],
    s_qilin: [
        {key: 'tid', name: '分类', value: [
            {n: '电影', v: '1'}, {n: '电视剧', v: '2'}, {n: '短剧', v: '3'},
            {n: '动漫', v: '4'}, {n: '综艺', v: '5'}, {n: '内地剧', v: '6'},
            {n: '港台剧', v: '7'}, {n: '日韩剧', v: '8'}, {n: '欧美剧', v: '9'},
            {n: '动作片', v: '10'}, {n: '恐怖片', v: '11'}, {n: '科幻片', v: '12'},
            {n: '战争片', v: '13'}, {n: '爱情片', v: '14'}, {n: '喜剧片', v: '15'},
            {n: '剧情片', v: '16'}, {n: '记录片', v: '17'}, {n: '内地番', v: '18'},
            {n: '日韩番', v: '19'}, {n: '港台番', v: '20'}, {n: '欧美番', v: '21'},
            {n: '泰剧', v: '22'}, {n: '漫剧', v: '23'}, {n: '有声漫剧', v: '24'},
        ]},
        {key: 'year', name: '年份', value: QILIN_YEARS},
        {key: 'area', name: '地区', value: QILIN_AREAS},
    ],
}

// ═══ 请求 ═══

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
}

function parseJson(text) {
    // 宿主若已帮着 parse 过就直接透传
    if (typeof text === 'object' && text) return text
    try {
        return JSON.parse(text)
    } catch {
        return null
    }
}

async function get(ctx, url, opt = {}) {
    const headers = opt.headers || HEADERS
    const timeout = opt.timeout || TIMEOUT
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const res = await ctx.lib.net.req(url, {headers, timeout})
            if (res && res.content) return res.content
        } catch (e) {
            ctx.log('魔法盒子 ' + url.slice(0, 56) + ' 失败: ' + e.message)
        }
    }
    return ''
}

async function getJson(ctx, url, headers = HEADERS, timeout = TIMEOUT) {
    try {
        const res = await ctx.lib.net.req(url, {headers, timeout})
        return parseJson(res && res.content)
    } catch (e) {
        ctx.log('魔法盒子 GET ' + url.slice(0, 48) + ' 失败: ' + e.message)
        return null
    }
}

async function postOnce(ctx, url, payload, timeout) {
    const body = JSON.stringify(payload)
    const headers = {
        'User-Agent': UA,
        Referer: HOST + '/',
        Accept: 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        Origin: HOST,
    }
    try {
        // body/data 都带上：不同宿主的 POST 字段名不一，认哪个用哪个
        const res = await ctx.lib.net.req(url, {method: 'POST', headers, body, data: body, timeout})
        return parseJson(res && res.content)
    } catch (e) {
        ctx.log('魔法盒子 POST ' + url.slice(0, 48) + ' 失败: ' + e.message)
        return null
    }
}

async function postJson(ctx, url, payload, timeout = TIMEOUT) {
    let data = await postOnce(ctx, url, payload, timeout)
    // 站点维护时 data 里塞 guard 壳，等半秒重试一次
    if (isGuard(data)) {
        await sleep(500)
        data = await postOnce(ctx, url, payload, timeout)
    }
    return data
}

// 奇优搜索是表单 POST
async function postForm(ctx, url, form, headers, timeout = TIMEOUT) {
    const body = Object.entries(form)
        .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
        .join('&')
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const res = await ctx.lib.net.req(url, {
                method: 'POST',
                headers: {...headers, 'Content-Type': 'application/x-www-form-urlencoded'},
                body, data: body, timeout,
            })
            if (res && res.content) return res.content
        } catch (e) {
            ctx.log('魔法盒子 表单 ' + url.slice(0, 48) + ' 失败: ' + e.message)
        }
    }
    return ''
}

// guard 壳识别：type_id=guard 的分类或「资源维护中」占位
function isGuard(data) {
    const d = data && data.data
    if (!d) return false
    if (Array.isArray(d)) {
        return d.some((x) => x && x.vod_name === '资源维护中')
    }
    if (typeof d === 'object') {
        if ((d.class || []).some((c) => c && String(c.type_id) === 'guard')) return true
        if (d.vod_name === '资源维护中') return true
    }
    return false
}

// ═══ 纯 JS 加密件（趣看看阿里云签名专用）═══
// dr3 宿主没有 crypto/atob，SHA1 / HMAC-SHA1 / Base64 / UTF-8 全部手写。
// 和小猪看看里的 scanJson 一个思路：不依赖宿主，自带就跑。

function rol(x, n) {
    return ((x << n) | (x >>> (32 - n))) | 0
}

// 输入字节数组，输出 5 个 32 位字（标准 FIPS 180-1 流程）
function sha1Words(bytes) {
    const h = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]
    const bitLen = bytes.length * 8
    const data = bytes.slice()
    data.push(0x80)
    while (data.length % 64 !== 56) data.push(0)
    const hi = Math.floor(bitLen / 0x100000000)
    const lo = bitLen >>> 0
    data.push(
        (hi >>> 24) & 0xff, (hi >>> 16) & 0xff, (hi >>> 8) & 0xff, hi & 0xff,
        (lo >>> 24) & 0xff, (lo >>> 16) & 0xff, (lo >>> 8) & 0xff, lo & 0xff,
    )
    const w = new Array(80)
    for (let off = 0; off < data.length; off += 64) {
        for (let i = 0; i < 16; i++) {
            const j = off + i * 4
            w[i] = (data[j] << 24) | (data[j + 1] << 16) | (data[j + 2] << 8) | data[j + 3]
        }
        for (let i = 16; i < 80; i++) {
            w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1)
        }
        let a = h[0]
        let b = h[1]
        let c = h[2]
        let d = h[3]
        let e = h[4]
        for (let i = 0; i < 80; i++) {
            let f, k
            if (i < 20) {
                f = (b & c) | (~b & d)
                k = 0x5a827999
            } else if (i < 40) {
                f = b ^ c ^ d
                k = 0x6ed9eba1
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d)
                k = 0x8f1bbcdc
            } else {
                f = b ^ c ^ d
                k = 0xca62c1d6
            }
            const t = (rol(a, 5) + f + e + k + w[i]) | 0
            e = d
            d = c
            c = rol(b, 30)
            b = a
            a = t
        }
        h[0] = (h[0] + a) | 0
        h[1] = (h[1] + b) | 0
        h[2] = (h[2] + c) | 0
        h[3] = (h[3] + d) | 0
        h[4] = (h[4] + e) | 0
    }
    return h
}

function wordsToBytes(words) {
    const out = []
    for (const w of words) {
        out.push((w >>> 24) & 0xff, (w >>> 16) & 0xff, (w >>> 8) & 0xff, w & 0xff)
    }
    return out
}

function hmacSha1(keyStr, msgStr) {
    let key = utf8Bytes(keyStr)
    if (key.length > 64) key = wordsToBytes(sha1Words(key))
    const ipad = []
    const opad = []
    for (let i = 0; i < 64; i++) {
        const k = i < key.length ? key[i] : 0
        ipad.push(k ^ 0x36)
        opad.push(k ^ 0x5c)
    }
    const inner = wordsToBytes(sha1Words(ipad.concat(utf8Bytes(msgStr))))
    return wordsToBytes(sha1Words(opad.concat(inner)))
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function b64encode(bytes) {
    let out = ''
    for (let i = 0; i < bytes.length; i += 3) {
        const b1 = i + 1 < bytes.length
        const b2 = i + 2 < bytes.length
        const n = (bytes[i] << 16) | ((b1 ? bytes[i + 1] : 0) << 8) | (b2 ? bytes[i + 2] : 0)
        out += B64[(n >>> 18) & 63] + B64[(n >>> 12) & 63] +
            (b1 ? B64[(n >>> 6) & 63] : '=') + (b2 ? B64[n & 63] : '=')
    }
    return out
}

function b64decode(str) {
    const out = []
    let buf = 0
    let bits = 0
    for (const ch of String(str || '')) {
        const v = B64.indexOf(ch)
        if (v < 0) continue
        buf = ((buf & 0xfff) << 6) | v
        bits += 6
        if (bits >= 8) {
            bits -= 8
            out.push((buf >> bits) & 0xff)
        }
    }
    return out
}

function utf8Bytes(str) {
    const out = []
    for (let i = 0; i < str.length; i++) {
        let cp = str.charCodeAt(i)
        if (cp >= 0xd800 && cp <= 0xdbff && i + 1 < str.length) {
            const lo = str.charCodeAt(i + 1)
            if (lo >= 0xdc00 && lo <= 0xdfff) {
                cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00)
                i++
            }
        }
        if (cp < 0x80) out.push(cp)
        else if (cp < 0x800) out.push(0xc0 | (cp >> 6), 0x80 | (cp & 63))
        else if (cp < 0x10000) out.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63))
        else out.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 63), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63))
    }
    return out
}

function utf8Decode(bytes) {
    let out = ''
    let i = 0
    while (i < bytes.length) {
        const b = bytes[i]
        if (b < 0x80) {
            out += String.fromCharCode(b)
            i++
        } else if (b < 0xe0) {
            out += String.fromCharCode(((b & 0x1f) << 6) | (bytes[i + 1] & 0x3f))
            i += 2
        } else if (b < 0xf0) {
            out += String.fromCharCode(
                ((b & 0x0f) << 12) | ((bytes[i + 1] & 0x3f) << 6) | (bytes[i + 2] & 0x3f))
            i += 3
        } else {
            const cp = ((b & 0x07) << 18) | ((bytes[i + 1] & 0x3f) << 12) |
                ((bytes[i + 2] & 0x3f) << 6) | (bytes[i + 3] & 0x3f)
            const off = cp - 0x10000
            out += String.fromCharCode(0xd800 + (off >> 10), 0xdc00 + (off & 0x3ff))
            i += 4
        }
    }
    return out
}

function guid() {
    // SignatureNonce：拼一个伪 UUID 就够（服务端只要求唯一）
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = Math.random() * 16 | 0
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
    })
}

// 阿里云 RPC 签名的百分号编码：encodeURIComponent 基础上把 + 和 * 也编掉
function aliyunEnc(v) {
    return encodeURIComponent(String(v)).replace(/\+/g, '%2B').replace(/\*/g, '%2A')
}

function aliyunSign(params, secret) {
    const canon = Object.keys(params).sort()
        .map((k) => aliyunEnc(k) + '=' + aliyunEnc(params[k]))
        .join('&')
    const sts = 'GET&' + aliyunEnc('/') + '&' + aliyunEnc(canon)
    return b64encode(hmacSha1(secret + '&', sts))
}

// ═══ 内置分支：奇优影院 (qiyou05.com，纯 HTML) ═══

const QIYOU_SITE = 'http://www.qiyou05.com'

function qiyouHeaders() {
    return {'User-Agent': UA, Referer: QIYOU_SITE + '/', 'Accept-Language': 'zh-CN,zh;q=0.9'}
}

// 卡片：<li class="col-md-x …"> 里 title 片名 / data-original 图 / .pic-text 备注
function qiyouCards(html) {
    if (!html) return []
    const blocks = [...html.matchAll(/<li class="col-md-\d+ col-sm-4 col-xs-3">([\s\S]*?)<\/li>/g)]
        .map((m) => m[1])
    if (!blocks.length) {
        for (const m of html.matchAll(/<li class="active[^"]*clearfix">([\s\S]*?)<\/li>/g)) {
            blocks.push(m[1])
        }
    }
    const out = []
    for (const blk of blocks) {
        const href = (blk.match(/href="(\/view\/\d+\.html)"/) || [])[1]
        const name = (blk.match(/title="([^"]+)"/) || [])[1]
        const pic = (blk.match(/data-original="([^"]+)"/) || [])[1]
        if (!href || !name || !pic) continue
        const rmk = (blk.match(/<span class="pic-text text-right">([^<]*)<\/span>/) || [])[1] || ''
        out.push({
            vod_id: 'qiyou@' + absUrl(QIYOU_SITE, href),
            vod_name: name.trim(),
            vod_pic: fixQiyouPic(pic),
            vod_remarks: rmk.trim(),
        })
    }
    return out
}

function fixQiyouPic(p) {
    if (p.startsWith('//')) return 'https:' + p
    if (p.startsWith('http://') || p.startsWith('https://')) return p
    return QIYOU_SITE + p
}

async function qiyouCategory(ctx, tid, pg) {
    tid = tid || '1'
    const page = Math.max(1, parseInt(pg, 10) || 1)
    const url = page <= 1
        ? QIYOU_SITE + '/list/' + tid + '.html'
        : QIYOU_SITE + '/list/' + tid + '_' + page + '.html'
    const ck = 'qy:cat:' + tid + ':' + page
    let items = await ctx.cache.get(ck)
    if (!items) {
        const html = await get(ctx, url, {headers: qiyouHeaders()})
        items = qiyouCards(html)
        if (items.length) await ctx.cache.set(ck, items, CACHE_TTL)
    }
    return {
        list: items,
        page,
        // 前瞻式页数：整页(≥24)就给下一页
        pagecount: items.length >= 24 ? page + 1 : page,
        limit: 24,
        total: 9999,
    }
}

async function qiyouDetail(ctx, url) {
    const html = await get(ctx, url, {headers: qiyouHeaders()})
    if (!html) return {list: []}
    const name = ((html.match(/<h1 class="line1">([^<]+)<\/h1>/) || [])[1] || '未知名称').trim()
    const pic = fixQiyouPic((html.match(/<img class="lazyload" data-original="([^"]+)"/) || [])[1] || '')
    const rmk = ((html.match(/<span class="pic-text text-right">([^<]*)<\/span>/) || [])[1] || '').trim()
    const dm = html.match(/<p class="desc[^"]*"><span class="left text-muted">简介：<\/span>([\s\S]*?)<a href="#desc">/)
    const content = dm ? dm[1].replace(/<[^>]+>/g, '').trim() : ''
    // 选集链接统一拼成 集名$绝对地址
    const epsOf = (chunk) => [...chunk.matchAll(/<a href="(\/play\/[^"]+)" title="([^"]+)">/g)]
        .map((em) => em[2].trim() + '$' + (em[1].startsWith('/') ? QIYOU_SITE + em[1] : em[1]))

    const playFrom = []
    const playUrl = []
    // 多线路：tab 标题 + 对应 down 块里的播放列表
    for (const m of html.matchAll(/<a data-toggle="tab" href="#(down\d+)">([^<]+)<\/a>/g)) {
        const sm = html.match(new RegExp('id="' + m[1] + '"[^>]*>[\\s\\S]*?<ul class="stui-content__playlist clearfix">([\\s\\S]*?)</ul>'))
        if (!sm) continue
        const eps = epsOf(sm[1])
        if (eps.length) {
            playFrom.push(m[2].trim())
            playUrl.push(eps.join('#'))
        }
    }
    // 没有分线路结构就整页扫一遍
    if (!playFrom.length) {
        const eps = epsOf(html)
        if (eps.length) {
            playFrom.push('奇优线路')
            playUrl.push(eps.join('#'))
        }
    }
    if (!playFrom.length) return {list: []}
    return {list: [{
        vod_id: 'qiyou@' + url,
        vod_name: name,
        vod_pic: pic,
        vod_remarks: rmk,
        vod_content: content,
        vod_play_from: playFrom.join('$$$'),
        vod_play_url: playUrl.join('$$$'),
    }]}
}

async function qiyouSearch(ctx, kw) {
    const html = await postForm(ctx, QIYOU_SITE + '/search.php', {searchword: kw}, qiyouHeaders())
    const items = qiyouCards(html)
    return {list: items, page: 1, pagecount: 1, limit: items.length || 20, total: items.length}
}

async function qiyouPlayer(ctx, playUrl) {
    const html = await get(ctx, playUrl, {headers: qiyouHeaders()})
    if (html) {
        const im = html.match(/<iframe[^>]+src=["']([^"']+)["']/)
        if (im) {
            // /play/ 页里套的是代理 iframe，真地址要从 iframe 里再挖一层
            let iu = im[1]
            if (iu.startsWith('//')) iu = 'https:' + iu
            else if (!iu.startsWith('http://') && !iu.startsWith('https://')) iu = QIYOU_SITE + iu
            const ihtml = await get(ctx, iu, {headers: {'User-Agent': UA, Referer: iu}})
            if (ihtml) {
                const uv = ihtml.match(/const\s+Url\s*=\s*["']([^"']+)["']/)
                const sv = ihtml.match(/const\s+Sign\s*=\s*["']([^"']+)["']/)
                const fv = ihtml.match(/const\s+From\s*=\s*["']([^"']+)["']/)
                if (uv && sv && fv) {
                    const origin = iu.split('://')[0] + '://' + iu.split('://')[1].split('/')[0]
                    const api = origin + '/player/api.php?url=' + uv[1] + '&sign=' + sv[1] + '&t=' + fv[1]
                    const j = await getJson(ctx, api, {'User-Agent': UA, Referer: iu}, 10000)
                    if (j && j.code === 200 && j.url) {
                        return {parse: 0, jx: 0, url: j.url, header: qiyouHeaders()}
                    }
                }
                for (const re of [/https?:\/\/[^"']+\.m3u8[^"']*/, /https?:\/\/[^"']+\.mp4[^"']*/]) {
                    const m = ihtml.match(re)
                    if (m) return {parse: 0, jx: 0, url: m[0], header: qiyouHeaders()}
                }
            }
            // 换不到直链就把 iframe 交给播放器嗅探
            return {parse: 1, jx: 0, url: iu, header: qiyouHeaders()}
        }
        for (const re of [/https?:\/\/[^"']+\.m3u8/, /https?:\/\/[^"']+\.mp4/]) {
            const m = html.match(re)
            if (m) return {parse: 0, jx: 0, url: m[0], header: qiyouHeaders()}
        }
    }
    return {parse: 1, jx: 0, url: playUrl, header: qiyouHeaders()}
}

// ═══ 内置分支：趣看看短剧 (阿里云 VOD) ═══

const QK_API = 'https://minidrama-api.contentchina.com'
const QK_HOST = 'https://minidrama.contentchina.com'
const QK_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
const QK_HEADERS = {
    'User-Agent': QK_UA,
    Accept: 'application/json, text/plain, */*',
    Referer: QK_HOST + '/',
}

async function qkGet(ctx, path, params) {
    // code==200 才算成功，返回 data 字段
    const qs = Object.entries(params || {})
        .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
        .join('&')
    const j = await getJson(ctx, QK_API + path + (qs ? '?' + qs : ''), QK_HEADERS, 5000)
    if (j && j.code === 200) return j.data
    return null
}

function qkCard(it) {
    const total = it.total || 0
    return {
        vod_id: 'qukkan@' + String(it.albumId || ''),
        vod_name: it.title || '',
        vod_pic: it.coverUrl || '',
        vod_remarks: total ? '全' + total + '集' : '',
    }
}

async function qkCategory(ctx, tid, pg, by) {
    const page = Math.max(1, parseInt(pg, 10) || 1)
    const params = {pageSize: 100, currentPage: page}
    if (tid && tid !== 'all') params.filterCategories = tid
    const data = await qkGet(ctx, '/web/v1/drama/list', params)
    if (!data) return {list: [], page, pagecount: 1, limit: 36, total: 0}
    let items = data.data || []
    // 站点没有排序参数，hot/time 是客户端排的
    if (by === 'hot') items = items.slice().sort((a, b) => (parseInt(b.hot, 10) || 0) - (parseInt(a.hot, 10) || 0))
    else if (by === 'time') items = items.slice().sort((a, b) => (parseInt(b.updateTime, 10) || 0) - (parseInt(a.updateTime, 10) || 0))
    const pag = data.pagination || {}
    return {
        list: items.map(qkCard),
        page,
        pagecount: Math.max(1, pag.totalPages || 1),
        limit: 36,
        total: pag.total || items.length,
    }
}

async function qkDetail(ctx, albumId) {
    const ck = 'qk:d:' + albumId
    const hit = await ctx.cache.get(ck)
    if (hit) return hit
    const data = await qkGet(ctx, '/web/v1/drama/detail', {albumId})
    if (!data) return {list: []}
    const serial = data.serialData || {}
    // 集数链接直接固化 albumId:seq，播放时按这个格式识别
    const eps = (data.episodeList || [])
        .filter((ep) => ep.sequence)
        .map((ep) => '第' + ep.sequence + '集$' + albumId + ':' + ep.sequence)
    const result = {list: [{
        vod_id: 'qukkan@' + albumId,
        vod_name: serial.title || '剧集' + albumId,
        vod_pic: serial.coverUrl || '',
        type_name: (serial.categories || []).join(','),
        vod_remarks: serial.total ? '全' + serial.total + '集' : '',
        vod_actor: (serial.leadActor || []).join(','),
        vod_content: String(serial.introduction || '').trim(),
        vod_play_from: '趣看看短剧',
        vod_play_url: eps.join('#'),
    }]}
    await ctx.cache.set(ck, result, DETAIL_TTL)
    return result
}

async function qkSearch(ctx, kw, pg) {
    const page = Math.max(1, parseInt(pg, 10) || 1)
    // 接口没有 wd 参数：拉整页列表回来客户端过滤
    const data = await qkGet(ctx, '/web/v1/drama/list', {pageSize: 100, currentPage: page})
    if (!data) return {list: [], page, pagecount: 1, limit: 36, total: 0}
    const hits = (data.data || [])
        .filter((it) => String(it.title || '').includes(kw))
        .map(qkCard)
    const pag = data.pagination || {}
    return {
        list: hits,
        page,
        pagecount: Math.max(1, pag.totalPages || 1),
        limit: 36,
        total: pag.total || 0,
    }
}

function decodePlayAuth(auth) {
    // playAuth 是 base64 的 JSON，里面带着临时 AK/SK 和授权信息
    try {
        const data = JSON.parse(utf8Decode(b64decode(auth)))
        return {
            AccessKeyId: data.AccessKeyId,
            AccessKeySecret: data.AccessKeySecret,
            SecurityToken: data.SecurityToken,
            AuthInfo: data.AuthInfo,
            Region: data.Region,
            VideoId: data.VideoMeta.VideoId,
        }
    } catch {
        return null
    }
}

async function qkResolve(ctx, albumId, seq) {
    try {
        const auth = await qkGet(ctx, '/web/v1/drama/play_auth', {albumId, seq})
        if (!auth || !auth.playAuth) return ''
        const info = decodePlayAuth(auth.playAuth)
        if (!info) return ''
        const params = {
            AccessKeyId: info.AccessKeyId,
            Action: 'GetPlayInfo',
            VideoId: info.VideoId,
            Formats: 'mp4',
            AuthTimeout: 3600,
            SecurityToken: info.SecurityToken,
            Format: 'JSON',
            Version: '2017-03-21',
            SignatureMethod: 'HMAC-SHA1',
            SignatureVersion: '1.0',
            SignatureNonce: guid(),
            Channel: 'HTML5',
            AuthInfo: info.AuthInfo,
        }
        params.Signature = aliyunSign(params, info.AccessKeySecret)
        const query = Object.entries(params)
            .map(([k, v]) => aliyunEnc(k) + '=' + aliyunEnc(v))
            .join('&')
        const j = await getJson(ctx, 'https://vod.' + info.Region + '.aliyuncs.com/?' + query, QK_HEADERS, 4000)
        const plays = (j && j.PlayInfoList && j.PlayInfoList.PlayInfo) || []
        if (plays.length) {
            // 多清晰度取最高的
            plays.sort((a, b) => (parseInt(b.Height, 10) || 0) - (parseInt(a.Height, 10) || 0))
            return plays[0].PlayURL || ''
        }
    } catch (e) {
        ctx.log('趣看看 解析失败: ' + e.message)
    }
    return ''
}

async function qkPlayer(ctx, playId) {
    const parts = String(playId).split(':')
    if (!(parts.length === 2 && /^\d+$/.test(parts[0]) && /^\d+$/.test(parts[1]))) {
        return {parse: 0, jx: 0, url: ''}
    }
    const ck = parts[0] + ':' + parts[1]
    let url = await ctx.cache.get('qk:play:' + ck)
    if (!url) {
        url = await qkResolve(ctx, parts[0], parts[1])
        if (url) await ctx.cache.set('qk:play:' + ck, url, PLAY_TTL)
    }
    if (!url) return {parse: 1, jx: 0, url: ''}
    return {
        parse: 0, jx: 0, url,
        header: {'User-Agent': QK_UA, Referer: QK_HOST + '/', Origin: QK_HOST},
    }
}

// ═══ 内置分支：麒麟视频 (qlys.cc，苹果CMS：网页列表 + API详情/搜索) ═══

const QILIN_SITE = 'https://www.qlys.cc'
const QILIN_API = 'https://www.qlys.cc/api.php/provide/vod/'
const QILIN_UA = 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36'
const QILIN_HEADERS = {
    'User-Agent': QILIN_UA,
    Referer: QILIN_SITE + '/',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

function fixQilinPic(p) {
    if (!p) return ''
    if (p.startsWith('//')) return 'https:' + p
    if (p.startsWith('http://') || p.startsWith('https://')) return p
    return QILIN_SITE + (p.startsWith('/') ? p : '/' + p)
}

async function qilinCategory(ctx, tid, pg, year, area) {
    tid = tid || '1'
    const page = Math.max(1, parseInt(pg, 10) || 1)
    const ck = 'ql:cat:' + [tid, page, year || '', area || ''].join(':')
    const hit = await ctx.cache.get(ck)
    if (hit) return hit
    let fp = ''
    if (year) fp += '/year/' + year
    if (area) fp += '/area/' + encodeURIComponent(area)
    const url = QILIN_SITE + '/index.php/vod/type/id/' + tid + fp + '/page/' + page + '.html'
    const items = []
    let pagecount = page
    const html = await get(ctx, url, {headers: QILIN_HEADERS})
    if (html) {
        for (const m of html.matchAll(/<div class="vod-item">([\s\S]*?)<\/a>\s*<\/div>/g)) {
            const blk = m[1]
            const vid = (blk.match(/href="\/index\.php\/vod\/detail\/id\/(\d+)\.html"/) || [])[1]
            const name = (blk.match(/title="([^"]+)"/) || [])[1]
            if (!vid || !name) continue
            items.push({
                vod_id: 'qilin@' + vid,
                vod_name: name.trim(),
                vod_pic: fixQilinPic((blk.match(/<img[^>]+src="([^"]+)"/) || [])[1] || ''),
                vod_remarks: ((blk.match(/<span class="remarks">([^<]+)<\/span>/) || [])[1] || '').trim(),
            })
        }
        // 苹果CMS有尾页链接，可以直接反推总页数（跟小猪看看那站不一样）
        if (/title="尾页"/.test(html)) {
            const nums = [...html.matchAll(/\/page\/(\d+)\.html/g)].map((m) => parseInt(m[1], 10))
            if (nums.length) pagecount = Math.max(...nums)
        }
    }
    const result = {list: items, page, pagecount: Math.max(1, pagecount), limit: 30, total: 9999}
    if (items.length) await ctx.cache.set(ck, result, CACHE_TTL)
    return result
}

async function qilinDetail(ctx, vid) {
    vid = String(vid)
    const ck = 'ql:d:' + vid
    const hit = await ctx.cache.get(ck)
    if (hit) return hit
    const data = await getJson(ctx, QILIN_API + '?ac=detail&ids=' + vid, QILIN_HEADERS, 8000)
    if (!data || !data.list || !data.list.length) return {list: []}
    const it = data.list[0]
    let playFrom = it.vod_play_from || '麒麟线路'
    let playUrl = it.vod_play_url || ''
    // 对齐线路、剔除空线路（苹果CMS两侧数量偶尔不一致）
    if (playUrl) {
        const fs = playFrom.split('$$$')
        const us = playUrl.split('$$$')
        if (fs.length !== us.length) {
            const n = Math.min(fs.length, us.length)
            fs.length = n
            us.length = n
        }
        const kf = []
        const ku = []
        for (let i = 0; i < fs.length; i++) {
            if (us[i] && us[i].includes('$')) {
                kf.push(fs[i])
                ku.push(us[i])
            }
        }
        playFrom = kf.length ? kf.join('$$$') : '麒麟线路'
        playUrl = ku.join('$$$')
    }
    if (!playUrl) return {list: []}
    const result = {list: [{
        vod_id: 'qilin@' + vid,
        vod_name: it.vod_name || '未知名称',
        vod_pic: it.vod_pic || '',
        vod_remarks: it.vod_remarks || '',
        type_name: it.type_name || '麒麟视频',
        vod_year: String(it.vod_year || ''),
        vod_area: it.vod_area || '',
        vod_actor: it.vod_actor || '',
        vod_director: it.vod_director || '',
        vod_content: String(it.vod_content || '').replace(/<[^>]+>/g, '').trim().slice(0, 500),
        vod_play_from: playFrom,
        vod_play_url: playUrl,
    }]}
    await ctx.cache.set(ck, result, CACHE_TTL)
    return result
}

async function qilinSearch(ctx, kw, pg) {
    const page = Math.max(1, parseInt(pg, 10) || 1)
    const data = await getJson(ctx,
        QILIN_API + '?ac=detail&wd=' + encodeURIComponent(kw || '') + '&pg=' + page,
        QILIN_HEADERS, 8000)
    if (!data || !data.list) return {list: [], page, pagecount: page, limit: 30, total: 0}
    const items = data.list.map((it) => ({
        vod_id: 'qilin@' + String(it.vod_id || ''),
        vod_name: it.vod_name || '',
        vod_pic: fixQilinPic(it.vod_pic || ''),
        vod_remarks: it.vod_remarks || '',
    }))
    return {
        list: items,
        page,
        pagecount: Math.max(1, parseInt(data.pagecount, 10) || page),
        limit: 30,
        total: parseInt(data.total, 10) || 0,
    }
}

// 播放：qlys.cc 的 m3u8 直链直接透传
function qilinPlayer(playUrl) {
    const u = String(playUrl).split('$').pop().trim()
    if (!u) return {parse: 0, jx: 0, url: ''}
    const isM3u8 = u.toLowerCase().includes('.m3u8')
    return {
        parse: 0, jx: 0, url: u,
        header: {'User-Agent': QILIN_UA, Referer: QILIN_SITE + '/'},
        format: isM3u8 ? 'application/x-mpegURL' : '',
        contentType: isM3u8 ? 'application/x-mpegURL' : '',
    }
}

// ═══ 卡片与 id ═══

// 卡片统一出口：vod_id 编码成 src@realId；聚合流(推荐/搜索)备注带来源名
function card(srcKey, v, withSrc) {
    let pic = String(v.vod_pic || '')
    if (pic.startsWith('//')) pic = 'http:' + pic
    let remark = String(v.vod_remarks || '').trim()
    if (remark.length > 20) remark = remark.slice(0, 20)
    if (withSrc) {
        const srcName = SOURCE_NAME[srcKey] || srcKey
        remark = remark ? srcName + ' · ' + remark : srcName
    }
    return {
        vod_id: encId(srcKey, v.vod_id || ''),
        vod_name: v.vod_name || '',
        vod_pic: pic,
        vod_remarks: remark,
    }
}

function encId(srcKey, vodId) {
    return srcKey + '@' + vodId
}

function decId(s) {
    s = String(s || '')
    let m = s.match(/^(qiyou|qukkan|qilin)@(.+)$/)
    if (m) return [m[1], m[2]]
    m = s.match(/^([A-Za-z0-9_-]+)@(.+)$/)
    if (m && SOURCE_API[m[1]]) return [m[1], m[2]]
    return ['', s]
}

function srcOfTid(tid) {
    const s = String(tid || '')
    return s.startsWith('s_') ? s.slice(2) : s
}

function absUrl(base, u) {
    u = String(u || '').trim().replace(/\\\//g, '/')
    if (u.startsWith('//')) return 'http:' + u
    if (u.startsWith('/')) return base + u
    return u
}

// 播放串按 TVBox 约定重组：名字$地址 用 # 连集、$$$ 连线路，地址统一补全
function fixPlayUrl(s) {
    if (!s) return ''
    const groups = []
    for (const grp of String(s).split('$$$')) {
        const eps = []
        for (const ep of grp.split('#')) {
            if (!ep.trim()) continue
            if (ep.includes('$')) {
                const at = ep.indexOf('$')
                eps.push(ep.slice(0, at) + '$' + absUrl(HOST, ep.slice(at + 1)))
            } else {
                eps.push(absUrl(HOST, ep))
            }
        }
        groups.push(eps.join('#'))
    }
    return groups.join('$$$')
}

// l98 的播放地址常是 tvbox_ep_xxx 的 base64 壳，解出里面的真直链
function decodeEpToken(url) {
    try {
        let token = url.split('/').pop().split('?')[0]
        if (!token.startsWith('tvbox_ep_')) return ''
        token = token.slice('tvbox_ep_'.length)
        const obj = JSON.parse(utf8Decode(b64decode(token)))
        const real = obj.i || ''
        if (typeof real === 'string' && real.startsWith('http')) return real
    } catch {
        return ''
    }
    return ''
}

function resolvePlay(url) {
    if (DIRECT_PLAY && url.includes('/api/tvbox/play/')) {
        const real = decodeEpToken(url)
        if (real) return real
    }
    return url
}

function isMedia(url) {
    const u = String(url || '').toLowerCase()
    return u.includes('m3u8') || u.includes('.mp4') || u.includes('.flv') || u.includes('.mkv')
}

function refererOf(url) {
    const at = url.indexOf('://')
    if (at > 0) {
        const rest = url.slice(at + 3)
        return url.slice(0, at + 3) + rest.split('/')[0] + '/'
    }
    return HOST + '/'
}

// ═══ 推荐流与聚合 ═══

async function homeOf(ctx, srcKey, timeout = TIMEOUT) {
    const ck = 'home:' + srcKey
    const hit = await ctx.cache.get(ck)
    if (hit) return hit
    const data = await postJson(ctx, API_HOME, {api: SOURCE_API[srcKey] || '', filter: true}, timeout)
    const home = (data && data.data) || {}
    home.list = home.list || []
    home.class = home.class || []
    if (home.list.length) await ctx.cache.set(ck, home, CACHE_TTL)
    return home
}

async function catPage(ctx, srcKey, tid, page) {
    const ck = 'p:' + srcKey + ':' + tid + ':' + page
    const hit = await ctx.cache.get(ck)
    if (hit) return hit
    const data = await postJson(ctx, API_CATEGORY,
        {api: SOURCE_API[srcKey], tid, page, filter: true, extend: {}}, CAT_TIMEOUT)
    const lst = (data && data.data && data.data.list) || []
    if (lst.length) await ctx.cache.set(ck, lst, CACHE_TTL)
    return lst
}

// 自适应步长：首页 ≥40 条时一页直达，否则一次翻页并行拉 CAT_PAGES 个源分页
async function catFetch(ctx, srcKey, tid, pg) {
    let steps = await ctx.cache.get('step:' + srcKey)
    if (!steps) steps = CAT_PAGES
    const first = await catPage(ctx, srcKey, tid, 1)
    let items = []
    if (first.length) {
        if (first.length >= CAT_MIN_ITEMS && pg <= 1) {
            await ctx.cache.set('step:' + srcKey, 1, CACHE_TTL)
            return first.slice(0, CAT_MAX)
        }
        items = first.slice()
    }
    const start = (pg - 1) * steps + 1
    const got = await Promise.all(
        Array.from({length: steps}, (_, i) => catPage(ctx, srcKey, tid, start + i)))
    const seen = new Set(items.map((v) => String(v.vod_id || '')))
    for (const r of got) {
        for (const v of r) {
            const vid = String(v.vod_id || '')
            if (vid && seen.has(vid)) continue
            seen.add(vid)
            items.push(v)
        }
    }
    return items.slice(0, CAT_MAX)
}

// 多源首页轮询穿插：每个源轮流出一张卡（py 的 _merge_by_source）
function interleave(buckets) {
    const out = []
    const total = buckets.reduce((n, b) => n + b.cards.length, 0)
    for (let idx = 0; out.length < total; idx++) {
        let added = false
        for (const b of buckets) {
            if (idx < b.cards.length) {
                out.push(b.cards[idx])
                added = true
            }
        }
        if (!added) break
    }
    return out
}

async function recommendList(ctx) {
    const hit = await ctx.cache.get('rec')
    if (hit) return hit
    // Promise.all 保序：buckets 天然按 REC_SOURCES 顺序
    const buckets = await Promise.all(REC_SOURCES.map(async (k) => {
        try {
            const home = await homeOf(ctx, k, REC_TIMEOUT)
            return {k, cards: home.list.slice(0, REC_PER_SRC).map((v) => card(k, v, true))}
        } catch {
            return {k, cards: []}
        }
    }))
    const merged = interleave(buckets)
    await ctx.cache.set('rec', merged, CACHE_TTL)
    return merged
}

async function searchAll(ctx, keys, kw) {
    // 各源并行搜，Promise.all 保序，源顺序即结果顺序
    const buckets = await Promise.all(keys.map(async (k) => {
        try {
            const data = await postJson(ctx, API_SEARCH, {api: SOURCE_API[k], keyword: kw}, SEARCH_TIMEOUT)
            const lst = (data && data.data) || []
            return (Array.isArray(lst) ? lst : []).slice(0, SEARCH_PER_SRC).map((v) => card(k, v, true))
        } catch {
            return []
        }
    }))
    const merged = []
    const seen = new Set()
    for (const cards of buckets) {
        for (const c of cards) {
            if (seen.has(c.vod_name)) continue
            seen.add(c.vod_name)
            merged.push(c)
        }
    }
    return rank(merged, kw).slice(0, SEARCH_MAX)
}

// 相关度排序：全等 > 前缀 > 包含(越靠前越好)；auto 模式真命中 ≥5 就只留真命中
function rank(cards, kw) {
    const k = String(kw || '').toLowerCase().replace(/ /g, '')
    const score = (c) => {
        const n = String(c.vod_name || '').toLowerCase().replace(/ /g, '')
        if (!n) return 900
        if (n === k) return 0
        if (n.startsWith(k)) return 1
        if (k && n.includes(k)) return 2 + n.indexOf(k)
        return 900
    }
    const hits = cards.filter((c) => score(c) < 900)
    let out = cards
    if (SEARCH_STRICT === true) out = hits
    else if (SEARCH_STRICT === 'auto' && hits.length >= 5) out = hits
    return out.slice().sort((a, b) => score(a) - score(b))
}

// 主源详情播不了时，拿片名去别的源搜同款，能播的那个顶上（py 的 _fallback_detail）
async function fallbackDetail(ctx, srcKey, name) {
    if (!name) return null
    const cached = await ctx.cache.get('search:' + name)
    const cands = []
    if (cached) {
        for (const c of cached) {
            const [k, rid] = decId(c.vod_id)
            if (k && k !== srcKey && !EXTRA_KEYS.includes(k)) cands.push([k, rid])
        }
    }
    if (!cands.length) {
        for (const k of SEARCH_ONLY.concat(REC_SOURCES)) {
            if (k === srcKey || !SOURCE_API[k]) continue
            const data = await postJson(ctx, API_SEARCH, {api: SOURCE_API[k], keyword: name}, SEARCH_TIMEOUT)
            const lst = (data && data.data) || []
            for (const v of (Array.isArray(lst) ? lst : []).slice(0, 3)) {
                if (v.vod_id) cands.push([k, String(v.vod_id)])
            }
        }
    }
    let tried = 0
    for (const [k, rid] of cands) {
        if (tried >= FALLBACK_TRY) break
        tried++
        const data = await postJson(ctx, API_DETAIL, {api: SOURCE_API[k], ids: [rid]}, 10000)
        const d = (data && data.data) || {}
        const url = fixPlayUrl(d.vod_play_url || '')
        if (!url) continue
        return {
            vod_id: encId(k, d.vod_id || rid),
            vod_name: d.vod_name || name,
            vod_pic: d.vod_pic || '',
            type_name: SOURCE_NAME[k] || '',
            vod_year: d.vod_year || '',
            vod_area: d.vod_area || '',
            vod_remarks: d.vod_remarks || 'HD',
            vod_actor: d.vod_actor || '',
            vod_director: d.vod_director || '',
            vod_content: String(d.vod_content || '').replace(/<[^>]+>/g, '').slice(0, 500),
            vod_play_from: d.vod_play_from || '播放',
            vod_play_url: url,
        }
    }
    return null
}

// ═══ 钩子 ═══

// 站点 API（全是 POST JSON）
const API_HOME = HOST + '/api/tvbox/home'
const API_CATEGORY = HOST + '/api/tvbox/category'
const API_SEARCH = HOST + '/api/search'
const API_DETAIL = HOST + '/api/detail'

export default {
    meta: {
        title: '魔法盒子',
        host: HOST,
        searchable: 2, filterable: 1, quickSearch: 0,
    },

    rule: {
        homeUrl: '/',
        // 详情不走 URL 模板：l98 的详情是 API POST，三个内置分支也各自实现
        detailUrl: HOST + '/',
        headers: HEADERS,
        timeout: TIMEOUT,
        // 静态分类 + 筛选面板交给声明式 home
        class_name: CLASSES.map((c) => c.name).join('&'),
        class_url: CLASSES.map((c) => c.id).join('&'),
        filter: FILTERS,
    },

    // 预热推荐流：不 await，后台跑，进首页时多半已有缓存
    async init(ctx) {
        recommendList(ctx).catch(() => {})
    },

    // 首页推荐：多源轮询（py 的 homeVideoContent；py 的 homeContent 单源列表 dr3 没有落点）
    async homeVod(ctx) {
        try {
            const rec = await recommendList(ctx)
            return {list: rec.slice(0, REC_LIMIT)}
        } catch {
            return {list: []}
        }
    },

    async category(ctx, tid, pg, filter, extend) {
        const page = Math.max(1, parseInt(pg, 10) || 1)
        let ext = extend
        if (typeof ext === 'string') {
            try {
                ext = JSON.parse(ext)
            } catch {
                ext = {}
            }
        }
        const fl = (ext && typeof ext === 'object' ? ext : null) || ctx.fl || {}
        const srcKey = srcOfTid(tid)
        try {
            if (srcKey === 'qiyou') return await qiyouCategory(ctx, String(fl.tid || '') || '1', page)

            if (srcKey === 'qukkan') {
                return await qkCategory(ctx, String(fl.tid || '') || 'all', page, String(fl.by || ''))
            }

            if (srcKey === 'qilin') {
                return await qilinCategory(ctx, String(fl.tid || '') || '1', page,
                    String(fl.year || ''), String(fl.area || ''))
            }

            // 影视推荐：多源轮询流，筛选 = 按来源过滤，客户端分页
            if (srcKey === REC_KEY) {
                let rec = await recommendList(ctx)
                const srcFilter = String(fl.src || '')
                if (srcFilter) rec = rec.filter((v) => String(v.vod_id).split('@')[0] === srcFilter)
                const pagecount = Math.max(1, Math.ceil(rec.length / REC_LIMIT))
                return {
                    list: rec.slice((page - 1) * REC_LIMIT, page * REC_LIMIT),
                    page,
                    pagecount,
                    limit: REC_LIMIT,
                    total: rec.length,
                }
            }

            if (!SOURCE_API[srcKey]) {
                return {page, pagecount: page, limit: 10, total: 0, list: []}
            }

            // 聚合源：没选子分类就给该源首页，选了就走自适应分页
            const subTid = String(fl.tid || '')
            if (!subTid) {
                const home = await homeOf(ctx, srcKey)
                const vods = (home.list || []).map((v) => card(srcKey, v, false))
                return {list: vods, page: 1, pagecount: 1, limit: vods.length || 10, total: vods.length}
            }

            const ck = 'cat:' + srcKey + ':' + subTid + ':' + page
            let rawList = await ctx.cache.get(ck)
            if (!rawList) {
                rawList = await catFetch(ctx, srcKey, subTid, page)
                if (rawList.length) await ctx.cache.set(ck, rawList, CACHE_TTL)
            }
            const vods = rawList.map((v) => card(srcKey, v, false))
            return {
                list: vods,
                page,
                // 前瞻式页数：有货就再给一页
                pagecount: vods.length ? page + 1 : page,
                limit: vods.length || 10,
                total: vods.length ? vods.length * page : 0,
            }
        } catch (e) {
            ctx.log('魔法盒子 分类失败: ' + e.message)
            return {page: 1, pagecount: 1, limit: 10, total: 0, list: []}
        }
    },

    async search(ctx, wd, quick, pg) {
        const kw = String(wd || '').trim()
        const page = Math.max(1, parseInt(pg, 10) || 1)
        if (!kw) return {page, pagecount: 1, limit: 0, total: 0, list: []}
        try {
            let all = await ctx.cache.get('search:' + kw)
            if (!all) {
                const keys = SEARCH_ALL
                    ? SOURCES.map((s) => s.key)
                    : SEARCH_ONLY.filter((k) => SOURCE_API[k])
                all = await searchAll(ctx, keys, kw)
                if (all.length) await ctx.cache.set('search:' + kw, all, CACHE_TTL)
            }
            // 内置分支结果只并入第 1 页（py 原版行为）；现拼现用，不污染缓存
            if (page === 1) {
                try {
                    const qk = await qkSearch(ctx, kw, 1)
                    all = all.concat(qk.list || [])
                } catch {}
                try {
                    const ql = await qilinSearch(ctx, kw, 1)
                    all = all.concat(ql.list || [])
                } catch {}
            }
            const total = all.length
            const pagecount = Math.max(1, Math.ceil(total / SEARCH_LIMIT))
            return {
                list: all.slice((page - 1) * SEARCH_LIMIT, page * SEARCH_LIMIT),
                page,
                pagecount,
                limit: SEARCH_LIMIT,
                total,
            }
        } catch (e) {
            ctx.log('魔法盒子 搜索失败: ' + e.message)
            return {page, pagecount: 1, limit: 0, total: 0, list: []}
        }
    },

    async detail(ctx, id) {
        const [srcKey, realId] = decId(id)
        if (!srcKey || !realId) return {list: []}
        if (srcKey === 'qiyou') return qiyouDetail(ctx, realId)
        if (srcKey === 'qukkan') return qkDetail(ctx, realId)
        if (srcKey === 'qilin') return qilinDetail(ctx, realId)

        const ck = 'd:' + srcKey + ':' + realId
        const hit = await ctx.cache.get(ck)
        if (hit) return {list: [hit]}

        // 详情 API 有时抽风，重试一轮
        let data = null
        for (let i = 0; i < 2; i++) {
            data = await postJson(ctx, API_DETAIL, {api: SOURCE_API[srcKey], ids: [realId]})
            if (data && data.success && data.data) break
            await sleep(400)
        }
        const d = (data && data.data) || null
        if (!d || !Object.keys(d).length) return {list: []}

        const playUrl = fixPlayUrl(d.vod_play_url || '')
        if (!playUrl && DETAIL_FALLBACK) {
            // 本源没播放地址：拿片名去别的源搜同款
            const alt = await fallbackDetail(ctx, srcKey, d.vod_name || '')
            if (alt) {
                await ctx.cache.set(ck, alt, DETAIL_TTL)
                return {list: [alt]}
            }
            return {list: []}
        }
        if (!playUrl) return {list: []}

        const vod = {
            vod_id: encId(srcKey, d.vod_id || realId),
            vod_name: d.vod_name || '',
            vod_pic: d.vod_pic || '',
            type_name: SOURCE_NAME[srcKey] || '',
            vod_year: d.vod_year || '',
            vod_area: d.vod_area || '',
            vod_remarks: d.vod_remarks || 'HD',
            vod_actor: d.vod_actor || '',
            vod_director: d.vod_director || '',
            vod_content: String(d.vod_content || '').replace(/<[^>]+>/g, '').slice(0, 500),
            vod_play_from: d.vod_play_from || '播放',
            vod_play_url: playUrl,
        }
        await ctx.cache.set(ck, vod, DETAIL_TTL)
        return {list: [vod]}
    },

    async play(ctx, flag, id, flags) {
        const raw = String(id || '').trim()
        if (!raw) return {parse: 0, jx: 0, url: ''}

        // 趣看看：带前缀，或详情里固化的 "albumId:seq" 格式
        if (raw.startsWith('qukkan@')) return qkPlayer(ctx, raw.slice('qukkan@'.length))
        if (/^\d+:\d+$/.test(raw)) return qkPlayer(ctx, raw)

        // 奇优：播放链接是 /play/ 代理页
        if (raw.includes('qiyou05.com')) {
            let playUrl = raw
            if (playUrl.includes('$')) playUrl = playUrl.split('$')[1]
            if (playUrl.includes('$')) playUrl = playUrl.split('$').pop()
            return qiyouPlayer(ctx, playUrl)
        }

        // 麒麟：qlys.cc 的 m3u8 直链
        if (raw.includes('qlys.cc')) return qilinPlayer(raw)

        let playUrl = absUrl(HOST, raw)
        playUrl = resolvePlay(playUrl)
        if (isMedia(playUrl)) {
            const isM3u8 = playUrl.toLowerCase().includes('m3u8')
            return {
                parse: 0, jx: 0, url: playUrl,
                header: {'User-Agent': UA, Referer: refererOf(playUrl)},
                format: isM3u8 ? 'application/x-mpegURL' : 'video/mp4',
                contentType: isM3u8 ? 'application/x-mpegURL' : 'video/mp4',
            }
        }
        // l98 自己的播放/媒体接口直接透传给播放器
        if (playUrl.includes(HOST) &&
            (playUrl.includes('/api/tvbox/play/') || playUrl.includes('/api/tvbox/media/'))) {
            return {parse: 0, jx: 0, url: playUrl, header: {'User-Agent': UA, Referer: HOST + '/'}}
        }
        // 都不是就交播放器嗅探
        return {parse: 1, jx: 0, url: playUrl, header: {'User-Agent': UA, Referer: HOST + '/'}}
    },
}