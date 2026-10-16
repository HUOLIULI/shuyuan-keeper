/*
@header({
  title: '七星七猫好看短剧',
  lang: 'dr3',
  searchable: 2, filterable: 0, quickSearch: 0,
})

【七星七猫好看短剧 dr3 移植】—— 三平台合一，对照 七星七猫好看短剧.py 逐环节对译
- 三家都是 JSON 接口、都有鉴权/签名，没有一个能用声明式引擎，六个环节全部手写
- 分类是动态的（七猫 59 个标签 + 好看 12 个标签，都得先请求才知道），home 也得写钩子

平台速写（2026-09 全部实测可用）：
  七星 app.whjzjx.cn
      登录  POST u.shytkjgs.com/user/v3/account/login
            载荷是 AES-128-ECB + PKCS7 + base64 的设备 JSON（密钥 B@ecf920Od8A4df7），
            换回 token 当 authorization 用。走 ctx.lib.crypto.aesX(..., {mode:'ECB', utf8:true})
      列表  GET /v1/theater/home_page?theater_class_id=&page_num=&page_size=
            data.total 给总数，page_num 实测有效（相邻页零重叠）
      详情  GET /v2/theater_parent/detail?theater_parent_id=
            data.theaters[].{num, son_video_url}，url 自带签名，直链
      搜索  POST /v3/search {text} -> data.theater.search_data[]

  七猫 api-store.qmplaylet.com（列表/搜索）+ api-read.qmplaylet.com（详情）
      鉴权  qm-params = base64(设备JSON) 经自定义字符表替换；sign = md5(拼接串 + 固定密钥)
            两个接口前缀不同，签名串也不同，逐个端点算（见 signStr）
      列表  GET /api/v1/playlet/index?tag_id=&next_id=&playlet_privacy=1&operation=1&sign=
            首页给 69 条，后续页很碎（3/5/3…），靠响应里的 next_id 续
      详情  GET /player/api/v1/playlet/info?playlet_id=&sign=
      搜索  GET /api/v1/playlet/search?wd=&page=&sign=   标题带 <font> 高亮标签，需剥标签

  好看 sv.baidu.com（百度好看）
      标签  POST /haokan/ui-feed/playletShelfFeed        body {"data":"{\"from\":\"feed\"}"}（JSON）
      列表  POST /haokan/ui-feed/playletTagsFeed        form 编码 {tag_id,pn,rn}，带 has_more
      选集  POST /appui/api?cmd=video/commonlist&...    form/JSON 均可，参数直接进 query

比 py 原版多做的：
- 好看的选集接口换了传参方式。原版把参数塞进 {"video/commonlist":"k=v&k=v"} 的嵌套 body，
  实测现在每个字段都回「非法请求」；改成全部走 query 后恢复正常（status=0 成功）。
  顺带去掉了那串 1000+ 字符的 URL 模板。
- 好看清晰度按 rank 取最高档（原版按数组下标取 [2]，数组顺序不保证）；
  另外三档全给，返回多线路而不是只给一条。
- 三家都按各自的真实翻页信号算页数：七星 total、七猫空页回收、好看 has_more。
  原版三家统一写 pagecount:9999 / total:999999，等于永远翻不到底。
- 好看搜索：原版调的 /haokan/ui-interact/playlet/search/sugs 现已全面「猜空了」
  （总裁/战神/重生等所有词都空），另试 3 个候选路径同样无效——已停用并在 search 里注明。

已知边界：
- 好看搜索停用，故 search 只覆盖七星 + 七猫。
- 好看选集接口忽略一切翻页参数，每页恒定返回前 10 集、has_more 恒为 1，
  所以长剧只能拿到前 10 集（87 集的实测如此）。这是上游限制，已在 hkEpisodes 注明。
- 好看封面字段 poster/preview_url 是 http 开头，未强制改 https（部分 CDN 不响应 https）。
*/

// ═══ 七星 ═══

