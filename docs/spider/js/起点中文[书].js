/*
@header({ searchable:1, filterable:1, title:'起点中文', '类型':'小说', lang:'ds' })
*/
var rule = {
    类型: '小说',
    title: '起点中文',
    host: 'https://www.qidian.com',
    searchable: 1,
    searchUrl: 'https://www.qidian.com/search?kw={{key}}&searchtype=article',
    推荐: async function () {
        // 起点首页动态加载，drpyS 通常难以直接抓取静态推荐，返回空
        return setResult([]);
    },
    一级: async function (tid, pg, f, e) {
        // 此函数在 Legado 翻译中通常对应详情页或列表页，但 drpyS 中一级通常指列表。
        // 由于起点主要靠搜索和直接访问详情，这里如果作为通用列表解析（如分类），需要构建 URL。
        // 鉴于输入是搜索规则，主要逻辑在 搜索 和 二级。
        let input = this.input;
        if (!input) return setResult([]);
        let html = (await req(input)).content;
        
        // 解析书籍列表 (基于 Legado bookList: class.res-book-item)
        let list = [];
        let bookItems = cut(html, 'class="res-book-item"', '</div>');
        
        // 由于 cut 简单截取可能不准，使用更稳健的解析逻辑 (假设 drpyS 支持简单的字符串查找或类似 DOM 操作)
        // 注意：drpyS 的 req 返回的是对象，content 是字符串。我们需要模拟提取。
        // 起点搜索页结构较复杂，通常通过 ajax 获取数据。
        // 这里提供基于 HTML 解析的通用骨架，实际应用中可能需要特定的选择器适配 drpyS 的解析能力。
        // 若 drpyS 不支持复杂 DOM 解析，可能需要通过 JS 模板引擎变量或特定方法。
        // 下面尝试使用简单的正则或字符串切割来提取 title 和 url。
        
        let books = html.match(/class="res-book-item[^"]*"[\s\S]*?/g);
        if (books && books.length > 0) {
            for (let i = 0; i < books.length; i++) {
                let bookHtml = books[i];
                // 提取 title
                let titleMatch = bookHtml.match(/<div[^>]*class="res-novel-title[^"]*"[^>]*>([\s\S]*?)<\/div>/);
                let title = titleMatch ? titleMatch[1].replace(/<[^>]+>/g, '').trim() : '';
                
                // 提取 url
                let urlMatch = bookHtml.match(/href="([^"]*?\/book\/\d+)"/);
                let url = urlMatch ? urlMatch[1] : '';
                
                // 提取 cover
                let picMatch = bookHtml.match(/data-src="([^"]*)"/);
                let pic = picMatch ? picMatch[1] : '';
                
                // 提取 desc
                let descMatch = bookHtml.match(/<div[^>]*class="res-summary[^"]*"[^>]*>([\s\S]*?)<\/div>/);
                let desc = descMatch ? descMatch[1].replace(/<[^>]+>/g, '').trim() : '';
                
                if (title && url) {
                    list.push({
                        title: title,
                        url: url,
                        desc: desc,
                        pic_url: pic
                    });
                }
            }
        }
        return setResult(list);
    },
    二级: async function (ids) {
        // ids 是传入的 URL 或 ID
        let url = ids;
        let html = (await req(url)).content;
        
        // 解析详情页信息
        // 1. 书名: meta[@property='og:novel:author'] 实际上是 author, 书名通常是 og:title 或 og:novel:book_name
        let getName = (html.match(/<meta[^>]*property=["']og:novel:book_name["'][^>]*content=["'](.*?)["']/) || [])[1] || '';
        let getAuthor = (html.match(/<meta[^>]*property=["']og:novel:author["'][^>]*content=["'](.*?)["']/) || [])[1] || '';
        let getIntro = (html.match(/<meta[^>]*property=["']og:description["'][^>]*content=["'](.*?)["']/) || [])[1] || '';
        let getPic = (html.match(/<meta[^>]*property=["']og:image["'][^>]*content=["'](.*?)["']/) || [])[1] || '';
        
        // 获取章节列表
        // 起点章节通常动态加载或存储在 JSON 中
        // 尝试从页面中提取章节链接或数据
        // 由于起点反爬较严，章节列表往往需要单独的 AJAX 请求或从特定 div 中提取
        let chapterTitles = [];
        let chapterUrls = [];
        
        // 简单策略：查找所有包含 chapter 的链接或特定 class
        // 这里假设章节列表在 HTML 中可以直接解析，或者通过特定的容器
        let chapterItems = html.match(/<li[^>]*class="[^"]*chapter[^"]*"[^>]*>[\s\S]*?<a[^>]*href="([^"]*)"[^>]*>([^<]*)<\/a>[\s\S]*?<\/li>/g);
        if (chapterItems && chapterItems.length > 0) {
            for (let i = 0; i < chapterItems.length; i++) {
                let item = chapterItems[i];
                let urlMatch = item.match(/href="([^"]*)"/);
                let titleMatch = item.match(/<a[^>]*href="[^"]*"[^>]*>([^<]*)<\/a>/);
                if (urlMatch && titleMatch) {
                    chapterUrls.push(urlMatch[1]);
                    chapterTitles.push(titleMatch[1].trim());
                }
            }
        }
        
        let vodPlayUrl = '';
        if (chapterTitles.length > 0) {
            let parts = [];
            for (let i = 0; i < chapterTitles.length; i++) {
                parts.push(chapterTitles[i] + '$' + chapterUrls[i]);
            }
            vodPlayUrl = parts.join('#');
        }

        return {
            vod_id: url,
            vod_name: getName,
            vod_pic: getPic,
            vod_content: getIntro,
            vod_remarks: getAuthor,
            vod_play_from: '起点中文',
            vod_play_url: vodPlayUrl
        };
    },
    搜索: async function (wd, quick, pg) {
        // wd: 关键词, pg: 页码
        // 构造搜索 URL
        let url = `https://www.qidian.com/search?kw=${encodeURIComponent(wd)}&searchtype=article&page=${pg}`;
        let html = (await req(url)).content;
        
        // 解析搜索结果 (同 一级 解析逻辑，因为搜索页和列表页结构可能类似)
        let list = [];
        let books = html.match(/class="res-book-item[^"]*"[\s\S]*?/g);
        if (books && books.length > 0) {
            for (let i = 0; i < books.length; i++) {
                let bookHtml = books[i];
                let titleMatch = bookHtml.match(/<div[^>]*class="res-novel-title[^"]*"[^>]*>([\s\S]*?)<\/div>/);
                let title = titleMatch ? titleMatch[1].replace(/<[^>]+>/g, '').trim() : '';
                let urlMatch = bookHtml.match(/href="([^"]*?\/book\/\d+)"/);
                let url = urlMatch ? urlMatch[1] : '';
                let picMatch = bookHtml.match(/data-src="([^"]*)"/);
                let pic = picMatch ? picMatch[1] : '';
                let descMatch = bookHtml.match(/<div[^>]*class="res-summary[^"]*"[^>]*>([\s\S]*?)<\/div>/);
                let desc = descMatch ? descMatch[1].replace(/<[^>]+>/g, '').trim() : '';

                if (title && url) {
                    list.push({
                        title: title,
                        url: url,
                        desc: desc,
                        pic_url: pic
                    });
                }
            }
        }
        return setResult(list);
    },
    lazy: async function (flag, id, flags) {
        // 加载章节内容
        let html = (await req(id)).content;
        
        // 解析正文
        // Legado 规则: class.read-content@html
        let content = '';
        let contentMatch = html.match(/<div[^>]*class="[^"]*read-content[^"]*"[\s\S]*?>([\s\S]*?)<\/div>/);
        if (contentMatch) {
            content = contentMatch[1];
            // 清理 HTML 标签，保留文本
            content = content.replace(/<script[\s\S]*?<\/script>/g, '')
                           .replace(/<style[\s\S]*?<\/style>/g, '')
                           .replace(/<[^>]+>/g, '')
                           .trim();
        }
        
        return {
            parse: 0,
            url: 'novel://' + JSON.stringify({
                title: '章节内容',
                content: content
            })
        };
    }
};