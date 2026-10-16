"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '博看听书(修复版)',
  lang: 'hipy'
})
"""

import sys
import json
import time
import hashlib
import urllib.parse

sys.path.append('..')

try:
    from base.spider import BaseSpider
except ImportError:
    # hipy 环境外(本地测试)的兜底基类
    class BaseSpider:
        def __init__(self, query_params=None, t4_api=None):
            pass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class Spider(BaseSpider):
    """博看听书 - 使用可用API"""
    
    # 站点域名说明:
    #   www.bookan.com.cn   营销官网(无 /voice 接口,请求会404)
    #   api.bookan.com.cn   业务API(分类/详情/章节)
    #   es.bookan.com.cn    搜索API(v3搜索接口专用)
    HOST = 'https://www.bookan.com.cn'
    API_HOST = 'https://api.bookan.com.cn'
    SEARCH_HOST = 'https://es.bookan.com.cn'
    
    # 机构实例ID(栏目配置,分类/搜索共用)
    INSTANCE_ID = '25304'
    
    # 分类
    # 注: 1303-1320 区间除 1317/1322(服务端无数据,恒报500)外均有效
    CLASS_DATA = [
        {'id': '1305', 'name': '少年读物'},
        {'id': '1304', 'name': '儿童文学'},
        {'id': '1320', 'name': '国学经典'},
        {'id': '1306', 'name': '文艺少年'},
        {'id': '1309', 'name': '育儿心经'},
        {'id': '1310', 'name': '心理哲学'},
        {'id': '1307', 'name': '青春励志'},
        {'id': '1312', 'name': '历史小说'},
        {'id': '1303', 'name': '故事会'},
        {'id': '1319', 'name': '相声评书'},
    ]
    
    def __init__(self, query_params=None, t4_api=None):
        super().__init__(query_params, t4_api)
        self.name = '博看听书'
        self.session = None
        if HAS_REQUESTS:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://voicepc.bookan.com.cn/',
            })
    
    def init(self, extend=''):
        pass
    
    def getName(self):
        return self.name
    
    def homeContent(self, filter=False):
        """首页内容"""
        classes = []
        for cls in self.CLASS_DATA:
            classes.append({
                'type_id': cls['id'],
                'type_name': cls['name']
            })
        return {
            'class': classes,
            'filters': {}
        }
    
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        """
        分类内容 - 走业务API(主站www下无此路径,会404)
        """
        try:
            pg = int(pg) if pg else 1
            
            url = f"{self.API_HOST}/voice/book/list?instance_id={self.INSTANCE_ID}&page={pg}&category_id={tid}&num=24"
            
            print(f"[博看] 请求分类: {url}")
            
            if HAS_REQUESTS and self.session:
                response = self.session.get(url, timeout=15)
                
                if response.status_code == 200:
                    # 尝试解析JSON
                    try:
                        data = response.json()
                        print(f"[博看] 解析JSON成功, code: {data.get('code')}")
                    except:
                        # 如果返回HTML，尝试从HTML解析
                        html = response.text
                        print(f"[博看] 返回HTML, 长度: {len(html)}")
                        return self._parse_html_category(html, tid, pg)
                    
                    videos = []
                    if data and data.get('code') == 0:
                        items = data.get('data', {}).get('list', [])
                        for item in items:
                            book_id = item.get('id')
                            name = item.get('name', '')
                            cover = item.get('cover', '')
                            author = item.get('extra', {}).get('author', '') or item.get('press', '')
                            
                            if book_id and name:
                                videos.append({
                                    'vod_id': str(book_id),
                                    'vod_name': name,
                                    'vod_pic': cover or '',
                                    'vod_remarks': author or '',
                                })
                        
                        total = data.get('data', {}).get('total', 0)
                        last_page = data.get('data', {}).get('last_page', 0)
                        # 优先用接口返回的 last_page,取不到再按 total 推算
                        if last_page and last_page > 0:
                            page_count = last_page
                        elif total > 0:
                            page_count = max(1, (total + 23) // 24)
                        else:
                            page_count = 1
                        
                        return {
                            'list': videos,
                            'page': pg,
                            'pagecount': page_count,
                            'total': total or len(videos)
                        }
            
            return {'list': [], 'page': pg, 'pagecount': 1, 'total': 0}
            
        except Exception as e:
            print(f"[博看] categoryContent错误: {e}")
            return {'list': [], 'page': pg, 'pagecount': 1, 'total': 0}
    
    def _parse_html_category(self, html, tid, pg):
        """从HTML解析分类内容(兜底)"""
        videos = []
        
        # 尝试从HTML中提取数据
        import re
        
        # 查找JSON数据
        json_pattern = r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({[^<]+})</script>'
        match = re.search(json_pattern, html)
        if match:
            try:
                data = json.loads(match.group(1))
                # 尝试从数据中提取列表
                for key in ['list', 'data', 'items', 'books']:
                    if key in data:
                        items = data[key]
                        if isinstance(items, list):
                            for item in items:
                                book_id = item.get('id') or item.get('book_id')
                                name = item.get('name') or item.get('title')
                                if book_id and name:
                                    videos.append({
                                        'vod_id': str(book_id),
                                        'vod_name': name,
                                        'vod_pic': item.get('cover') or item.get('pic') or '',
                                        'vod_remarks': item.get('author') or '',
                                    })
                        break
            except:
                pass
        
        return {
            'list': videos,
            'page': pg,
            'pagecount': 1,
            'total': len(videos)
        }
    
    def detailContent(self, ids):
        """详情内容"""
        try:
            if not ids:
                return {'list': []}
            
            book_id = ids[0]
            
            # 章节列表(该接口正常)
            url = f"{self.API_HOST}/voice/album/units?album_id={book_id}&page=1&num=200&order=1"
            
            print(f"[博看] 获取章节: {url}")
            
            play_list = []
            book_name = f"听书_{book_id}"
            book_cover = ''
            book_author = ''
            
            if HAS_REQUESTS and self.session:
                response = self.session.get(url, timeout=15)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get('code') == 0:
                            chapters = data.get('data', {}).get('list', [])
                            for ch in chapters:
                                title = ch.get('title', '')
                                file_url = ch.get('file', '')
                                if file_url:
                                    play_list.append(f"{title or '章节'}${file_url}")
                            
                            print(f"[博看] 获取到 {len(play_list)} 个章节")
                    except:
                        pass
            
            # 书籍信息: 真实接口是 voice/album/info (voice/book/detail 不存在,返回 Illegal Access)
            info_url = f"{self.API_HOST}/voice/album/info?album_id={book_id}"
            if HAS_REQUESTS and self.session:
                response = self.session.get(info_url, timeout=15)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get('code') == 0:
                            info = data.get('data', {})
                            book_name = info.get('name', book_name)
                            book_cover = info.get('cover', '')
                            book_author = info.get('extra', {}).get('author', '') or info.get('press', '')
                    except:
                        pass
            
            vod = {
                'vod_id': str(book_id),
                'vod_name': book_name,
                'vod_pic': book_cover,
                'vod_actor': book_author,
                'vod_play_from': '博看听书',
                'vod_play_url': '#'.join(play_list),
                'vod_remarks': f'共{len(play_list)}集',
            }
            
            return {'list': [vod]}
            
        except Exception as e:
            print(f"[博看] detailContent错误: {e}")
            return {'list': []}
    
    def searchContent(self, key, quick=False, pg=1):
        """搜索 - 走搜索专用域 es.bookan.com.cn 的 v3 接口"""
        try:
            pg = int(pg) if pg else 1
            encoded = urllib.parse.quote(key)
            
            url = f"{self.SEARCH_HOST}/api/v3/voice/book?instanceId={self.INSTANCE_ID}&keyword={encoded}&pageNum={pg}&limitNum=15"
            
            print(f"[博看] 搜索: {url}")
            
            videos = []
            if HAS_REQUESTS and self.session:
                response = self.session.get(url, timeout=15)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get('code') == 0:
                            for item in data.get('data', {}).get('list', []):
                                book_id = item.get('id')
                                name = item.get('name', '')
                                if book_id and name:
                                    videos.append({
                                        'vod_id': str(book_id),
                                        'vod_name': name,
                                        'vod_pic': item.get('cover', ''),
                                        'vod_remarks': item.get('extra', {}).get('author', '') or item.get('press', ''),
                                    })
                    except:
                        pass
            
            return {
                'list': videos,
                'page': pg,
                'pagecount': 1,
                'total': len(videos)
            }
            
        except Exception as e:
            print(f"[博看] searchContent错误: {e}")
            return {'list': []}
    
    def playerContent(self, flag, id, vipFlags=0):
        """播放 - 音频直接放行(CDN支持Range断点)"""
        if id and id.startswith('http'):
            return {
                'url': id,
                'parse': 0,
                'jx': 0,
                'header': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://voicepc.bookan.com.cn/',
                    'Range': 'bytes=0-',
                }
            }
        return {'url': '', 'parse': 0, 'jx': 0}
    
    def localTest(self):
        """本地测试"""
        print("=" * 60)
        print("博看听书测试")
        print("=" * 60)
        
        # 测试API
        print("\n1. 测试API连通性:")
        test_url = f"{self.API_HOST}/voice/book/list?instance_id={self.INSTANCE_ID}&page=1&category_id=1305&num=1"
        if HAS_REQUESTS:
            try:
                resp = self.session.get(test_url, timeout=10)
                print(f"  状态码: {resp.status_code}")
                print(f"  内容类型: {resp.headers.get('Content-Type', '')}")
                if resp.status_code == 200:
                    print(f"  响应预览: {resp.text[:100]}")
            except Exception as e:
                print(f"  错误: {e}")
        
        # 测试分类
        print("\n2. 测试分类:")
        result = self.categoryContent('1305', 1)
        print(f"  获取到 {len(result.get('list', []))} 本书")
        if result.get('list'):
            book = result['list'][0]
            print(f"  示例: {book.get('vod_name')} (ID: {book.get('vod_id')})")
        
        # 测试详情
        if result.get('list'):
            book_id = result['list'][0]['vod_id']
            print(f"\n3. 测试详情: ID={book_id}")
            detail = self.detailContent([book_id])
            if detail.get('list'):
                vod = detail['list'][0]
                print(f"  书名: {vod.get('vod_name')}")
                chapters = vod.get('vod_play_url', '').split('#')
                print(f"  章节数: {len(chapters)}")
                if chapters and chapters[0]:
                    parts = chapters[0].split('$')
                    print(f"  第一章: {parts[0] if parts else '未知'}")
        
        # 测试搜索
        print("\n4. 测试搜索(关键字: 三体):")
        sresult = self.searchContent('三体')
        print(f"  搜索到 {len(sresult.get('list', []))} 条结果")
        if sresult.get('list'):
            sbook = sresult['list'][0]
            print(f"  示例: {sbook.get('vod_name')} (ID: {sbook.get('vod_id')})")
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    spider.localTest()