const QX_BASE = 'https://app.whjzjx.cn'
const QX_LOGIN = 'https://u.shytkjgs.com/user/v3/account/login'
const QX_AES_KEY = 'B@ecf920Od8A4df7'
const QX_PAGE = 24
const QX_HEADERS = {platform: '1', version_name: '3.8.3.1'}
// 实测五个 class 都有内容；total 分别 24/294/844/18/203
const QX_CLASSES = [
    ['qx_1', '剧场'], ['qx_3', '新剧'], ['qx_2', '热播'], ['qx_7', '星选'], ['qx_5', '阳光'],
]

// ═══ 七猫 ═══

const QM_STORE = 'https://api-store.qmplaylet.com'
const QM_READ = 'https://api-read.qmplaylet.com'
const QM_KEYS = 'd3dGiJc651gSQ8w1'
// base64 字符表替换：把标准 64 字符换成站方自定义集（含 - 和 _）
const QM_CHARS = {
    '+': 'P', '/': 'X', 0: 'M', 1: 'U', 2: 'l', 3: 'E', 4: 'r', 5: 'Y', 6: 'W', 7: 'b',
    8: 'd', 9: 'J', A: '9', B: 's', C: 'a', D: 'I', E: '0', F: 'o', G: 'y', H: '_',
    I: 'H', J: 'G', K: 'i', L: 't', M: 'g', N: 'N', O: 'A', P: '8', Q: 'F', R: 'k',
    S: '3', T: 'h', U: 'f', V: 'R', W: 'q', X: 'C', Y: '4', Z: 'p', a: 'm', b: 'B',
    c: 'O', d: 'u', e: 'c', f: '6', g: 'K', h: 'x', i: '5', j: 'T', k: '-', l: '2',
    m: 'z', n: 'S', o: 'Z', p: '1', q: 'V', r: 'v', s: 'j', t: 'Q', u: '7', v: 'D',
    w: 'w', x: 'n', y: 'L', z: 'e',
}
const QM_DEVICE = {
    static_score: '0.8',
    uuid: '00000000-7fc7-08dc-0000-000000000000',
    'device-id': '20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70',
    mac: '', sourceuid: 'aa7de295aad621a6', 'refresh-type': '0', model: '22021211RC',
    'wlb-imei': '', 'client-id': 'aa7de295aad621a6', brand: 'Redmi', oaid: '',
    'oaid-no-cache': '', 'sys-ver': '12', 'trusted-id': '', 'phone-level': 'H',
    imei: '', 'wlb-uid': 'aa7de295aad621a6',
}

// ═══ 好看 ═══

const HK_BASE = 'https://sv.baidu.com'
const HK_UA = 'Mozilla/5.0 (Linux; U; Android 8.0.0; zh-cn; Mi Note 2 Build/OPR1.170623.032) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/61.0.3163.128 Mobile Safari/537.36'
const HK_HEADERS = {'User-Agent': HK_UA}
const HK_PAGE = 24
// 原版硬编码的「新剧」分区，shelf 标签表里没有但实测 tag_id=2 有内容
const HK_EXTRA_CLASS = ['hk_2', '好看-新剧']

const TIMEOUT = 10000

// ═══ 七星：登录与请求 ═══

// AES-128-ECB 登录换 token，实例级缓存；token 失效时上层会清缓存重取
async function qxToken(ctx) {
    const hit = await ctx.cache.get('qxTk')
    if (hit) return hit
    const payload = {
        device: '2a50580e69d38388c94c93605241fb306',
        package_name: 'com.jz.xydj',
        android_id: 'ec1280db12795506',
        install_first_open: true,
        first_install_time: 1752505243345,
        last_update_time: 1752505243345,
        report_link_url: '',
        authorization: '',
        timestamp: Date.now(),
    }
    try {
        // aesX 走 CryptoJS；mode=ECB + utf8:true 才是「明文进、base64 密文出」
        const body = ctx.lib.crypto.aesX(
            JSON.stringify(payload), QX_AES_KEY, undefined,
            {mode: 'ECB', method: 'enc', utf8: true},
        )
        const res = await ctx.lib.net.req(QX_LOGIN, {
            method: 'POST',
            body,
            timeout: TIMEOUT,
            headers: {
                ...QX_HEADERS,
                user_agent: 'Mozilla/5.0 (Linux; Android 9) AppleWebKit/537.36 ' +
                    'Chrome/91.0.4472.114 Safari/537.36',
                'content-type': 'application/json; charset=utf-8',
            },
        })
        const tk = JSON.parse(res.content)?.data?.token
        if (tk) await ctx.cache.set('qxTk', tk, 6 * 60 * 60 * 1000)
        return tk || ''
    } catch (e) {
        ctx.log('七星 登录失败: ' + e.message)
        return ''
    }
}

