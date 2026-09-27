var rule = {
    "书名": "69书吧",
    "作者": "drpy",
    "url": "https://69shuba.cx",
    "分类url": "全部分类::/blist/class/0/{{page}}.htm\n玄幻魔法::/blist/class/1/{{page}}.htm\n修真武侠::/blist/class/2/{{page}}.htm\n言情小说::/blist/class/3/{{page}}.htm\n历史军事::/blist/class/4/{{page}}.htm\n游戏竞技::/blist/class/5/{{page}}.htm\n科幻空间::/blist/class/6/{{page}}.htm\n悬疑惊悚::/blist/class/7/{{page}}.htm\n同人小说::/blist/class/8/{{page}}.htm\n都市小说::/blist/class/9/{{page}}.htm\n官场职场::/blist/class/10/{{page}}.htm\n穿越时空::/blist/class/11/{{page}}.htm\n青春校园::/blist/class/12/{{page}}.htm\n完本-全部分类::/blist/full/0/{{page}}.htm\n完本-玄幻魔法::/blist/full/1/{{page}}.htm\n完本-修真武侠::/blist/full/2/{{page}}.htm\n完本-言情小说::/blist/full/3/{{page}}.htm\n完本-历史军事::/blist/full/4/{{page}}.htm\n完本-游戏竞技::/blist/full/5/{{page}}.htm\n完本-科幻空间::/blist/full/6/{{page}}.htm\n完本-悬疑惊悚::/blist/full/7/{{page}}.htm\n完本-同人小说::/blist/full/8/{{page}}.htm\n完本-都市小说::/blist/full/9/{{page}}.htm\n完本-官场职场::/blist/full/10/{{page}}.htm\n完本-穿越时空::/blist/full/11/{{page}}.htm\n完本-青春校园::/blist/full/12/{{page}}.htm",
    "搜索url": "https://69shuba.cx/search.php?keyword={{key}}&page={{page}}",
    "搜索规则": {
        "bookList": ".newbox ul li",
        "bookName": "a@text",
        "author": "label@text",
        "bookUrl": "a:eq(1)@href",
        "coverUrl": "img@src@js:if(result.includes('/nc.jpg')){a=java.getString('h3 a:eq(1)@href');if(a){d=a.match(/\\/(\\d+)\\.htm$/)[1];result=`${book.origin}/fengmian/${d.slice(0,-3)}/${d}/${d}s.jpg`;}else{result=java.getString('img@src')}}else{result}",
        "intro": "",
        "lastChapter": "",
        "checkKeyWord": "我有一个"
    },
    "分类规则": {
        "bookList": ".newbox ul li",
        "bookName": "a@text",
        "author": "label@text",
        "bookUrl": "a:eq(1)@href",
        "coverUrl": "img@src@js:if(result.includes('/nc.jpg')){a=java.getString('h3 a:eq(1)@href');if(a){d=a.match(/\\/(\\d+)\\.htm$/)[1];result=`${book.origin}/fengmian/${d.slice(0,-3)}/${d}/${d}s.jpg`;}else{result=java.getString('img@src')}}else{result}",
        "intro": "",
        "lastChapter": ""
    },
    "详情规则": {
        "bookName": "meta[property='og:novel:book_name']@content",
        "author": "meta[property='og:novel:author']@content",
        "intro": "#jianjie-popup .content p",
        "coverUrl": ".bookimg2 img@src@js:if(result.includes('/nc.jpg')){d=baseUrl.match(/\\/(\\d+)\\.htm$/)[1];result=`${book.origin}/fengmian/${d.slice(0,-3)}/${d}/${d}s.jpg`;}else{result}",
        "lastChapter": "",
        "tocUrl": ""
    },
    "目录规则": {
        "chapterList": "li",
        "chapterName": "a@text",
        "chapterUrl": "a@href"
    },
    "内容规则": {
        "content": ".txtnav@html",
        "replaceRegex": "##(^(.+\\n){2}({{book.durChapterTitle}}.*\\n)?)|(\\n.*)+|(\\n.*\\(本章完\\)$)|(\\n最.新.小.说.+)"
    },
    "lazy": "",
    "首页": true,
    "首页内容": true,
    "分类内容": true,
    "搜索内容": true,
    "详情内容": true,
    "目录内容": true,
    "正文内容": true
};