/*
@header({
  title: '看剧AI',
  lang: 'dr3',
  searchable: 2, filterable: 0, quickSearch: 0,
})

【看剧AI dr3 移植】—— 对照 看剧AI.py 逐环节对译
- 站点是 HMAC-SHA256 签名的 JSON API，签名串 "{METHOD}\n{path+query}\n{ts_ms}\n{nonce}"
  → hex，放进 x-ai-movie-timestamp / x-ai-movie-nonce / x-ai-movie-signature 三个头
- 列表/搜索/详情/播放全是签名 GET，解析线路是签名 POST，声明式引擎一条都用不上
- 分类是静态五个（movie/series/anime/variety/short_drama），交给声明式 home

为什么文件里自带 SHA-256 / HMAC 实现：
  drpy3 的 ctx.lib.crypto 只有 md5 / base64 / gzip / aesX / desX / rc4 / rsaX，
  既没有 sha256 也没有 hmac，而这个站的签名绕不开。纯 JS 实现已对着 Python 的
  hashlib/hmac 逐值比对过（含超长密钥、含中文消息、真实签名串，见 tools/verify-kanju.mjs）。

接口（2026-09 实测全部 200）：
  GET  /v1/feed/home                          {sections:[{title,cards:[…]}]} 8 个板块
  GET  /v1/browse/catalog?kind=&page=&limit=  {cards, pagination:{total,has_more,next_page}}
  GET  /v1/browse/catalog?q=&page=&limit=    同上，搜索
  GET  /v1/catalog/{id}                       详情，含 episodes[{number,title,token}]
  GET  /v1/catalog/{id}/episodes              详情没带 episodes 时的兜底
  GET  /v1/playback/resolve/{token}           {line_options:[…]} 一集的全部线路
  POST /v1/playback/resolve-line              {ticket,line,provider_id,play_from} → {line:{url}}

修掉的原版问题（实测复现）：
1) 播放永远走嗅探，解析接口形同虚设
   原版 playerContent 里有一句 `if not token.startswith("YJ-"): 交给播放器嗅探`。
   但站点现在下发的 token 一律是 "av_…" 开头（实测），没有 "YJ-" 这回事，
   于是每一集都命中这个分支直接嗅探，resolve / resolve-line 两个接口从没被走到过。
   去掉该前缀判断，改成「先尝试解析，确实换不到才回退嗅探」。
2) 线路排序靠 provider_name 里有「资源」二字
   原版 line_rank 用 name.contains("资源") 判断是不是直链，属于按文案猜。
   接口本身就给了 url_kind 字段（实测 m3u8×20 + resolve_ticket×3），直接按它分。
3) 官方线路其实放不出来
   实测 resolve_ticket 换出的官方地址（字节 ixigua）直连返回 403 —— 官方站要各自的
   Referer/凭据，不是本接口能覆盖的。所以把资源类 m3u8 直链排在前面（实测能播），
   官方线路只作兜底；换出来 403 的照常交播放器，不硬吞。

另外：
- resolve 结果按 token 缓存 5 分钟（一集一套线路，短时间不变），省掉切集时的重复请求
- 卡片上的 heat_value / playback_count 原版没取，现在并进备注
- 列表接口 limit 实测可调，30 → 50 仍正常返回，翻页请求数更少
*/

const HOST = 'https://kanju.ai'
// 从前端 JS 提取的签名密钥
const API_SECRET = '557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0'
const DEFAULT_PIC = 'https://pic.rmb.bdstatic.com/bjh/user/default.png'
const TIMEOUT = 8000
// 列表接口 limit 上限就是 50（实测传 100/200 反而只回 20 条），别再往上调
const PAGE_SIZE = 50
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
// resolve 结果缓存：一集一套线路，短时间不变
const TTL_RESOLVE = 5 * 60 * 1000
const TTL_DETAIL = 10 * 60 * 1000

const HEADERS = {
    'User-Agent': UA,
    Accept: 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    Referer: HOST + '/',
    Origin: HOST,
}
const PLAY_HEADERS = {'User-Agent': UA, Referer: HOST + '/'}