async function qxGet(ctx, path) {
    const tk = await qxToken(ctx)
    for (let i = 0; i < 2; i++) {
        try {
            const res = await ctx.lib.net.req(QX_BASE + path, {
                headers: {...QX_HEADERS, authorization: tk, 'User-Agent': 'Mozilla/5.0'},
                timeout: TIMEOUT,
            })
            const j = JSON.parse(res.content)
            if (j && j.code === 'ok') return j.data || {}
            ctx.log('七星 ' + path + ' 返回: ' + j?.code + ' ' + (j?.msg || ''))
        } catch (e) {
            ctx.log('七星 ' + path + ' 失败: ' + e.message)
        }
        if (i === 0) await ctx.cache.delete('qxTk')
    }
    return {}
}

function qxVod(x) {
    const t = x.theater || x
    if (!t || !t.id) return null
    return {
        vod_id: 'qx_' + t.id,
        vod_name: t.title || '',
        vod_pic: t.cover_url || '',
        vod_remarks: t.play_amount_str || t.theme || t.rank_tag_desc || '',
    }
}

async function qxList(ctx, cls, pg) {
    const path = `/v1/theater/home_page?theater_class_id=${cls}` +
        `&page_num=${pg}&page_size=${QX_PAGE}`
    const d = await qxGet(ctx, path)
    return {list: (d.list || []).map(qxVod).filter(Boolean), total: d.total || 0, isEnd: d.is_end}
}

// ═══ 七猫：签名与请求 ═══

// 每次现算：qm-params 里带时间戳 session-id，缓存反而容易拿到过期签名
function qmHeaders(ctx) {
    const params = {...QM_DEVICE, 'session-id': String(Date.now())}
    const raw = ctx.lib.crypto.base64Encode(JSON.stringify(params))
    const qm = [...raw].map((c) => QM_CHARS[c] || c).join('')
    const signStr = 'AUTHORIZATION=app-version=10001application-id=com.duoduo.read' +
        'channel=unknownis-white=net-env=5platform=android' + 'qm-params=' + qm + 'reg=' + QM_KEYS
    return {
        'net-env': '5', reg: '', channel: 'unknown', 'is-white': '', platform: 'android',
        'application-id': 'com.duoduo.read', authorization: '', 'app-version': '10001',
        'user-agent': 'webviewversion/0', 'qm-params': qm, sign: ctx.lib.crypto.md5(signStr),
    }
}

async function qmGet(ctx, host, path, signRaw) {
    const url = host + path + '&sign=' + ctx.lib.crypto.md5(signRaw + QM_KEYS)
    for (let i = 0; i < 2; i++) {
        try {
            const res = await ctx.lib.net.req(url, {headers: qmHeaders(ctx), timeout: TIMEOUT})
            return JSON.parse(res.content)?.data || {}
        } catch (e) {
            ctx.log('七猫 ' + path.slice(0, 46) + ' 失败: ' + e.message)
        }
    }
    return {}
}

