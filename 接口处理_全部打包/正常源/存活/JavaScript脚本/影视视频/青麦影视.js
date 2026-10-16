/*
@header({
  title: '青麦影视',
  lang: 'dr3',
  searchable: 2, filterable: 1, quickSearch: 0,
})

【青麦影视 dr3 移植】—— 对照 青麦影视.py 逐环节对译
- 站点是 POST + JSON 接口（screenMovie / searchMovie / movieDesc / movieDetails），
  声明式引擎只发 GET，列表/搜索/详情/播放四个环节都得手写钩子
- 分类与筛选面板能全声明式（class_name / class_url / filter），home 一个钩子都没写
- 认证：/api/auth/deviceIdLogin 换 JWT，带上后 movieDetails 才有选集与播放地址
  （实测不带 token 时 movieDesc 正常、movieDetails 返回 0 集且 url 为空）
- vod_id 用 "typeId@@id" —— 正好是 drpy3 的原生透传约定（callStage 原样传参，
  拆 @@ 只发生在默认 detail 实现内部，不会截断钩子收到的 id）

接口（2026-09 实测，字段名与 py 原版一致）：
  POST /api/auth/deviceIdLogin?deviceId=…  {}            -> data = JWT（有效期约 90 天）
  POST /api/v1/pc/screen/screenMovie  {condition,pageNum,pageSize}
        condition = {typeId, sreecnTypeEnum, source, region?, classify?, year?}
        -> data.{records,total}    typeId: M16电影/M15电视剧/M17动漫/M18综艺/M416纪录片
        sreecnTypeEnum: HOT / NEWEST / COLLECT（实测 RATE、COMMENT 返回 0，不进面板）
  POST /api/v1/pc/search/searchMovie {condition:{value},pageNum,pageSize}
        -> data.{records,total,pages}   支持分页（实测「爱」total=234 / 47 页）
  POST /api/v1/pc/play/movieDesc     {id,playerId:90,typeId} -> data（元信息，不需要 token）
  POST /api/v1/pc/play/movieDetails  {id,playerId:90,episodeId,typeId}
        -> data.{url, episodeList[{id,episode,episodeNum,lock}], moviePlayerList, actorList}

播放地址是「多清晰度塞进一个串」：'4K*地址～HD*地址～LD*地址'，已按线路拆开返回。

比 py 原版多做的：
- 拆多清晰度 → 3 条线路（4K/HD/LD）都返回，而不是只取第一条
- 锁集标记：episodeList[].lock 原版完全没用；实测锁集照样给可播地址（200 #EXTM3U），
  所以照常放出，只在集名后加「(锁)」提示
- 搜索支持翻页（原版把 pageNum 写死 1，234 条结果只能看前 30）
- 补上筛选面板：原版一个 filter 配置都没写，面板根本不会渲染
- 简介里的 & 换成 ／（原版做法，避免播放器把 & 当参数分隔符）
*/

const HOST = 'https://www.qingmaisp.com'
const TIMEOUT = 8000
const PAGE_SIZE = 30
// deviceId = base64("TVBoxQMSP00000001")；写死常量，免得依赖宿主的 base64 实现
const DEVICE = 'VFZCb3hRTVNQMDAwMDAwMDE='
// JWT 有效期约 90 天，缓存一天足够，也留出失效后重登的余量
const TOKEN_TTL = 24 * 60 * 60 * 1000

const UA = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/120.0.0.0 Mobile Safari/537.36'

// 四个接口共用的请求头；token / deviceId 按需追加
const HEADERS = {
    'User-Agent': UA,
    'Content-Type': 'application/json;charset=UTF-8',
    client: 'pc',
    devicetype: 'web',
    useclient: 'pc',
    Referer: HOST + '/',
}

const PLAY_HEADERS = {'User-Agent': UA, Referer: HOST + '/'}

// ═══ 端点 ═══
// 三个端点路径集中放一处，钩子里不散落字符串
const LIST_PATH = '/api/v1/pc/screen/screenMovie'
const SEARCH_PATH = '/api/v1/pc/search/searchMovie'
const DESC_PATH = '/api/v1/pc/play/movieDesc'
const DETAILS_PATH = '/api/v1/pc/play/movieDetails'

// ═══ 请求层 ═══

// deviceIdLogin 换 token，实例级缓存
async function token(ctx) {
    const hit = await ctx.cache.get('tk')
    if (hit) return hit
    const data = await post(ctx, '/api/auth/deviceIdLogin?deviceId=' + DEVICE, {}, false)
    const tk = data.token || ''
    if (tk) await ctx.cache.set('tk', tk, TOKEN_TTL)
    return tk
}

