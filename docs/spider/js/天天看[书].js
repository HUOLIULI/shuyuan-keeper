/*
@header({ searchable:2, filterable:0, title:'天天看', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'天天看', host:'https://cn.ttkan.co/', searchable:2,
  searchUrl:'https://cn.ttkan.co//search?q=**',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[], html=(await req(input)).content;
    // 解析列表，push {title,url,desc,pic_url}
    let items = cutAll(html, 'class=novel_cell', '');
    for(let i=0;i<items.length;i++){
      let item = items[i];
      let title = get(item, 'tag.ul@tag.li.0@tag.a@text');
      let url = get(item, 'tag.ul@tag.li.0@tag.a@href');
      let desc = get(item, 'tag.ul@tag.li.2@text');
      let pic_url = get(item, 'tag.a@tag.amp-img@src');
      d.push({title, url, desc, pic_url});
    }
    return setResult(d);
  },
  二级: async function(ids){
    let html=(await req(ids)).content;
    let vod_name = get(html, 'class.novel_info@tag.div.2@tag.ul@tag.li.0@text');
    let vod_pic = get(html, 'class.novel_info@tag.div.1@tag.a@tag.amp-img@src');
    let vod_content = get(html, 'class.description@text');
    let author = get(html, 'class.novel_info@tag.div.2@tag.ul@tag.li.1@tag.a@text');
    let kind = get(html, 'class.novel_info@tag.div.2@tag.ul@tag.li.2@text').replace(/类别：/g, '');
    let vod_remarks = [author, kind].filter(x=>x).join('|');
    
    // 获取章节列表
    let chapList = cutAll(html, 'class.full_chapters@tag.div.1@tag.a', 'tag.a@href');
    let urlList = [];
    let chapNames = [];
    let anchors = get(html, 'class.full_chapters@tag.div.1@tag.a');
    if (anchors && anchors.length > 0) {
      for (let i = 0; i < anchors.length; i++) {
        let name = get(anchors[i], 'text');
        let href = get(anchors[i], 'href');
        if (name && href) {
          chapNames.push(name);
          urlList.push(href);
        }
      }
    }
    let vod_play_url = urlList.map((u, i) => chapNames[i] + '$' + u).join('#');
    
    return { 
      vod_id:ids, 
      vod_name:vod_name, 
      vod_pic:vod_pic, 
      vod_content:vod_content, 
      vod_remarks:vod_remarks, 
      vod_play_from:'正文', 
      vod_play_url:vod_play_url 
    };
  },
  搜索: async function(wd,quick,pg){
    let d=[], html=(await req(input)).content;
    // 解析搜索结果，push {title,url,desc,pic_url}
    let items = cutAll(html, 'class=novel_cell', '');
    for(let i=0;i<items.length;i++){
      let item = items[i];
      let title = get(item, 'tag.ul@tag.li.0@tag.a@text');
      let url = get(item, 'tag.ul@tag.li.0@tag.a@href');
      let desc = get(item, 'tag.ul@tag.li.2@text');
      let pic_url = get(item, 'tag.a@tag.amp-img@src');
      d.push({title, url, desc, pic_url});
    }
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    let html=(await req(id)).content;
    let content = get(html, 'class.content@tag.p@text');
    // 清理内容
    if (content) {
      content = content.replace(/\(.*?\)/g, '').replace(/交流好书.*/g, '').replace(/关注.*/g, '');
    }
    return {parse:0, url:'novel://'+JSON.stringify({title:'章节',content:content})};
  }
};