function qmVod(x) {
    if (!x || !x.playlet_id) return null
    return {
        vod_id: 'qm_' + x.playlet_id,
        vod_name: String(x.title || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim(),
        vod_pic: x.image_link || '',
        vod_remarks: x.hot_value || (x.total_num ? '全' + x.total_num + '集' : ''),
    }
}

async function qmList(ctx, tag, pg) {
    // 首页不带 next_id；后续页把 next_id 拼进签名串（实测首页 69 条，后续页只有 3~5 条）
    const signRaw = pg > 1
        ? `next_id=${pg}operation=1playlet_privacy=1tag_id=${tag}`
        : `operation=1playlet_privacy=1tag_id=${tag}`
    const path = `/api/v1/playlet/index?tag_id=${tag}&playlet_privacy=1&operation=1`
        + (pg > 1 ? `&next_id=${pg}` : '')
    const d = await qmGet(ctx, QM_STORE, path, signRaw)
    return {list: (d.list || []).map(qmVod).filter(Boolean), nextId: d.next_id}
}

// ═══ 好看：请求与解析 ═══

// shelf 用 JSON 体，tagsFeed / commonlist 用 form 编码 —— 三个端点编码方式不一致
async function hkPost(ctx, path, obj, form) {
    try {
        const res = await ctx.lib.net.req(HK_BASE + path, {
            method: 'POST',
            headers: form
                ? {...HK_HEADERS, 'content-type': 'application/x-www-form-urlencoded'}
                : {...HK_HEADERS, 'content-type': 'application/json'},
            body: form ? new URLSearchParams(obj).toString() : JSON.stringify(obj),
            timeout: TIMEOUT,
        })
        return JSON.parse(res.content) || {}
    } catch (e) {
        ctx.log('好看 ' + path.slice(-30) + ' 失败: ' + e.message)
        return {}
    }
}

function hkVod(x) {
    if (!x || !x.playlet_id) return null
    return {
        vod_id: 'hk_' + x.playlet_id,
        vod_name: x.playlet_title || '',
        vod_pic: x.playlet_poster || x.cover_url || '',
        vod_remarks: x.episodes_num_text || (x.hot_value ? x.hot_value + ' 热度' : ''),
    }
}

async function hkTags(ctx) {
    const d = await hkPost(ctx, '/haokan/ui-feed/playletShelfFeed',
        {data: JSON.stringify({from: 'feed'})}, false)
    return d.data?.playlet_tags || []
}

async function hkList(ctx, tag, pg) {
    const d = await hkPost(ctx, '/haokan/ui-feed/playletTagsFeed',
        {tag_id: String(tag), pn: String(pg), rn: String(HK_PAGE)}, true)
    const data = d.data || {}
    return {list: (data.list || []).map(hkVod).filter(Boolean), hasMore: !!data.has_more}
}

// 选集：参数全部走 query。原版用的 {"video/commonlist":"k=v&..."} 嵌套体
// 现在每个字段都被判「非法请求」，改 query 后恢复（实测 status=0）
// ⚠ 硬上限：接口忽略一切翻页参数（pn/page/start/offset/rn 组合共 15 种变体全试过），
//   每页恒定返回前 10 集，has_more 永远是 1。所以只取一次，不要循环翻页——
//   那样只会把同一批数据重复请求 N 遍。87 集的剧只能拿到前 10 集，这是上游限制。
async function hkEpisodes(ctx, id) {
    const q = new URLSearchParams({
        cmd: 'video/commonlist', log: 'vhk', tn: '1043677m', ctn: '1043677m', blur: '1',
        os: 'android', apiv: '7.93.0.18', appv: '793001', version: '7.93.0.18',
        is_playlet: '1', from: 'playlet_talos', source_from: 'kanju_shelf_playlet',
        type: 'playlet', page_value: 'playlet', rn: '50', pn: '1', direction: '3',
        id: String(id), commonlist_id: String(Date.now()),
        // 每次换随机设备标识，站方会按 uid 记播放进度
        cuid: hex(32).toUpperCase() + '%7C0', zid: hex(32), androidId: hex(16),
    })
    let d
    try {
        const res = await ctx.lib.net.req(HK_BASE + '/appui/api?' + q.toString(), {
            method: 'POST',
            headers: {...HK_HEADERS, 'content-type': 'application/json'},
            body: '{}',
            timeout: TIMEOUT,
        })
        d = JSON.parse(res.content) || {}
    } catch (e) {
        ctx.log('好看 选集失败: ' + e.message)
        return []
    }
    const rows = d['video/commonlist']?.data?.results || []
    const out = []
    for (const r of rows) {
        const c = r.content
        if (!c) continue
        // 标题形如「剧名-第1集」，集号那截单独抽出来，剧名前缀留给 detail 还原剧名
        const m = String(c.title || '').match(/(第\s*\d+\s*集)/)
        out.push({
            name: m ? m[1] : String(c.title || ''),
            rawTitle: String(c.title || ''),
            clarity: c.clarityUrl || [],
        })
    }
    return out
}

function hex(n) {
    let s = ''
    while (s.length < n) s += Math.floor(Math.random() * 0xffffffff).toString(16)
    return s.slice(0, n)
}

// 清晰度按 rank 取最高档，别信数组下标（原版取 clarity_urls[2]）
function bestClarity(list) {
    let best = null
    for (const c of list || []) {
        if (!c || !c.url) continue
        if (!best || Number(c.rank || 0) > Number(best.rank || 0)) best = c
    }
    return best
}

// ═══ 工具 ═══

// id 形如 qx_123 / qm_456 / hk_789
function splitId(id) {
    const s = String(id || '')
    const i = s.indexOf('_')
    return i < 0 ? ['', s] : [s.slice(0, i), s.slice(i + 1)]
}

function clean(v) {
    const s = String(v ?? '').trim()
    return s === '暂无' || s === '未知' || s === 'null' || s === 'None' ? '' : s
}

// 空页回收：翻过头时页数落到实际末页（别写成 max(n, page)，会把这一分支吃掉）
function pagecountOf(page, hasMore) {
    return hasMore ? page + 1 : page
}

// ═══ 钩子 ═══

export default {
    meta: {
        title: '七星七猫好看短剧',
        host: HK_BASE,
        searchable: 2, filterable: 0, quickSearch: 0,
    },

    rule: {
        timeout: TIMEOUT,
        // 三家全是 JSON 接口且带鉴权，声明式引擎只发 GET，六个环节一律手写
    },

    // 预热七星 token：不预热的话第一个列表请求会先 401 再重登
    async init(ctx) {
        await qxToken(ctx)
    },

    // 分类：七星 5 个静态 + 七猫标签（带组名）+ 好看标签
    async home(ctx, filter) {
        const classes = QX_CLASSES.map(([id, name]) => ({type_id: id, type_name: '七星-' + name}))

        // 七猫 5 组标签：精选/背景/情节/角色/风格，「推荐」是默认项不进面板
        try {
            const d = await qmGet(ctx, QM_STORE,
                '/api/v1/playlet/index?tag_id=0&playlet_privacy=1&operation=1',
                'operation=1playlet_privacy=1tag_id=0')
            for (const grp of d.tag_categories || []) {
                const gname = grp.name || grp.tag_name || ''
                for (const t of grp.tags || []) {
                    if (!t.tag_id || String(t.tag_name).includes('推荐')) continue
                    classes.push({
                        type_id: 'qm_' + t.tag_id,
                        type_name: '七猫-' + (gname ? gname + '·' : '') + t.tag_name,
                    })
                }
            }
        } catch (e) {
            ctx.log('七猫 标签拉取失败: ' + e.message)
        }

        for (const t of await hkTags(ctx)) {
            if (t.tag_id != null) {
                classes.push({type_id: 'hk_' + t.tag_id, type_name: '好看-' + t.name})
            }
        }
        classes.push({type_id: HK_EXTRA_CLASS[0], type_name: HK_EXTRA_CLASS[1]})
        return {class: classes}
    },

    // 推荐：三平台各取一坨拼一起
    async homeVod(ctx) {
        const [qx, qm, hk] = await Promise.all([
            qxList(ctx, 1, 1).catch(() => ({list: []})),
            qmList(ctx, 0, 1).catch(() => ({list: []})),
            hkList(ctx, 1, 1).catch(() => ({list: []})),
        ])
        return {list: [...(qx.list || []).slice(0, 12), ...(qm.list || []).slice(0, 12),
            ...(hk.list || []).slice(0, 12)]}
    },

    async category(ctx, tid, pg, filter, extend) {
        const page = pg || 1
        const [pfx, pid] = splitId(tid)
        if (pfx === 'qx') {
            const r = await qxList(ctx, pid, page)
            const total = r.total || 0
            let n = total > 0 ? Math.ceil(total / QX_PAGE) : pagecountOf(page, !r.isEnd)
            if (!r.list.length && page > 1) n = page - 1
            return {page, pagecount: Math.max(1, n), limit: QX_PAGE, total, list: r.list}
        }
        if (pfx === 'qm') {
            const r = await qmList(ctx, pid, page)
            let n = pagecountOf(page, r.list.length > 0)
            if (!r.list.length && page > 1) n = page - 1
            return {page, pagecount: Math.max(1, n), limit: 69, total: 0, list: r.list}
        }
        if (pfx === 'hk') {
            const r = await hkList(ctx, pid, page)
            let n = pagecountOf(page, r.hasMore)
            if (!r.list.length && page > 1) n = page - 1
            return {page, pagecount: Math.max(1, n), limit: HK_PAGE, total: 0, list: r.list}
        }
        return {page, pagecount: 1, limit: 0, total: 0, list: []}
    },

    async detail(ctx, id) {
        const [pfx, pid] = splitId(id)
        if (pfx === 'qx') return {list: (await qxDetail(ctx, pid)).filter(Boolean)}
        if (pfx === 'qm') return {list: (await qmDetail(ctx, pid)).filter(Boolean)}
        if (pfx === 'hk') return {list: (await hkDetail(ctx, pid)).filter(Boolean)}
        return {list: []}
    },

    // 三家都是详情页里就带好签名直链，play 只透传（UA 按平台给，好看 CDN 会校验）
    async play(ctx, flag, id, flags) {
        const url = String(id || '')
        if (!/^https?:\/\//i.test(url)) {
            ctx.log('播放 id 不是直链: ' + url)
            return {parse: 0, url: ''}
        }
        return {parse: 0, url, header: {'User-Agent': flag === '好看' ? HK_UA : 'Mozilla/5.0'}}
    },

    // 搜索：好看的搜索端点已下线（实测所有关键词返回「猜空了」），只搜七星 + 七猫
    async search(ctx, wd, quick, pg) {
        const kw = String(wd || '').trim()
        if (!kw) return {page: 1, pagecount: 1, limit: 0, total: 0, list: []}
        const [qx, qm] = await Promise.all([qxSearch(ctx, kw), qmSearch(ctx, kw, pg || 1)])
        const list = [...qx, ...qm]
        return {page: pg || 1, pagecount: 1, limit: list.length, total: list.length, list}
    },
}

// ═══ 三家详情 ═══

async function qxDetail(ctx, pid) {
    const d = await qxGet(ctx, `/v2/theater_parent/detail?theater_parent_id=${pid}`)
    if (!d.title && !d.theaters) return []
    const eps = (d.theaters || []).map((t, i) => ({
        name: t.num != null ? '第' + t.num + '集' : '第' + (i + 1) + '集',
        url: t.son_video_url || '',
    })).filter((e) => e.url)
    const tags = (d.desc_tags || []).filter(Boolean)
    const rem = []
    if (d.score) rem.push('评分 ' + d.score)
    if (d.quality_grade) rem.push('评级 ' + d.quality_grade)
    if (clean(d.filing)) rem.push(clean(d.filing).slice(0, 16))
    if (d.total) rem.push('全' + d.total + '集')
    const vod = {
        vod_id: 'qx_' + pid,
        vod_name: d.title || '',
        vod_pic: d.cover_url || d.share_cover || '',
        type_name: tags.slice(0, 3).join('/'),
        vod_year: '', vod_area: '',
        vod_remarks: rem.join(' '),
        vod_actor: '', vod_director: '',
        vod_content: clean(d.introduction),
        vod_play_from: '七星',
    }
    vod.vod_play_url = (eps.length ? eps : []).map((e) => e.name + '$' + e.url).join('#')
    return [vod]
}

async function qmDetail(ctx, pid) {
    const d = await qmGet(ctx, QM_READ, `/player/api/v1/playlet/info?playlet_id=${pid}`,
        `playlet_id=${pid}`)
    if (!d.title && !d.play_list) return []
    const eps = (d.play_list || []).map((x) => ({
        name: x.sort != null ? String(x.sort) : (x.title || ''), url: x.video_url || '',
    })).filter((e) => e.url)
    const rem = []
    if (d.total_episode_num) rem.push('全' + d.total_episode_num + '集')
    if (d.is_over) rem.push('已完结')
    const vod = {
        vod_id: 'qm_' + pid,
        vod_name: clean(d.title),
        vod_pic: d.image_link || '',
        type_name: clean(d.tags).slice(0, 20),
        vod_year: '', vod_area: '',
        vod_remarks: rem.join(' '),
        vod_actor: '', vod_director: '',
        vod_content: clean(d.intro),
        vod_play_from: '七猫',
    }
    vod.vod_play_url = eps.map((e) => e.name + '$' + e.url).join('#')
    return [vod]
}

async function hkDetail(ctx, pid) {
    const eps = await hkEpisodes(ctx, pid)
    // 选集接口的 content.title 形如「剧名-第1集」，集名已单独抽出，
    // 剩下的前缀就是剧名；接口本身不返回剧名字段
    const firstTitle = eps[0] ? String(eps[0].rawTitle || '') : ''
    const drama = firstTitle.replace(/[-—]\s*第\s*\d+\s*集\s*$/, '').trim()
    const list = eps.map((e) => {
        const best = bestClarity(e.clarity)
        return best ? e.name + '$' + best.url : ''
    }).filter(Boolean)
    const vod = {
        vod_id: 'hk_' + pid,
        vod_name: drama,
        vod_pic: '', type_name: '短剧',
        vod_year: '', vod_area: '',
        // 如实告知只拿到前 10 集，别让用户以为整部都在
        vod_remarks: eps.length ? '前' + eps.length + '集（接口只给这些）' : '',
        vod_actor: '', vod_director: '',
        vod_content: '',
        vod_play_from: '好看',
        vod_play_url: list.join('#'),
    }
    return [vod]
}

// ═══ 三家搜索 ═══

async function qxSearch(ctx, kw) {
    try {
        const tk = await qxToken(ctx)
        const res = await ctx.lib.net.req(QX_BASE + '/v3/search', {
            method: 'POST',
            headers: {...QX_HEADERS, authorization: tk, 'content-type': 'application/json',
                'User-Agent': 'Mozilla/5.0'},
            body: JSON.stringify({text: kw}),
            timeout: TIMEOUT,
        })
        const rows = JSON.parse(res.content)?.data?.theater?.search_data || []
        return rows.map((x) => ({
            vod_id: 'qx_' + x.id,
            vod_name: x.title || '',
            vod_pic: x.cover_url || '',
            vod_remarks: x.score_str || (x.total ? '全' + x.total + '集' : ''),
        })).filter((v) => v.vod_id !== 'qx_undefined')
    } catch (e) {
        ctx.log('七星 搜索失败: ' + e.message)
        return []
    }
}

async function qmSearch(ctx, kw, page) {
    const track = 'ec1280db127955061754851657967'
    const path = `/api/v1/playlet/search?extend=&page=${page}&wd=${encodeURIComponent(kw)}` +
        `&read_preference=0&track_id=${track}`
    const d = await qmGet(ctx, QM_STORE, path,
        `extend=page=${page}read_preference=0track_id=${track}wd=${kw}`)
    return (d.list || []).map((x) => ({
        vod_id: 'qm_' + x.id,
        vod_name: String(x.title || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim(),
        vod_pic: x.image_link || '',
        vod_remarks: x.total_num ? '全' + x.total_num + '集' : '',
    })).filter((v) => v.vod_id !== 'qm_undefined')
}
