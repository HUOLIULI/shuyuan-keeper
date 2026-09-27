var rule = {
    "version": "1",
    "host": "https://www.69shuba.com",
    "header": "",
    "search": {
        "api": "/search.php?keyword={{key}}",
        "rule": {
            "bookList": ".booklist li",
            "name": "h4 a@text",
            "bookUrl": "h4 a@href",
            "author": ".author span@text",
            "kind": ".kind span:first-child@text",
            "lastChapter": ".last span@text",
            "coverUrl": "img@src",
            "intro": ".intro@text"
        },
        "checkKeyWord": "我"
    },
    "home": {
        "bookList": ".newbox .book li",
        "name": "a@text",
        "bookUrl": "a@href",
        "author": ".author span@text",
        "kind": ".kind span:first-child@text",
        "lastChapter": ".last span@text",
        "coverUrl": "img@src",
        "intro": ".intro@text"
    },
    "detail": {
        "author": ".author span@text",
        "kind": ".kind span@text",
        "coverUrl": ".book img@src",
        "intro": ".intro@text",
        "lastChapter": ".last span@text",
        "chapterList": ".chapterlist a"
    },
    "content": {
        "rule": ".txtnav p@text"
    }
};