// ═══ SHA-256 / HMAC-SHA256 ═══
// 引擎没有这两个，只能自带。正确性由 tools/verify-kanju.mjs 对着 Python 逐值比对。

const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

// 字符串 → UTF-8 字节数组
function utf8Bytes(str) {
    const out = []
    for (const ch of String(str)) {
        const c = ch.codePointAt(0)
        if (c < 0x80) out.push(c)
        else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f))
        else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f))
        else {
            out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f),
                0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f))
        }
    }
    return out
}

const rotr = (x, n) => ((x >>> n) | (x << (32 - n))) >>> 0
const hex8 = (n) => (n >>> 0).toString(16).padStart(8, '0')

function sha256Bytes(bytes) {
    // 末尾补 0x80，补零到长度 ≡ 56 (mod 64)，末尾 8 字节是比特长度的大端
    const bits = bytes.length * 8
    const padded = bytes.slice()
    padded.push(0x80)
    while (padded.length % 64 !== 56) padded.push(0)
    padded.push(0, 0, 0, 0)
    padded.push((bits >>> 24) & 0xff, (bits >>> 16) & 0xff, (bits >>> 8) & 0xff, bits & 0xff)

    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
    const w = new Array(64)
    for (let off = 0; off < padded.length; off += 64) {
        for (let i = 0; i < 16; i++) {
            const j = off + i * 4
            w[i] = ((padded[j] << 24) | (padded[j + 1] << 16) | (padded[j + 2] << 8) | padded[j + 3]) >>> 0
        }
        for (let i = 16; i < 64; i++) {
            const s0 = (rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)) >>> 0
            const s1 = (rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)) >>> 0
            w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
        }
        let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7]
        for (let i = 0; i < 64; i++) {
            const S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0
            const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0
            const S0 = (rotr(a, 2) ^ rotr(a, 13) ^ (rotr(a, 22))) >>> 0
            const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) >>> 0
            h = g; g = f; f = e
            e = (d + t1) >>> 0
            d = c; c = b; b = a
            a = (t1 + t2) >>> 0
        }
        H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0
        H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0
        H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0
        H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0
    }
    return H
}

function hmacSha256(key, message) {
    const B = 64
    let k = utf8Bytes(key)
    // 密钥超长先哈希一次压到 B 字节
    if (k.length > B) {
        k = sha256Bytes(k).flatMap(
            (w) => [(w >>> 24) & 0xff, (w >>> 16) & 0xff, (w >>> 8) & 0xff, w & 0xff])
    }
    while (k.length < B) k.push(0)
    const iKey = k.map((b) => b ^ 0x36)
    const oKey = k.map((b) => b ^ 0x5c)
    const inner = sha256Bytes(iKey.concat(utf8Bytes(message)))
    return sha256Bytes(oKey.concat(inner.flatMap(
        (w) => [(w >>> 24) & 0xff, (w >>> 16) & 0xff, (w >>> 8) & 0xff, w & 0xff]))).map(hex8).join('')
}

function nonce16() {
    // 16 字节随机数 → 32 位十六进制
    let s = ''
    while (s.length < 32) s += Math.floor(Math.random() * 0xffffffff).toString(16)
    return s.slice(0, 32)
}

// 签名串格式：{METHOD}\n{path_with_search}\n{timestamp_ms}\n{nonce}
function signHeaders(method, path, json) {
    const ts = String(Date.now())
    const nonce = nonce16()
    const sig = hmacSha256(API_SECRET, method + '\n' + path + '\n' + ts + '\n' + nonce)
    return {
        ...HEADERS,
        ...(json ? {'Content-Type': 'application/json'} : null),
        'x-ai-movie-timestamp': ts,
        'x-ai-movie-nonce': nonce,
        'x-ai-movie-signature': sig,
    }
}

// ═══ 请求 ═══