// 走 req + 显式 method/data：d.ts 的 ReqOptions 契约（data 在非 GET 时作请求体）
// 认证失败时清一次 token 重试，对齐 py 原版 _p 的降级逻辑
async function post(ctx, path, payload, auth = true) {
    for (let attempt = 0; attempt < 2; attempt++) {
        const headers = {...HEADERS}
        if (auth) {
            const tk = await token(ctx)
            if (tk) {
                headers.token = tk
                headers.deviceId = DEVICE
            }
        }
        try {
            const res = await ctx.lib.net.req(HOST + path, {
                method: 'POST',
                data: payload || {},
                headers,
                timeout: TIMEOUT,
            })
            const json = JSON.parse(res.content)
            if (json && json.code === 200) {
                // 登录接口把 JWT 直接放在 data 上，其余接口的 data 是对象
                return typeof json.data === 'string' ? {token: json.data} : (json.data || {})
            }
            ctx.log('青麦 ' + path + ' 返回异常: code=' + json?.code + ' msg=' + json?.msg)
        } catch (e) {
            ctx.log('青麦 ' + path + ' 失败: ' + e.message)
        }
        if (auth && attempt === 0) await ctx.cache.delete('tk')
    }
    return {}
}

// ═══ 工具 ═══

function toVods(records) {
    const out = []
    for (const x of records || []) {
        if (!x || !x.id) continue
        // 站方给 remarks（如「已完结」）就用，否则按总集数兜底
        const rem = x.remarks
            || (Number.isInteger(x.totalEpisode) && x.totalEpisode > 1 ? '全' + x.totalEpisode + '集' : '高清')
        out.push({
            vod_id: (x.typeId || 'M') + '@@' + x.id,
            vod_name: x.name || '',
            vod_pic: x.cover || '',
            vod_remarks: rem,
            vod_year: String(x.year || ''),
        })
    }
    return out
}

// 站方用「暂无」占位缺失字段，直接上屏很突兀，统一清成空
function clean(v) {
    const s = String(v ?? '').trim()
    return s === '暂无' || s === '未知' ? '' : s
}

// 站方把多清晰度塞在一个串里：'4K*地址～HD*地址～LD*地址'，拆成 [名,址,名,址,…]
function splitLines(raw) {
    const urls = []
    for (const seg of String(raw || '').split('～')) {
        const i = seg.indexOf('*')
        if (i < 1) continue
        const u = seg.slice(i + 1).trim()
        if (u) urls.push(seg.slice(0, i).trim() || '播放', u)
    }
    return urls
}

// ═══ 筛选配置（取值逐个实测过，见文件头；RATE/COMMENT/韩剧/国产 返回 0 故不列）═══
const FILTERS = [
    {
        key: 'sort', name: '排序',
        value: [
            {n: '热门', v: 'HOT'},
            {n: '最新', v: 'NEWEST'},
            {n: '最多收藏', v: 'COLLECT'},
        ],
    },
    {
        key: 'region', name: '地区',
        value: [
            {n: '全部', v: ''},
            {n: '美国', v: '美国'},
            {n: '日本', v: '日本'},
            {n: '韩国', v: '韩国'},
            {n: '英国', v: '英国'},
            {n: '法国', v: '法国'},
            {n: '泰国', v: '泰国'},
            {n: '中国', v: '中国'},
            {n: '中国台湾', v: '中国台湾'},
            {n: '其他', v: '其他'},
        ],
    },
    {
        key: 'classify', name: '题材',
        value: [
            {n: '全部', v: ''},
            {n: '剧情', v: '剧情'},
            {n: '连续', v: '连续'},
            {n: '欧美', v: '欧美'},
            {n: '犯罪', v: '犯罪'},
            {n: '喜剧', v: '喜剧'},
            {n: '爱情', v: '爱情'},
            {n: '悬疑', v: '悬疑'},
            {n: '恐怖', v: '恐怖'},
            {n: '科幻', v: '科幻'},
            {n: '动画', v: '动画'},
            {n: '综艺', v: '综艺'},
            {n: '战争', v: '战争'},
            {n: '纪录片', v: '纪录片'},
        ],
    },
    {
        key: 'year', name: '年份',
        value: [
            {n: '全部', v: ''},
            {n: '2026', v: '2026'},
            {n: '2025', v: '2025'},
            {n: '2024', v: '2024'},
            {n: '2023', v: '2023'},
            {n: '2022', v: '2022'},
            {n: '2021', v: '2021'},
            {n: '2020', v: '2020'},
            {n: '2019', v: '2019'},
            {n: '2018', v: '2018'},
            {n: '2015', v: '2015'},
            {n: '2010', v: '2010'},
        ],
    },
]

// ═══ 钩子 ═══

