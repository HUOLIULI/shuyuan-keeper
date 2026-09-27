/*
@header({ searchable:2, filterable:1, title:'独步小说网[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'独步小说网[书]', host:'https://www.dbxsd.com', searchable:2,
  searchUrl:'https://www.dbxsd.com/search?q=**',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[], html=(await req(this.input)).content;
    // 解析列表，push {title,url,desc,pic_url}
    // 由于 Legado 规则复杂且涉及动态 JS 计算封面，这里提供基础框架，实际需配合 CSS/JS 引擎
    // 注意：drpyS 原生不支持 Legado 的 @css 或复杂 JS 表达式，需简化或重写
    // 假设结构一致，使用基础解析逻辑作为占位，实际需根据网站 DOM 调整
    let rows = html.match(/<tr.*?<\/tr>/gs) || [];
    for(let r of rows){
      if(!r.includes('td') && !r.includes('a')) continue;
      let title = r.match(/<a[^>]*title="([^"]+)"/);
      let url = r.match(/<a[^>]*href="([^"]+)"/);
      if(!title || !url) continue;
      let pic = '';
      try {
        let bookId = url[1].match(/(\d+)\/?$/);
        if(bookId) pic = 'https://www.dbxsd.com/uploads/cover/' + bookId[1] + 's.jpg';
      } catch(e){}
      d.push({
        title: title[1],
        url: url[1],
        desc: '',
        pic_url: pic
      });
    }
    return setResult(d);
  },
  二级: async function(ids){
    let html=(await req(ids)).content;
    let meta = (name) => {
      let m = html.match(new RegExp('<meta\\s+property="' + name + '"\\s+content="([^"]*)"'));
      return m ? m[1] : '';
    };
    
    let name = meta('og:novel:book_name') || meta('og:title') || '';
    let author = meta('og:novel:author');
    let pic = meta('og:image');
    let desc = meta('og:description');
    let kind = meta('og:novel:category');
    let status = meta('og:novel:status');
    let lastChap = meta('og:novel:latest_chapter_name');
    
    // 解析章节列表 (基于 Legado 内容规则中的 downloadUrls: @css:.col-xs-1+a 推测可能涉及章节链接)
    // 通常小说详情页面的章节链接在特定容器内，这里尝试通用匹配 a 标签
    let chapUrls = [];
    let chapRegex = /<a[^>]*href="([^"]*\/\d+\.html)"[^>]*>([^<]*)<\/a>/g;
    let m;
    let seen = new Set();
    while((m = chapRegex.exec(html)) !== null){
      if(seen.has(m[1])) continue;
      seen.add(m[1]);
      // 简单过滤：通常章节链接包含数字.html
      chapUrls.push(m[2] + '#' + m[1]);
    }
    
    return { 
      vod_id: ids, 
      vod_name: name, 
      vod_pic: pic, 
      vod_content: desc, 
      vod_remarks: [author, kind, status, lastChap].filter(Boolean).join(' | '), 
      vod_play_from: '正文', 
      vod_play_url: chapUrls.join('#') 
    };
  },
  搜索: async function(wd,quick,pg){
    let d=[], html=(await req(this.input)).content;
    // 搜索逻辑与一级类似，复用解析
    let rows = html.match(/<tr.*?<\/tr>/gs) || [];
    for(let r of rows){
      if(!r.includes('td') && !r.includes('a')) continue;
      let title = r.match(/<a[^>]*title="([^"]+)"/);
      let url = r.match(/<a[^>]*href="([^"]+)"/);
      if(!title || !url) continue;
      let pic = '';
      try {
        let bookId = url[1].match(/(\d+)\/?$/);
        if(bookId) pic = 'https://www.dbxsd.com/uploads/cover/' + bookId[1] + 's.jpg';
      } catch(e){}
      d.push({
        title: title[1],
        url: url[1],
        desc: '',
        pic_url: pic
      });
    }
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    let html=(await req(id)).content;
    // 解析正文内容 id.cont-body.0
    let contentMatch = html.match(/id="cont-body"[^>]*>([\s\S]*?)<\/div>/);
    let content = contentMatch ? contentMatch[1].replace(/<[^>]+>/g, '').trim() : html;
    return {parse:0, url:'novel://' + JSON.stringify({title:'章节',content:content})};
  }
};