async function apiGet(ctx, path) {
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const res = await ctx.lib.net.req(HOST + path, {
                headers: signHeaders('GET', path, false), timeout: TIMEOUT,
            })
            return JSON.parse(res.content) || {}
        } catch (e) {
            ctx.log('看剧AI ' + path.slice(0, 52) + ' 失败: ' + e.message)
        }
    }
    return {}
}

async function apiPost(ctx, path, payload) {
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const res = await ctx.lib.net.req(HOST + path, {
                method: 'POST',
                data: payload,
                headers: signHeaders('POST', path, true), timeout: TIMEOUT,
            })
            return JSON.parse(res.content) || {}
        } catch (e) {
            ctx.log('看剧AI POST ' + path.slice(0, 46) + ' 失败: ' + e.message)
        }
    }
    return {}
}

// ═══ 工具 ═══

function toVod(card) {
    if (!card || !card.id) return null
    const genres = Array.isArray(card.genres) ? card.genres : []
    // 原版只取 remarks；这里把热度/完结状态也并进去，选片时一眼能看出量级
    const rem = [card.remarks, card.heat_value ? '热度' + card.heat_value : '']
        .filter(Boolean).join(' ')
    return {
        vod_id: String(card.id),
        vod_name: card.title || '',
        vod_pic: card.poster_url || DEFAULT_PIC,
        vod_remarks: rem,
        vod_year: card.year ? String(card.year) : '',
        vod_area: card.area || '',
        type_name: genres.slice(0, 3).join(' / '),
    }
}

function toVods(cards) {
    return (cards || []).map(toVod).filter(Boolean)
}

// 分页：优先 total，其次 has_more（与原版同一套逻辑）
function paginate(pag, page, limit, got) {
    const total = (pag && pag.total) || 0
    if (total && limit) return {limit, total, pagecount: Math.ceil(total / limit)}
    if (got && got < limit) return {limit, total: 0, pagecount: page}
    return {limit, total: 0, pagecount: pag && pag.has_more ? page + 1 : page}
}

// 过滤掉明显不是视频的地址（有的线路 url 指向封面图）
function isVideoUrl(url) {
    if (!url) return false
    return !/\.(jpg|jpeg|png|webp|gif|bmp)(\?|$)/i.test(url)
}

// ═══ 钩子 ═══

