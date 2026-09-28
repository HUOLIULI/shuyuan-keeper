// 4K影视[优] - 羊壳点播源
// 站点: https://www.4kvm.tv
// 基于API: /api/search?q=关键词

var rule = {
    title: '4K影视[优]',
    host: 'https://www.4kvm.tv',
    class_name: '4K影视',
    type: 3,
    searchable: 1,
    quickSearch: 0,
    filterable: 0,
    timeout: 10000,
    batch: false,
    logo: 'https://4kvm.staticimgjs.org/uploads/2026/03/e8bbe2c53e4567.png',
    desc: '4K影视站API源',

    // 首页推荐
    async homeVod() {
        const url = this.host + '/api/search?q=热门&page=1';
        const html = await request(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const data = JSON.parse(html);
        const list = (data.data?.list || []).map(v => ({
            vod_id: String(v.id),
            vod_name: v.title,
            vod_pic: v.cover || v.poster || '',
            vod_remarks: v.year || ''
        }));
        return { class: [], list: list };
    },

    // 分类列表
    async category(t, pg, filter) {
        const url = this.host + '/api/search?q=' + (t || '电影') + '&page=' + (pg || 1);
        const html = await request(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const data = JSON.parse(html);
        const list = (data.data?.list || []).map(v => ({
            vod_id: String(v.id),
            vod_name: v.title,
            vod_pic: v.cover || v.poster || '',
            vod_remarks: v.year || ''
        }));
        return { list: list };
    },

    // 详情
    async detail(ids) {
        // 搜索结果里已经有大部分信息，这里补充
        const url = this.host + '/api/search?q=id:' + ids;
        const html = await request(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const data = JSON.parse(html);
        const item = data.data?.list?.[0] || {};
        return {
            vod_id: String(item.id || ids),
            vod_name: item.title || '未知',
            vod_pic: item.cover || item.poster || '',
            vod_year: item.year || '',
            vod_remarks: item.updated_episodes ? '更新至第' + item.updated_episodes + '集' : '',
            vod_content: item.description || '',
            vod_play_from: '4K影视',
            vod_play_url: '第1集$' + this.host + '/play/' + ids
        };
    },

    // 搜索
    async search(wd, quick) {
        const url = this.host + '/api/search?q=' + encodeURIComponent(wd);
        const html = await request(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const data = JSON.parse(html);
        const list = (data.data?.list || []).map(v => ({
            vod_id: String(v.id),
            vod_name: v.title,
            vod_pic: v.cover || v.poster || '',
            vod_remarks: v.updated_episodes ? '更新至第' + v.updated_episodes + '集' : (v.year || '')
        }));
        return { list: list };
    },

    // 播放解析
    async lazy(flag, id) {
        // 4K影视是API站，播放地址需要进一步解析
        // 这里返回一个占位，实际需要抓播放页
        return {
            parse: 1,
            url: this.host + '/play/' + id
        };
    }
};
