/*
@header({ searchable:2, filterable:1, title:'酷我小说[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'酷我小说[书]', host:'http://appi.kuwo.cn', searchable:2,
  searchUrl:'http://appi.kuwo.cn/search?q=**',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[], html=(await req(this.input)).content;
    // 酷我API通常返回JSON，这里假设req处理了JSON解析或我们需要手动处理
    // 注意：Legado的 $.data 暗示返回的是JSON结构。drpyS的req默认返回响应对象，.content可能是字符串。
    // 如果是JSON API，通常需要 try-catch 或假设框架能解析JSON。
    // 鉴于 drpyS 的常见用法，如果是纯JSON接口，通常直接解析 content 为 JSON 对象。
    
    try {
      let json = JSON.parse(html);
      let list = json.data;
      if (Array.isArray(list)) {
        for (let item of list) {
          let title = item.title || '';
          let url = 'http://appi.kuwo.cn/novels/api/book/' + (item.book_id || '');
          let pic_url = item.cover_url || '';
          let desc = item.intro || '';
          
          // 处理 kind
          let statusText = '';
          if (item.status === 30 || item.status === '30') statusText = '连载';
          else if (item.status === 50 || item.status === '50') statusText = '完结';
          let kind = (item.category_name || '') + ',' + statusText;
          
          let author = item.author_name || '';
          let wordCount = item.all_words || '';
          
          let fullDesc = author + ' | ' + wordCount + '字\n' + kind + '\n' + desc;
          
          d.push({
            title: title,
            url: url,
            desc: fullDesc,
            pic_url: pic_url
          });
        }
      }
    } catch (e) {
      // 如果解析失败，保持空
    }
    return setResult(d);
  },
  二级: async function(ids){
    let html=(await req(ids)).content;
    try {
      let json = JSON.parse(html);
      let data = json.data || json; // 兼容不同的JSON结构
      let title = data.title || '';
      let pic = data.cover_url || '';
      let author = data.author_name || '';
      let intro = data.intro || '';
      
      // 处理 kind
      let statusText = '';
      if (data.status === 30 || data.status === '30') statusText = '连载';
      else if (data.status === 50 || data.status === '50') statusText = '完结';
      let updateTime = data.update_time ? data.update_time.replace(/\s.*:/, '') : '';
      let kind = (data.category_name || '') + ',' + statusText + ',' + updateTime;
      
      let lastChapter = data.new_chapter_name || '';
      // 简单清洗 lastChapter
      lastChapter = lastChapter.replace(/正文卷\..*?/, '').replace(/VIP卷\..*?/, '').replace(/默认卷\..*?/, '').replace(/卷_.*?/, '');
      
      let vod_remarks = author + '\n' + kind;
      
      // Legado 的 kind 替换逻辑比较特殊，这里简化处理
      // result.replace(/30/,"连载").replace(/50/,"完结")
      
      return { 
        vod_id:ids, 
        vod_name:title, 
        vod_pic:pic, 
        vod_content:intro, 
        vod_remarks:vod_remarks, 
        vod_play_from:'正文', 
        vod_play_url:'' // 二级页面通常不直接给章节列表，或者章节在详情API的另一个字段，但根据Legado规则，lastChapter只是信息，没有章节列表字段。
        // 注意：Legado规则中没有提供章节列表的bookUrl解析规则，只提供了详情。
        // 通常小说脚本需要获取章节列表。但提供的Legado规则中没有章节列表API。
        // 假设章节列表需要额外的请求，或者该书源仅展示详情。
        // 根据drpyS惯例，如果无法获取章节列表，vod_play_url可能为空或需要构造。
        // 这里保持为空，因为源规则未提供章节列表获取方式。
      };
    } catch (e) {
      return { vod_id:ids, vod_name:'解析错误', vod_pic:'', vod_content:'', vod_remarks:'', vod_play_from:'正文', vod_play_url:'' };
    }
  },
  搜索: async function(wd,quick,pg){
    let url = 'http://appi.kuwo.cn/search?q=' + encodeURIComponent(wd);
    if (pg > 1) url += '&page=' + pg; // 假设分页参数
    let html=(await req(url)).content;
    let d=[];
    try {
      let json = JSON.parse(html);
      let list = json.data;
      if (Array.isArray(list)) {
        for (let item of list) {
          let title = item.title || '';
          let bookUrl = 'http://appi.kuwo.cn/novels/api/book/' + (item.book_id || '');
          let pic_url = item.cover_url || '';
          let desc = item.intro || '';
          
          let statusText = '';
          if (item.status === 30 || item.status === '30') statusText = '连载';
          else if (item.status === 50 || item.status === '50') statusText = '完结';
          let kind = (item.category_name || '') + ',' + statusText;
          
          let author = item.author_name || '';
          let wordCount = item.all_words || '';
          let fullDesc = author + ' | ' + wordCount + '字\n' + kind + '\n' + desc;
          
          d.push({
            title: title,
            url: bookUrl,
            desc: fullDesc,
            pic_url: pic_url
          });
        }
      }
    } catch (e) {}
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    // 这里处理章节内容加载。由于二级页面没有返回章节列表，
    // drpyS 的 lazy 通常用于加载正文。
    // 如果章节列表是通过 vod_play_url 中的 url 拼接得到的，
    // 而这里没有章节列表，这个函数可能无法正常工作，除非 id 本身就是内容URL。
    // 根据 Legado 规则 content: $.data.content，推测有一个获取章节内容的API。
    // 假设 id 是章节内容获取的URL。
    let html=(await req(id)).content;
    try {
      let json = JSON.parse(html);
      let content = json.data.content || '';
      return {parse:0, url:'novel://'+JSON.stringify({title:'章节',content:content})};
    } catch (e) {
      return {parse:0, url:'novel://'+JSON.stringify({title:'章节',content:html})};
    }
  }
};