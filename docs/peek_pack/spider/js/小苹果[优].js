/*
@header({
  searchable: 2,
  filterable: 1,
  quickSearch: 0,
  title: '小苹果',
  author: 'EylinSir',
  '类型': '影视',
  lang: 'ds'
})
*/


var rule = {
    类型: '影视',
    title: '小苹果',
    author: 'EylinSir',
    host: 'http://su.haotv.site',
    headers: {
        "User-Agent": "okhttp/3.12.11"
    },
    searchUrl: '/api.php/v2.vod/androidsearch10086?page=fypage&wd=**',
    searchable: 2,
    quickSearch: 0,
    filterable: 1,
    timeout: 5000,
    play_parse: true,

    预处理: async function () {
        try {
        let url = this.host + "/api.php/v2.vod/androidtypes";
        let html = await request(url, { headers: this.headers });
        let data = JSON.parse(html);
        let classes = [];
        let filters = {};
        let dy = { "classes": "类型", "areas": "地区", "years": "年份", "sortby": "排序" };
        let demos = ['时间', '人气', '评分'];
        
        data.data.forEach(item => {
            classes.push(item.type_name);
            let typeId = item.type_id.toString();
            item['sortby'] = ['updatetime', 'hits', 'score'];
            let filterArray = [];
            for (let key in dy) {
                if (item[key] && item[key].length > 1) {
                    let values = [];
                    item[key].forEach((val, idx) => {
                        let vStr = val.toString().trim();
                        if (vStr !== "") {
                            values.push({ "n": key === "sortby" ? demos[idx] : vStr, "v": vStr });
                        }
                    });
                    let fKey = key === "areas" ? "areaes" : (key === "years" ? "yeares" : key);
                    filterArray.push({ "key": fKey, "name": dy[key], "value": values });
                }
            }
            filters[typeId] = filterArray;
        });
        
        this.class_name = classes.join('&');
        this.class_url = data.data.map(item => item.type_id).join('&');
        this.filter = filters;
        return [];
        } catch (e) {}
    },

    推荐: async function () {
        let url = this.host + "/api.php/v2.main/androidhome";
        let html = await request(url, { headers: this.headers });
        let data = JSON.parse(html);
        let d = [];
        data.data.list.forEach(i => {
            i.list.forEach(vod => {
                let r = vod.updateInfo ? "更新至" + vod.updateInfo : "";
                d.push({
                    title: vod.name,
                    pic_url: vod.pic,
                    desc: r || (vod.score ? vod.score.toString() : ""),
                    url: vod.id.toString()
                });
            });
        });
        return setResult(d);
    },

    一级: async function (tid, pg, filter, extend) {
        let params = {
            "page": pg,
            "type": tid,
            "area": extend.areaes || '',
            "year": extend.yeares || '',
            "sortby": extend.sortby || '',
            "class": extend.classes || ''
        };
        let query = Object.keys(params).filter(k => params[k] !== '').map(k => k + '=' + encodeURIComponent(params[k])).join('&');
        let url = this.host + '/api.php/v2.vod/androidfilter10086?' + query;
        let html = await request(url, { headers: this.headers });
        let data = JSON.parse(html);
        let d = [];
        data.data.forEach(vod => {
            let r = vod.updateInfo ? "更新至" + vod.updateInfo : "";
            d.push({
                title: vod.name,
                pic_url: vod.pic,
                desc: r || (vod.score ? vod.score.toString() : ""),
                url: vod.id.toString()
            });
        });
        return setResult(d);
    },

    二级: async function (id) {
        let url = this.host + '/api.php/v3.vod/androiddetail2?vod_id=' + id;
        let html = await request(url, { headers: this.headers });
        let data = JSON.parse(html).data;
        // 过滤掉包含“及时雨”的选集
        let filteredUrls = data.urls.filter(i => !i.key.includes("及时雨"));
        let playlist = filteredUrls.map(i => i.key + '$' + i.url).join('#');

        let VOD = {
            vod_name: data.name,
            vod_year: data.year,
            vod_area: data.area,
            vod_lang: data.lang,
            type_name: data.className,
            vod_actor: data.actor,
            vod_director: data.director,
            vod_content: data.content,
            vod_play_from: '小苹果',
            vod_play_url: playlist
        };
        return VOD;
    },

    搜索: async function (wd, quick, pg) {
        let page = pg || '1';
        let url = this.host + '/api.php/v2.vod/androidsearch10086?page=' + page + '&wd=' + encodeURIComponent(wd);
        let html = await request(url, { headers: this.headers });
        let data = JSON.parse(html);
        let d = [];
        data.data.forEach(vod => {
            let r = vod.updateInfo ? "更新至" + vod.updateInfo : "";
            d.push({
                title: vod.name,
                pic_url: vod.pic,
                desc: r || (vod.score ? vod.score.toString() : ""),
                url: vod.id.toString()
            });
        });
        return setResult(d);
    },

    lazy: async function (flag, id) {
        let playUrl = id;
        if (!id.startsWith('http')) {
            playUrl = "http://s.xpgtv.net/m3u8/" + id + ".m3u8";
        }
        const playHeader = {
            'user_id': 'XPGBOX',
            'token2': 'X28tpHOOiCB6T2VddyLaFNV4JZT0+i9Ep88+rWLcRPJXUkVhsTx5q9Be2N8=',
            'version': 'XPGBOX com.phoenix.tv1.6.1',
            'hash': 'bd56',
            'screenx': '2268',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'token': 'Yz0QiCqorD4JdlVqQTe4JJB0JazI2RUjg/9smAGhdtRQM3IXmiRx2PEt4t9EUFS+BiIyBffFa4MPMJkOZQJqe/ApC3U9wm2iDW9jWrFCWwR9mDwuMQU33A+F/VyQOhI/jYxKZFsGOcmWilxqLylX8bLLNnAU5jaTrSPwRO+DfBnIdhckWld4V1k2ZfZ3QKbN',
            'timestamp': '1768109944',
            'screeny': '1116'
        };
        return {
            parse: 0,
            url: playUrl,
            header: playHeader
        };
    }
};
