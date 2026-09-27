/*
@header({ searchable:2, filterable:1, title:'番茄小说2[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', 
  title:'番茄小说2[书]', 
  host:'https://fqapi.komr.cn', 
  searchable:2,
  searchUrl:'https://fqapi.komr.cn/search?q=**',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[], html=(await req(input)).content;
    try {
      let json = JSON.parse(html);
      if (json.book_data && json.book_data[0] && json.book_data[0].data) {
        let list = json.book_data[0].data;
        list.forEach(item => {
          let bookId = item.book_id;
          let url = "https://api5-normal-sinfonlineb.fqnovel.com/reading/bookapi/multi-detail/v/?aid=1967&iid=1&version_code=999&book_id=" + bookId;
          d.push({
            title: item.book_name,
            url: url,
            desc: item.abstract || "",
            pic_url: item.thumb_url || ""
          });
        });
      }
    } catch (err) {}
    return setResult(d);
  },
  二级: async function(ids){
    // ids 是从一级列表传下来的完整 URL 或 book_id
    let bookId = ids.match(/book_id=(\d+)/)?.[1] || ids;
    let res = await req("https://fanqienovel.com/api/reader/directory/detail?bookId=" + bookId);
    let html = res.content;
    
    // 构造播放 URL，这里简化处理，实际 drpyS 中 vod_play_url 需要包含章节列表
    // 由于 drpyS 的 '一级' 返回的是书籍列表项，'二级' 通常用于解析详情页
    // 但对于小说源，通常 '二级' 返回的是章节列表结构，或者直接使用 '搜索' 后的跳转
    
    let data = {};
    try {
      let json = JSON.parse(html);
      if (json.data && json.data.dirs) {
        let chapters = json.data.dirs.map(dir => {
          return {
            title: dir.name,
            url: "novel://" + JSON.stringify({ book_id: bookId, chapter_id: dir.id })
          };
        });
        data.vod_play_url = chapters.map(c => c.title + "|" + c.url).join("#");
      }
    } catch (e) {
      data.vod_play_url = "";
    }

    return { 
      vod_id: bookId, 
      vod_name: '未知书名', // 需要在一传参或者解析 book_id 对应的书名，这里简化
      vod_pic: '', 
      vod_content: '', 
      vod_remarks: '', 
      vod_play_from: '正文', 
      vod_play_url: data.vod_play_url 
    };
  },
  搜索: async function(wd,quick,pg){
    let d=[], html=(await req(input)).content;
    try {
      let json = JSON.parse(html);
      if (json.book_data && json.book_data[0] && json.book_data[0].data) {
        let list = json.book_data[0].data;
        list.forEach(item => {
          let bookId = item.book_id;
          let url = "https://api5-normal-sinfonlineb.fqnovel.com/reading/bookapi/multi-detail/v/?aid=1967&iid=1&version_code=999&book_id=" + bookId;
          d.push({
            title: item.book_name,
            url: url,
            desc: item.abstract || "",
            pic_url: item.thumb_url || ""
          });
        });
      }
    } catch (err) {}
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    // id 是 "novel://{...}" 格式
    let parsed = JSON.parse(id.replace('novel://', ''));
    let bookId = parsed.book_id;
    let chapterId = parsed.chapter_id;
    
    // 模拟内容获取，实际中可能需要更多逻辑
    let contentUrl = "https://fanqienovel.com/api/reader/content/detail?item_id=" + chapterId + "&book_id=" + bookId;
    let res = await req(contentUrl);
    let content = "";
    try {
      let json = JSON.parse(res.content);
      if (json.data && json.data.content) {
        content = json.data.content;
      }
    } catch(e) {}
    
    return {parse:0, url:'novel://'+JSON.stringify({title:'章节',content:content})};
  }
};