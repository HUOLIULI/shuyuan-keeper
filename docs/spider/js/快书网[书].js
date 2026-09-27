/*
@header({ searchable:2, filterable:1, title:'快书网[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'快书网[书]', host:'https://www.kuaishu5.com', searchable:2,
  searchUrl:'https://www.kuaishu5.com/search?q={{key}}&page={{page}}',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[];
    let html = await req(input).content;
    // 根据 Legado bookList: "class.item"
    let items = (new DOMParser().parseFromString(html, 'text/html')).querySelectorAll('div.item');
    items.forEach(item => {
      let title = item.querySelector('h3 a')?.textContent.trim() || '';
      let url = item.querySelector('a')?.getAttribute('href') || '';
      if(url && !url.startsWith('http')) url = rule.host + url;
      let picUrl = item.querySelector('img')?.getAttribute('src') || '';
      let desc = '';
      let author = item.querySelector('p:nth-child(1) a')?.textContent.trim().replace('作者：', '') || '';
      let kind = item.querySelector('p:nth-child(1) span')?.textContent.trim() || '';
      let lastChapter = item.querySelector('li a')?.textContent.trim() || '';
      if(author) desc += `作者: ${author} `;
      if(kind) desc += `类型: ${kind} `;
      if(lastChapter) desc += `最近更新: ${lastChapter}`;
      d.push({title:title, url:url, desc:desc, pic_url:picUrl});
    });
    return setResult(d);
  },
  二级: async function(ids){
    let html = await req(ids).content;
    let doc = new DOMParser().parseFromString(html, 'text/html');
    
    // 详情规则分析
    let name = doc.querySelector('meta[property="og:novel:author"]')?.getAttribute('content') || 
               doc.querySelector('h1')?.textContent.trim() || '未知书名';
    
    // 注意：Legado详情name用的是author meta，这通常是一个常见的元数据错误或特殊设计，
    // 但为了严谨，通常书名在标题或og:title，这里参考Legado规则尽量匹配，
    // 若Legado规则 name 指向 author meta，则按规则来，但通常实际使用中可能误配。
    // 观察详情规则: "name": "//meta[@property='og:novel:author']/@content" -> 这看起来像是把作者当书名？
    // 让我们检查 Legado 搜索规则中的 name: "tag.h3.0@tag.a.0@text"
    // Legado 详情规则中的 name: "//meta[@property='og:novel:author']/@content" 
    // 如果这是笔误，通常书名在 <h1> 或 og:title。
    // 但既然要求翻译Legado规则，如果Legado明确说name取author meta，那我们就取author meta作为显示名称的一部分或者纠正。
    // 通常 Legado 书源里 书名 对应 og:novel:name 或 h1。
    // 让我们假设这里的 Legado 规则是特定的，name取 author meta 可能是不对的，
    // 但为了通用性，我们取 h1 作为书名，如果 h1 为空则取 author。
    // 修正：查看 Legado 详情规则，name 确实指向 og:novel:author。这可能是一个特殊的书源行为。
    // 但在 drpy 中，我们通常希望 name 是书名。
    // 让我们看 intro: og:description, kind: og:novel:category && status
    // lastChapter: og:novel:latest_chapter_name
    // cover: og:image
    
    let realTitle = doc.querySelector('h1')?.textContent.trim() || name; // 优先 h1
    let author = doc.querySelector('meta[property="og:novel:author"]')?.getAttribute('content') || '';
    let intro = doc.querySelector('meta[property="og:description"]')?.getAttribute('content') || '';
    let kind = doc.querySelector('meta[property="og:novel:category"]')?.getAttribute('content') || '';
    let status = doc.querySelector('meta[property="og:novel:status"]')?.getAttribute('content') || '';
    let lastChapter = doc.querySelector('meta[property="og:novel:latest_chapter_name"]')?.getAttribute('content') || '';
    let pic = doc.querySelector('meta[property="og:image"]')?.getAttribute('content') || 
              doc.querySelector('img')?.getAttribute('src') || '';
    
    // 章节列表
    // 二级规则中没有直接给出章节列表选择器，通常需要根据内容页或目录页生成。
    // Legado 详情规则没有 chapterList。
    // 但是 二级 返回需要 vod_play_url，格式为 '章节1$url#章节2$url2'。
    // 通常目录页包含章节链接。假设目录在 class.chapter-list 或类似 div 中的 ul li a。
    // 如果没有明确的 Legado 章节规则，我们需要推断常见的结构或者留空并依赖 lazy 或 一级中的链接。
    // 在 drpyS 中，二级通常解析详情页或目录页。
    // 如果 Legado 没有提供章节列表规则，可能章节链接就在详情页的某个列表里。
    // 常见结构: .chapter-list li a 或 #list dd a
    let chapters = [];
    let chapterLinks = doc.querySelectorAll('.chapter-list li a, #list dd a, ul.chapter li a');
    chapterLinks.forEach(a => {
        let cTitle = a.textContent.trim();
        let cUrl = a.getAttribute('href');
        if(cTitle && cUrl) {
            if(!cUrl.startsWith('http')) cUrl = rule.host + cUrl;
            chapters.push(cTitle + '$' + cUrl);
        }
    });
    
    let vod_play_url = chapters.join('#');
    let vod_content = intro;
    let vod_remarks = author + (kind ? '|' + kind : '') + (status ? '|' + status : '');
    
    return { 
        vod_id: ids, 
        vod_name: realTitle, 
        vod_pic: pic, 
        vod_content: vod_content, 
        vod_remarks: vod_remarks, 
        vod_play_from: '快书网', 
        vod_play_url: vod_play_url 
    };
  },
  搜索: async function(wd,quick,pg){
    let d=[];
    let url = rule.searchUrl.replace('{{key}}', encodeURIComponent(wd)).replace('{{page}}', pg);
    let html = await req(url).content;
    let doc = new DOMParser().parseFromString(html, 'text/html');
    let items = doc.querySelectorAll('.item');
    items.forEach(item => {
      let title = item.querySelector('h3 a')?.textContent.trim() || '';
      let url = item.querySelector('a')?.getAttribute('href') || '';
      if(url && !url.startsWith('http')) url = rule.host + url;
      let picUrl = item.querySelector('img')?.getAttribute('src') || '';
      let desc = '';
      let author = item.querySelector('p:nth-child(1) a')?.textContent.trim().replace('作者：', '') || '';
      let kind = item.querySelector('p:nth-child(1) span')?.textContent.trim() || '';
      let lastChapter = item.querySelector('li a')?.textContent.trim() || '';
      if(author) desc += `作者: ${author} `;
      if(kind) desc += `类型: ${kind} `;
      if(lastChapter) desc += `最近更新: ${lastChapter}`;
      d.push({title:title, url:url, desc:desc, pic_url:picUrl});
    });
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    let html = await req(id).content;
    let doc = new DOMParser().parseFromString(html, 'text/html');
    // 内容规则: "content": "id.booktxt.0@tag.p@text"
    let contentEl = doc.getElementById('booktxt') || doc.querySelector('.booktxt');
    let text = '';
    if(contentEl) {
        let paras = contentEl.querySelectorAll('p');
        let lines = [];
        paras.forEach(p => {
            let t = p.textContent.trim();
            if(t) lines.push(t);
        });
        text = lines.join('\n');
    } else {
        text = doc.body?.textContent.trim() || '';
    }
    // 替换特殊字符
    text = text.replace(/&nbsp;/g, ' ').trim();
    
    return {parse:0, url:'novel://'+JSON.stringify({title:'章节',content:text})};
  }
};