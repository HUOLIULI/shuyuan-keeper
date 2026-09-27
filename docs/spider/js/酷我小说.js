var rule = {
    homeContent: {
        title: "",
        checkKeyWord: ""
    },
    categoryContent: {
        bookList: "$.data",
        name: "$.title",
        author: "$.author_name",
        kind: "{{$.category_name}},{{$.status}}@js:result.replace(/30/,'连载').replace(/50/,'完结')",
        intro: "$.intro",
        coverUrl: "$.cover_url",
        wordCount: "$.all_words",
        bookUrl: "/novels/api/book/{{$.book_id}}"
    },
    detailContent: {
        init: "$.data",
        author: "$.author_name",
        intro: "$.intro##(^|[。！？]+[”」）】]?)##$1<br>",
        kind: "{{$.category_name}},{{$.status}},{{$.update_time}}@js:result.replace(/30/,'连载').replace(/50/,'完结').replace(/\\s..:.*/,'')",
        lastChapter: "$.new_chapter_name##正文卷.",
        coverUrl: "$.cover_url",
        content: "$.data.content"
    },
    searchContent: {
        bookList: "$.data",
        name: "$.title",
        author: "$.author_name",
        kind: "{{$.category_name}},{{$.status}}@js:result.replace(/30/,'连载').replace(/50/,'完结')",
        intro: "$.intro",
        coverUrl: "$.cover_url",
        wordCount: "$.all_words",
        bookUrl: "/novels/api/book/{{$.book_id}}"
    },
    lazy: {
        host: "http://appi.kuwo.cn",
        encode: "UTF-8"
    }
};