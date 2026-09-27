var rule = {
    name: "快书网",
    url: "https://www.kuaishu5.com",
    homeContent: {},
    categoryContent: {
        "玄幻": "/xuanhuan/p{{page}}.html",
        "武侠": "/wuxia/p{{page}}.html",
        "都市": "/dushi/p{{page}}.html",
        "历史": "/lishi/p{{page}}.html",
        "科幻": "/kehuan/p{{page}}.html",
        "网游": "/wangyou/p{{page}}.html",
        "女频": "/nvpin/p{{page}}.html",
        "其他": "/qita/p{{page}}.html"
    },
    detailContent: {
        author: "meta[property=og:novel:author]@content",
        coverUrl: "meta[property=og:image]@src",
        intro: "meta[property=og:description]@content",
        kind: "meta[property=og:novel:category]@content"
    },
    searchContent: {
        bookList: "class.item",
        name: "tag.h3.0@tag.a.0@text",
        author: "tag.p.1@tag.a.0@text##作者：",
        coverUrl: "tag.img.0@src",
        bookUrl: "tag.a.0@href",
        kind: "tag.p.0@tag.span[0:1]@text",
        lastChapter: "tag.li.0@tag.a.0@text"
    },
    lazy: "https://www.kuaishu5.com"
};