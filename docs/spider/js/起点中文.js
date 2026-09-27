var rule = {
    "bookSourceName": "起点中文",
    "bookSourceGroup": "drpy",
    "bookSourceType": 0,
    "header": "{\"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\"}",
    "searchUrl": "https://www.qidian.com/search?kw={{key}}",
    "bookList": "<js>\npath='class.res-book-item';\nu=java.get('url');\nc=java.getElement(path);\nif (!c.length && result.includes('var buid')) {\n  cookie.removeCookie(source.getKey());\n  java.toast('在网页加载完成后，手动点击右上角 [√] 即可');\n  java.startBrowserAwait('https://www.qidian.com', 5000);\n}\n</js>",
    "rule": {
        "homeContent": [
            {
                "title": "男生榜单",
                "url": "https://www.qidian.com/rank/all/",
                "style": "{\"layout_flexGrow\":0,\"layout_flexBasisPercent\":1}"
            },
            {
                "title": "月票榜",
                "url": "https://www.qidian.com/rank/yuepiao/page{{page}}/",
                "style": "{\"layout_flexGrow\":0.25,\"layout_flexBasisPercent\":-1}"
            },
            {
                "title": "畅销榜",
                "url": "https://www.qidian.com/rank/hotsales/page{{page}}/",
                "style": "{\"layout_flexGrow\":0.25,\"layout_flexBasisPercent\":-1}"
            },
            {
                "title": "阅读指数榜",
                "url": "https://www.qidian.com/rank/readindex/page{{page}}/",
                "style": "{\"layout_flexGrow\":0.25,\"layout_flexBasisPercent\":-1}"
            },
            {
                "title": "粉丝榜",
                "url": "https://www.qidian.com/rank/newfans/page{{page}}/",
                "style": "{\"layout_flexGrow\":0.25,\"layout_flexBasisPercent\":-1}"
            }
        ],
        "categoryContent": {
            "bookList": "class.res-book-item",
            "name": "class.book-name@text",
            "author": "class.author@class.name.0@text",
            "intro": "class.desc@text",
            "kind": "class.tag@text",
            "coverUrl": "img@src",
            "lastChapter": "class.last-chapter@text",
            "updateTime": "class.time@text",
            "bookUrl": "a@href"
        },
        "detailContent": {
            "name": "//meta[@property='og:title']/@content",
            "author": "//meta[@property='og:novel:author']/@content",
            "intro": "//meta[@property='og:description']/@content",
            "coverUrl": "//meta[@property='og:image']/@content",
            "kind": "//meta[@property='og:novel:category']/@content",
            "lastChapter": "//meta[@property='og:novel:latest_chapter_name']/@content",
            "updateTime": "//meta[@property='og:novel:update_time']/@content",
            "wordCount": "//meta[@property='og:novel:word_count']/@content",
            "chapterList": "class.chapter-list@li",
            "chapterName": "text",
            "chapterUrl": "a@href"
        },
        "searchContent": {
            "bookList": "class.res-book-item",
            "name": "class.book-name@text",
            "author": "class.author@class.name.0@text",
            "intro": "class.desc@text",
            "kind": "class.tag@text",
            "coverUrl": "img@src",
            "bookUrl": "a@href"
        },
        "content": {
            "content": "class.read-content@html"
        }
    }
};