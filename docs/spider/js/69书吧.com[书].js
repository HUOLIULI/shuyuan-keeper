/*
@header({ searchable:2, filterable:0, title:'69书吧.com[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'69书吧.com[书]', host:'https://www.69shuba.com', searchable:2,
  searchUrl:'https://www.69shuba.com/search?q=**',
  推荐: async function(){ return [] },
  一级: async function(tid,pg,f,e){
    let d=[], html=(await req(this.input)).content;
    // 解析列表
    let bookList = html.matchAll(/<div class="newbox">\s*<ul[^>]*>(.*?)<\/ul>/g).match(/<li[^>]*>(.*?)<\/li>/g) || [];
    
    for (let item of bookList) {
      if (!item || !item.includes('<a')) continue;
      let aTag = item.match(/<a[^>]*href="([^"]+)"[^>]*>/i);
      let h3Tag = item.match(/<h3[^>]*><a[^>]*>(.*?)<\/a><\/h3>/is) || item.match(/<a[^>]*>(.*?)<\/a>/is);
      let imgTag = item.match(/<img[^>]*src="([^"]+)"|<img[^>]*data-src="([^"]+)"/i);
      let authorTag = item.match(/<label[^>]*class="[^"]*author[^"]*"|<span[^>]*class="[^"]*author[^"]*"/i);
      
      let title = (h3Tag && h3Tag[1]) ? h3Tag[1].replace(/<[^>]+>/g, '').trim() : '';
      let url = aTag ? aTag[1] : '';
      let pic = imgTag ? (imgTag[2] || imgTag[1]) : '';
      let author = '';
      
      if (authorTag) {
        let authorText = item.match(/<label[^>]*author[^>]*>(.*?)<\/label>|<span[^>]*author[^>]*>(.*?)<\/span>/i);
        if (authorText) author = authorText[1] || authorText[2] || '';
      }
      
      let kind = '';
      let kindTags = item.matchAll(/<label[^>]*>(.*?)<\/label>/g);
      let labels = [];
      for (let l of kindTags) labels.push(l[1]);
      kind = labels.slice(1, 3).join(' ');
      
      let desc = '';
      let ellipsis = item.match(/class="ellipsis_2"[^>]*>(.*?)<\/div>/is) || item.match(/class="ellipsis_2"[^>]*>(.*?)<\/p>/is);
      if (ellipsis) desc = ellipsis[1].replace(/<[^>]+>/g, '').trim();
      
      let lastChapter = '';
      let zzxj = item.match(/class="zzxj"[^>]*>\s*<p[^>]*>(.*?)<\/p>/is);
      if (zzxj) lastChapter = zzxj[1].replace(/<[^>]+>/g, '').trim();
      
      if (title && url) {
        d.push({
          title: title,
          url: url,
          desc: desc || kind,
          pic_url: pic,
          author: author,
          kind: kind,
          lastChapter: lastChapter
        });
      }
    }
    return setResult(d);
  },
  二级: async function(ids){
    let html=(await req(ids)).content;
    let vod_name = '';
    let vod_pic = '';
    let vod_content = '';
    let vod_remarks = '';
    let vod_play_url = '';
    
    let h1 = html.match(/<h1[^>]*>(.*?)<\/h1>/is) || html.match(/<title[^>]*>(.*?)<\/title>/is);
    if (h1) vod_name = h1[1].replace(/<[^>]+>/g, '').trim();
    
    let ogImage = html.match(/<meta property="og:image" content="([^"]+)"/i);
    if (ogImage) vod_pic = ogImage[1];
    
    let ogDesc = html.match(/<meta property="og:description" content="([^"]+)"/i);
    if (ogDesc) vod_content = ogDesc[1];
    
    let authorMeta = html.match(/<meta property="og:novel:author" content="([^"]+)"/i);
    let statusMeta = html.match(/<meta property="og:novel:status" content="([^"]+)"/i);
    let categoryMeta = html.match(/<meta property="og:novel:category" content="([^"]+)"/i);
    let updateTime = html.match(/<meta property="og:novel:update_time" content="([^"]+)"/i);
    
    vod_remarks = [
      authorMeta ? authorMeta[1] : '',
      statusMeta ? statusMeta[1] : '',
      categoryMeta ? categoryMeta[1] : ''
    ].filter(x => x).join(' | ');
    
    let chapterRegex = /<div class="txtnav">\s*<ul[^>]*>(.*?)<\/ul>/g;
    let chapters = html.match(/class="txtnav"[^>]*>\s*<ul[^>]*>(.*?)<\/ul>/gs) || [];
    let playUrls = [];
    
    if (chapters.length > 0) {
      let ulContent = chapters[0];
      let liItems = ulContent.match(/<li[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/gs) || [];
      for (let li of liItems) {
        let parts = li.match(/<li[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/is);
        if (parts) {
          let chapTitle = parts[2].replace(/<[^>]+>/g, '').trim();
          let chapUrl = parts[1];
          playUrls.push(chapTitle + '$' + chapUrl);
        }
      }
      vod_play_url = playUrls.join('|');
    }
    
    return {
      vod_id: ids,
      vod_name: vod_name,
      vod_pic: vod_pic,
      vod_content: vod_content,
      vod_remarks: vod_remarks,
      vod_play_from: '正文',
      vod_play_url: vod_play_url
    };
  },
  搜索: async function(wd,quick,pg){
    let d=[], html=(await req(this.input)).content;
    
    let bookList = html.matchAll(/<div class="newbox">\s*<ul[^>]*>(.*?)<\/ul>/g).match(/<li[^>]*>(.*?)<\/li>/g) || [];
    
    for (let item of bookList) {
      if (!item || !item.includes('<a')) continue;
      let aTag = item.match(/<a[^>]*href="([^"]+)"[^>]*>/i);
      let h3Tag = item.match(/<h3[^>]*><a[^>]*>(.*?)<\/a><\/h3>/is) || item.match(/<a[^>]*>(.*?)<\/a>/is);
      let imgTag = item.match(/<img[^>]*src="([^"]+)"|<img[^>]*data-src="([^"]+)"/i);
      
      let title = (h3Tag && h3Tag[1]) ? h3Tag[1].replace(/<[^>]+>/g, '').trim() : '';
      let url = aTag ? aTag[1] : '';
      let pic = imgTag ? (imgTag[2] || imgTag[1]) : '';
      
      let kind = '';
      let kindTags = item.matchAll(/<label[^>]*>(.*?)<\/label>/g);
      let labels = [];
      for (let l of kindTags) labels.push(l[1]);
      kind = labels.slice(1, 3).join(' ');
      
      let desc = '';
      let ellipsis = item.match(/class="ellipsis_2"[^>]*>(.*?)<\/div>/is) || item.match(/class="ellipsis_2"[^>]*>(.*?)<\/p>/is);
      if (ellipsis) desc = ellipsis[1].replace(/<[^>]+>/g, '').trim();
      
      if (title && url) {
        d.push({
          title: title,
          url: url,
          desc: desc || kind,
          pic_url: pic
        });
      }
    }
    return setResult(d);
  },
  lazy: async function(flag,id,flags){
    let html=(await req(id)).content;
    let content = html.match(/<div class="txtnav">(.*?)<\/div>/gs) || [];
    let mainContent = '';
    if (content.length > 0) {
      mainContent = content[0].replace(/<div class="txtnav">/gi, '').replace(/<\/div>/gi, '');
      mainContent = mainContent.replace(/<script[\s\S]*?<\/script>/gi, '');
      mainContent = mainContent.replace(/<!--[\s\S]*?-->/gi, '');
      mainContent = mainContent.replace(/<[^>]+>/g, '');
      mainContent = mainContent.trim();
    }
    
    return {
      parse: 0,
      url: 'novel://' + JSON.stringify({title:'章节', content: mainContent})
    };
  }
};