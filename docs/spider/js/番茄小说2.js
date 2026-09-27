var rule = {
    host: "https://fqapi.komr.cn",
    search: {
        "bookList": "books[*]",
        "name": "book.name",
        "author": "book.author_name",
        "kind": "book.category_name",
        "wordCount": "book.word_count",
        "lastChapter": "book.last_chapter_name",
        "updateTime": "book.update_time"
    },
    categoryContent: {
        "bookList": "books[*]",
        "name": "book.name",
        "author": "book.author_name",
        "kind": "book.category_name",
        "wordCount": "book.word_count",
        "lastChapter": "book.last_chapter_name",
        "updateTime": "book.update_time"
    },
    searchContent: {
        "bookList": "books[*]",
        "name": "book.name",
        "author": "book.author_name",
        "kind": "book.category_name",
        "wordCount": "book.word_count",
        "lastChapter": "book.last_chapter_name",
        "updateTime": "book.update_time"
    },
    detailContent: {
        "init": "data[0]",
        "bookInfo": {
            "name": "book.name",
            "author": "book.author_name",
            "kind": "book.category_name",
            "wordCount": "book.word_count",
            "updateTime": "book.update_time"
        },
        "content": "<js>\nlet cid = java.hexDecodeToString(result);\nlet url = source.host + \"/content?item_id=\" + cid + \"&key=***\";\nif (genreValue === '4') {\n  url += \"&tone_id=0\";\n}\njava.get(url, {method: \"GET\"});\n</js>"
    },
    lazy: "https://fanqienovel.com",
    homeContent: [
        {"title": "榜 单 排 行", "url": "https://api-lf.fanqiesdk.com/api/novel/channel/homepage/rank/rank_list/v2/?aid=13&limit=30&offset={{page -1}}&side_type=10&type=1"},
        {"title": "推荐榜单", "url": "https://api-lf.fanqiesdk.com/api/novel/channel/homepage/rank/rank_list/v2/?aid=13&limit=30&offset={{page -1}}&side_type=10&type=1"},
        {"title": "完结榜单", "url": "https://api-lf.fanqiesdk.com/api/novel/channel/homepage/rank/rank_list/v2/?aid=13&limit=30&offset={{page -1}}&side_type=11&type=1"}
    ]
};