export default {
    meta: {
        title: '看剧AI',
        host: HOST,
        searchable: 2, filterable: 0, quickSearch: 0,
    },

    rule: {
        headers: HEADERS,
        timeout: TIMEOUT,
        // 静态分类交给声明式 home：站点没有筛选参数，filterable 也关掉
        class_name: '电影&电视剧&动漫&综艺&短剧',
        class_url: 'movie&series&anime&variety&short_drama',
    },

    async homeVod(ctx) {
        const hit = await ctx.cache.get('home')
        if (hit) return {list: hit}
        const data = await apiGet(ctx, '/v1/feed/home')
        const seen = new Set()
        const list = []
        for (const sec of data.sections || []) {
            for (const card of sec.cards || []) {
                const v = toVod(card)
                if (!v || seen.has(v.vod_id)) continue
                seen.add(v.vod_id)
                list.push(v)
            }
        }
        const out = list.slice(0, 50)
        if (out.length) await ctx.cache.set('home', out, 5 * 60 * 1000)
        return {list: out}
    },

    async category(ctx, tid, pg, filter, extend) {
        const page = pg || 1
        const data = await apiGet(ctx, `/v1/browse/catalog?kind=${encodeURIComponent(tid)}` +
            `&page=${page}&limit=${PAGE_SIZE}`)
        const list = toVods(data.cards)
        const p = paginate(data.pagination, page, PAGE_SIZE, list.length)
        // 空页回收：翻过头时页数落回实际末页
        if (!list.length && page > 1) p.pagecount = page - 1
        return {page, pagecount: Math.max(1, p.pagecount), limit: p.limit, total: p.total, list}
    },

    async search(ctx, wd, quick, pg) {
        const kw = String(wd || '').trim()
        const page = pg || 1
        if (!kw) return {page: 1, pagecount: 1, limit: 0, total: 0, list: []}
        const data = await apiGet(ctx, `/v1/browse/catalog?q=${encodeURIComponent(kw)}` +
            `&page=${page}&limit=${PAGE_SIZE}`)
        const list = toVods(data.cards)
        const p = paginate(data.pagination, page, PAGE_SIZE, list.length)
        if (!list.length && page > 1) p.pagecount = page - 1
        return {page, pagecount: Math.max(1, p.pagecount), limit: p.limit, total: p.total, list}
    },

    // 详情：先取第一集的线路表，再给每条线路铺一份同集数的选集
    async detail(ctx, id) {
        const vid = String(id || '')
        if (!vid) return {list: []}
        const key = 'd:' + vid
        const hit = await ctx.cache.get(key)
        if (hit) return {list: [hit]}

        const data = await apiGet(ctx, '/v1/catalog/' + encodeURIComponent(vid))
        if (!data || !data.id) return {list: []}

        // 详情没带 episodes 时走兜底接口
        let eps = data.episodes || []
        if (!eps.length) {
            const more = await apiGet(ctx, '/v1/catalog/' + encodeURIComponent(vid) + '/episodes')
            eps = more.episodes || []
        }

        const tokens = eps.map((e) => e.token).filter(Boolean)
        // 同一集各线路基本一致，用第一集预取一次线路表
        const lines = tokens.length ? await resolveLines(ctx, tokens[0]) : []

        const buildEps = (providerId) => {
            const suffix = providerId ? '@@' + providerId : ''
            const out = []
            for (const ep of eps) {
                if (!ep.token) continue
                let title = ep.title || ''
                if (!title) title = ep.number != null ? '第' + ep.number + '集' : '播放'
                out.push(title + '$' + ep.token + suffix)
            }
            return out
        }

        const playFrom = []
        const playUrl = []
        for (const ln of lines) {
            const ep = buildEps(ln.provider_id)
            if (!ep.length) continue
            playFrom.push(ln.name)
            playUrl.push(ep.join('#'))
        }
        if (!playFrom.length) {
            playFrom.push('默认线路')
            playUrl.push(buildEps('').join('#'))
        }

        const genres = Array.isArray(data.genres) ? data.genres : []
        const vod = {
            vod_id: vid,
            vod_name: data.title || '',
            vod_pic: data.poster_url || DEFAULT_PIC,
            type_name: genres.slice(0, 5).join(' / '),
            vod_year: data.year ? String(data.year) : '',
            vod_area: data.area || '',
            vod_remarks: [
                data.remarks,
                data.episode_count ? '全' + data.episode_count + '集' : '',
                data.heat_value ? '热度' + data.heat_value : '',
            ].filter(Boolean).join(' '),
            vod_actor: (data.actors || []).slice(0, 20).join(' / '),
            vod_director: (data.directors || []).slice(0, 10).join(' / '),
            vod_content: data.description || '',
            vod_play_from: playFrom.join('$$$'),
            vod_play_url: playUrl.join('$$$'),
        }
        await ctx.cache.set(key, vod, TTL_DETAIL)
        return {list: [vod]}
    },

    // 播放：id = "{集名}${token}@@{provider_id}"，token 形如 av_…
    async play(ctx, flag, id, flags) {
        // 集名$之后才是 token；@@ 之后是这条线指定的 provider
        let raw = String(id || '').trim()
        const at = raw.indexOf('$')
        if (at >= 0) raw = raw.slice(at + 1)
        let token = raw
        let want = ''
        const sep = raw.indexOf('@@')
        if (sep >= 0) {
            token = raw.slice(0, sep)
            want = raw.slice(sep + 2)
        }
        token = token.trim()
        if (!token) return {parse: 0, url: ''}

        // 已经是直链就直接给（部分线路的 url 就写进了选集）
        if (/^https?:/i.test(token) && isVideoUrl(token)) {
            return {parse: 0, url: token, header: PLAY_HEADERS}
        }
        if (!/^https?:/i.test(token) && !token) {
            return {parse: 1, url: id, header: PLAY_HEADERS}
        }

        const lines = await resolveLines(ctx, token)
        if (!lines.length) {
            ctx.log('看剧AI 无线路: ' + token.slice(0, 40))
            return {parse: 1, url: webPlayer(token), header: PLAY_HEADERS}
        }

        // 排序：用户指定/flag 命中的线路优先，其余按 url_kind 和权重降序
        const rank = (ln) => {
            if (want && (ln.provider_id === want || ln.play_from === want || ln.name === want)) return 0
            if (flag && ln.name === flag) return 0
            return 1
        }
        const sorted = lines.slice().sort((a, b) => (rank(a) - rank(b)) || (b.weight - a.weight))

        for (const ln of sorted) {
            // 资源类直链：实测可播
            if (ln.kind !== 'resolve_ticket' && isVideoUrl(ln.url)) {
                return {parse: 0, url: ln.url, header: PLAY_HEADERS}
            }
            // 官方线路：用 resolve-line 换真地址
            if (ln.kind === 'resolve_ticket' && ln.ticket) {
                const r = await apiPost(ctx, '/v1/playback/resolve-line', {
                    ticket: ln.ticket,
                    line: ln.sourceId,
                    provider_id: ln.provider_id,
                    play_from: ln.play_from,
                })
                const real = (r.line || {}).url || ''
                // 官方线路实测直连会 403（要各家自己的凭据），换到就交给播放器
                if (real && isVideoUrl(real)) return {parse: 0, url: real, header: PLAY_HEADERS}
            }
        }
        // 全部换不到就回站点 web 播放页嗅探。
        // 实测有一类集（原版/中文版等）只挂 resolve_ticket 官方线路，
        // 换地址一律返回 401「该内容需要登录后播放」——这类集匿名确实放不出来，
        // 只能交给播放器走 web 页。
        ctx.log('看剧AI 所有线路均不可直连（多为需登录的官方线路），回退嗅探: '
            + token.slice(0, 28))
        return {parse: 1, url: webPlayer(token), header: PLAY_HEADERS}
    },
}