export default {
    meta: {
        title: '青麦影视',
        host: HOST,
        searchable: 2, filterable: 1, quickSearch: 0,
    },

    rule: {
        headers: HEADERS,
        timeout: TIMEOUT,
        // 静态分类 + 筛选面板交给声明式 home 渲染，一个钩子都不用写
        class_name: '电影&电视剧&动漫&综艺&纪录片',
        class_url: 'M16&M15&M17&M18&M416',
        filter: {
            M16: FILTERS, M15: FILTERS, M17: FILTERS, M18: FILTERS, M416: FILTERS,
        },
    },

    // 预热 token：首个列表请求就不用多等一次登录
    async init(ctx) {
        await token(ctx)
    },

    async homeVod(ctx) {
        // 声明式推荐只能发 GET，这里是 POST，手写；取最新而非热门，与 py 原版一致
        const d = await post(ctx, LIST_PATH, {condition: {sreecnTypeEnum: 'NEWEST', typeId: 'M'},
            pageNum: 1, pageSize: PAGE_SIZE})
        return {list: toVods(d.records)}
    },

    async category(ctx, tid, pg, filter, extend) {
        const page = pg || 1
        const fl = (extend && typeof extend === 'object' ? extend : null) || ctx.fl || {}
        // sort 在面板里是 sort，落到接口上是 sreecnTypeEnum
        const condition = {typeId: tid, sreecnTypeEnum: fl.sort || 'HOT', source: '0'}
        for (const k of ['region', 'classify', 'year']) {
            if (fl[k]) condition[k] = fl[k]
        }
        const d = await post(ctx, LIST_PATH, {condition, pageNum: page, pageSize: PAGE_SIZE})
        const list = toVods(d.records)
        const total = d.total || 0
        let pagecount = total > 0 ? Math.ceil(total / PAGE_SIZE) : 1
        // 空页回收：翻过头时把页数落到实际末页。
        // 注意别写成 max(n, page)——py 原版就是那么写的，结果这一分支被 max 吃掉、
        // pagecount 恒等于当前页，越界后播放器会一直停在幽灵页上。
        if (!list.length && page > 1) pagecount = page - 1
        return {page, pagecount: Math.max(1, pagecount), limit: PAGE_SIZE, total, list}
    },

    async search(ctx, wd, quick, pg) {
        const page = pg || 1
        const kw = String(wd || '').trim()
        if (!kw) return {page: 1, pagecount: 1, limit: PAGE_SIZE, total: 0, list: []}
        const d = await post(ctx, SEARCH_PATH, {condition: {value: kw}, pageNum: page, pageSize: PAGE_SIZE})
        const list = toVods(d.records)
        return {
            page,
            // 接口自带 pages，比拿 total 除更准
            pagecount: d.pages || (list.length >= PAGE_SIZE ? page + 1 : page),
            limit: PAGE_SIZE,
            total: d.total || list.length,
            list,
        }
    },

    // id 形如 "typeId@@id"；元信息与选集表互不依赖，并发取
    async detail(ctx, id) {
        const [typeId, mid] = String(id).split('@@')
        if (!mid) return {list: []}
        const [d, e] = await Promise.all([
            post(ctx, DESC_PATH, {id: mid, playerId: 90, typeId}),
            post(ctx, DETAILS_PATH, {id: mid, playerId: 90, episodeId: null, typeId}),
        ])
        if (!d.name && !e.name) return {list: []}

        const eps = e.episodeList || []
        const play = eps.map((x) => {
            const name = x.episode || ('第' + (x.episodeNum ?? '?') + '集')
            // lock 是站方的付费标记，但实测锁集照样给可播地址，所以照常放出只加提示
            return (x.lock ? name + '(锁)' : name) + '$' + typeId + '@@' + mid + '@@' + (x.id ?? '')
        })

        const rem = []
        if (d.score) rem.push('评分 ' + d.score)
        if (d.year) rem.push(d.year)
        if (d.totalEpisode) rem.push('全' + d.totalEpisode + '集')

        const vod = {
            vod_id: String(id),
            vod_name: d.name || e.name || '',
            vod_pic: d.cover || '',
            type_name: clean(d.classify),
            vod_year: clean(d.year),
            vod_area: clean(d.area),
            vod_remarks: rem.join(' '),
            vod_actor: clean(d.star),
            vod_director: clean(d.director),
            // 简介里的 & 会让播放器误当参数分隔符，换成全角
            vod_content: clean(d.introduce).replace(/&/g, '／'),
            vod_play_from: '青麦',
        }
        // 选集拿不到时给个正片兜底，页面至少可点
        vod.vod_play_url = (play.length ? play : ['正片$' + typeId + '@@' + mid + '@@']).join('#')
        return {list: [vod]}
    },

    // 播放：id 形如 "typeId@@id@@episodeId"；空集号即正片
    async play(ctx, flag, id, flags) {
        const p = String(id).split('@@')
        const typeId = p[0] || 'M'
        const mid = p[1] || ''
        const ep = p[2] && p[2] !== 'null' ? Number(p[2]) : null
        if (!mid) return {parse: 0, url: ''}

        const d = await post(ctx, DETAILS_PATH, {id: mid, playerId: 90, episodeId: ep, typeId})
        const urls = splitLines(d.url)
        if (!urls.length) {
            ctx.log('青麦 无播放地址: ' + id)
            return {parse: 0, url: ''}
        }
        // urls 给多线路；同时给 url 兜底，只认 url 的客户端也能播（默认取最高清晰度）
        return {parse: 0, url: urls[1], urls, header: PLAY_HEADERS}
    },
}
