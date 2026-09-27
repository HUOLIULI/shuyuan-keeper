/*
@header({ searchable:2, filterable:1, title:'番茄小说2[书]', '类型':'小说', lang:'ds' })
*/
var rule = {
  类型:'小说', title:'番茄小说2[书]', host:'https://api5-normal-sinfonlineb.fqnovel.com', searchable:2,
  searchUrl:'https://fqapi.komr.cn/search?keyword=**',
  推荐: async function(){
    let {input} = this;
    this.input = 'https://api5-normal-sinfonlineb.fqnovel.com/reading/bookapi/multi-detail/v/?aid=1967&iid=1&version_code=999&book_id=';
    return await this.一级();
  },
  一级: async function(){
    let {input, pdfa, pdfh, pd} = this;
    let html = await request(input);
    let d = [];
    let data = JSON.parse(html);
    if (data && data.data && Array.isArray(data.data)) {
      data.data.forEach((item) => {
        let bookData = item.book_data && item.book_data[0];
        if (bookData) {
          d.push({
            title: bookData.title || '',
            pic_url: bookData.thumb_url || '',
            desc: bookData.author || '',
            url: 'https://api5-normal-sinfonlineb.fqnovel.com/reading/bookapi/multi-detail/v/?aid=1967&iid=1&version_code=999&book_id=' + bookData.book_id,
            content: bookData.abstract || '',
          });
        }
      });
    }
    return setResult(d);
  },
  二级: async function(){
    let {input, pdfa, pdfh, pd} = this;
    let html = await request(input);
    let VOD = {};
    let data = JSON.parse(html);
    let bookData = data && data.data && data.data[0] && data.data[0].book_data && data.data[0].book_data[0];
    if (bookData) {
      VOD.vod_name = bookData.title || '';
      VOD.vod_pic = bookData.thumb_url || '';
      VOD.vod_content = bookData.abstract || '';
      VOD.vod_remarks = bookData.category || '';
      VOD.vod_play_from = bookData.title || '书名';
      let chapterUrl = 'https://fanqienovel.com/api/reader/directory/detail?bookId=' + bookData.book_id;
      let chapterHtml = await request(chapterUrl);
      let chapterData = JSON.parse(chapterHtml);
      let chapters = (chapterData && chapterData.data && chapterData.data.volumes && chapterData.data.volumes[0]) ? chapterData.data.volumes[0].items : [];
      let urls = chapters.map((ch) => ch.name + '$' + 'https://fanqienovel.com/reader/full?bookId=' + bookData.book_id + '&chapterId=' + ch.chapter_id);
      VOD.vod_play_url = urls.join('#');
    }
    return VOD;
  },
  搜索: async function(){
    let {KEY, MY_PAGE} = this;
    let url = rule.searchUrl.replace('**', KEY);
    if (MY_PAGE > 1) url = url + '&page=' + MY_PAGE;
    let html = await request(url);
    let d = [];
    let data = JSON.parse(html);
    if (data && Array.isArray(data.data)) {
      data.data.forEach((item) => {
        let bookData = item.book_data && item.book_data[0];
        if (bookData) {
          d.push({
            title: bookData.title || '',
            desc: bookData.author || '',
            img: bookData.thumb_url || '',
            url: 'https://api5-normal-sinfonlineb.fqnovel.com/reading/bookapi/multi-detail/v/?aid=1967&iid=1&version_code=999&book_id=' + bookData.book_id,
          });
        }
      });
    }
    return setResult(d);
  },
  lazy: async function(){
    let {input} = this;
    let html = await request(input);
    let data = JSON.parse(html);
    let content = (data && data.data && data.data.chapter && data.data.chapter.content) ? data.data.chapter.content : '';
    let title = (data && data.data && data.data.chapter && data.data.chapter.title) ? data.data.chapter.title : '章节';
    return {
      parse: 0,
      url: 'novel://' + JSON.stringify({title:title, content:content})
    };
  }
};