// ═══ 线路 ═══

// 取一集的全部线路并整理；结果按 token 缓存 5 分钟
async function resolveLines(ctx, token) {
    if (!token) return []
    const key = 'r:' + token
    const hit = await ctx.cache.get(key)
    if (hit) return hit
    const data = await apiGet(ctx, '/v1/playback/resolve/' + encodeURIComponent(token))
    const seen = new Set()
    const out = []
    for (const o of data.line_options || []) {
        const url = String(o.url || '')
        if (!url) continue
        const pid = o.provider_id || ''
        // 同一 provider 只留一条（接口会按权重给多个变体）
        const dedupe = pid || url
        if (seen.has(dedupe)) continue
        seen.add(dedupe)
        const kind = String(o.url_kind || '')
        out.push({
            name: o.provider_name || o.label || o.display_label || '默认线路',
            provider_id: pid,
            play_from: o.play_from || '',
            sourceId: o.playback_source_id || '',
            kind,
            url: kind === 'resolve_ticket' ? '' : url,
            ticket: kind === 'resolve_ticket' ? url.replace(/^resolve:\/\//, '') : '',
            weight: Number(o.preference_weight) || 0,
        })
    }
    // 资源直链（url_kind 为 m3u8/mp4/hls）排前面：实测它们能播，
    // 官方 resolve_ticket 换出的地址直连会 403，只作兜底。
    // 原版是按 provider_name 里含「资源」二字来猜，属于按文案猜字段。
    out.sort((a, b) => (a.kind === 'resolve_ticket' ? 1 : 0) - (b.kind === 'resolve_ticket' ? 1 : 0))
    if (out.length) await ctx.cache.set(key, out, TTL_RESOLVE)
    return out
}

// 站点 web 播放页（所有解析都失败时交给播放器嗅探）
function webPlayer(token) {
    return HOST + '/yj/' + token.replace(/^YJ-/, '')
}
