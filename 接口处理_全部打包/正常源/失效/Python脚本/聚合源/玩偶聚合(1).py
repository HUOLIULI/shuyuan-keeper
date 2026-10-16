# -*- coding: utf-8 -*-
"""Standalone MV Native plugin. No SDK, scheduler, or local runtime files.

Only requested pages are validated; there are no separate domain probes.
A bounded reusable pool owns HTTP jobs; callers never wait for losing requests.
The host owns drive enumeration, labels, opaque refs and playback policy.
"""
from __future__ import annotations

# Union with parent-verified saved domain-monitor snapshot (2026-09-27).
# These are candidates, NOT a claim of current availability; no monitor/DB dependency.
SITE_DOMAINS = {
    'wanou': ['https://www.wogg.net', 'https://wogg.xxooo.cf', 'https://woggpan.888484.xyz', 'https://woggpan.xxooo.cf', 'https://www.wogg.live'],
    'muou': ['https://666.666291.xyz', 'https://123.666291.xyz', 'https://www.muou.site', 'https://www.muou.asia'],
    'labi': ['http://feimo.fun', 'http://tvpanpan.site', 'https://www.mmpanpan.site'],
    'zhizhen': ['http://www.miqk.cc', 'https://www.mihdr.top', 'https://mihdr.top', 'https://zhizhen1.top'],
    'huajuan': ['https://wexwp.cc', 'https://www.wexwp.cc', 'https://www.2xiaopan.top', 'https://www.2xiaopan.one', 'https://www.hjzhencai.top'],
    'huban': ['http://121.205.88.174:16969', 'http://43.248.128.118:16969', 'http://xhban.xyz', 'http://38.76.197.172:16969', 'http://xhban.xyz:20720'],
    'kuaiying': ['http://154.201.83.50:12512', 'http://xsayang.fun:12512', 'http://38.76.197.172:12521', 'http://103.45.162.207:12512'],
    'shandian': ['https://sd.sduc.site', 'http://shandian.blog', 'http://sduc.cloud', 'http://sd.sduc.site'],
    'ouge': ['https://woog.nxog.fun', 'https://woog.nxog.eu.org', 'https://woog.430520.xyz', 'https://ogkk.nxog.eu.org'],
    'duoduo': ['https://tv.214521.xyz', 'https://yydsys.de5.net', 'https://tv.yydsys.cc', 'https://tv.yydsys.top', 'https://pan.yydsys.de'],
}

# 优先级从左到右递减，无需手填数字。
DEFAULT_AGG_CONFIG = {
    'linePriority': ['baidu', 'quark', 'uc', 'a123', 'guangya', 'a139', 'a189', 'a115', 'xunlei', 'ali', 'other'],
    'sitePriority': ['muou', 'wanou', 'huajuan', 'labi', 'duoduo', 'shandian', 'ouge', 'huban', 'kuaiying', 'zhizhen'],
}

# 各站 defaultCategoriesArray 集中配置：一个站一行，列表顺序即显示顺序。
SITE_CATEGORIES = {
    'wanou': [['44', '臻彩'], ['1', '电影'], ['2', '电视剧'], ['3', '动漫'], ['6', '短剧'], ['4', '综艺'], ['5', '音乐'], ['46', '纪录片']],
    'muou': [['1', '电影'], ['2', '电视剧'], ['3', '动漫'], ['4', '纪录片'], ['29', '综艺'], ['25', '115臻选'], ['30', '原盘']],
    'labi': [['29', '臻彩'], ['1', '电影'], ['2', '电视剧'], ['3', '动漫'], ['5', '短剧'], ['4', '综艺'], ['24', '蜡笔4K']],
    'zhizhen': [['26', '臻彩'], ['1', '电影'], ['2', '电视剧'], ['3', '动漫'], ['5', '短剧'], ['4', '综艺'], ['24', '老剧']],
    'huajuan': [['22', '高帧'], ['1', '电影'], ['2', '剧集'], ['3', '动漫'], ['23', 'AI短剧'], ['21', '综艺'], ['24', '4K原盘']],
    'huban': [['6', '臻彩'], ['1', '电影'], ['2', '电视剧'], ['4', '动漫'], ['5', '短剧'], ['3', '综艺'], ['30', '115网盘']],
    'kuaiying': [['5', '臻彩'], ['1', '电影'], ['2', '电视剧'], ['4', '动漫'], ['6', '短剧'], ['3', '综艺'], ['30', '115'], ['35', '123'], ['36', '天移迅']],
    'shandian': [['1', '电影'], ['2', '电视剧'], ['4', '动漫'], ['30', '短剧'], ['3', '综艺']],
    'ouge': [['1', '电影'], ['2', '电视剧'], ['3', '动漫'], ['5', '短剧'], ['4', '综艺'], ['21', '综合']],
    'duoduo': [['1', '电影'], ['2', '剧集'], ['4', '动漫'], ['5', '短剧'], ['3', '综艺'], ['20', '纪录']],
}

# 共用选择器在此维护；各站仅填写名称和差异项。
SITE_DEFAULTS = {'listSelector': '#main .module-item', 'detailPanSelector': '.module-row-info p', 'searchListSelector': '.module-search-item'}
SITES = {
    'wanou': {
        'name': '玩偶',
        'listSelector': '.module-item',
        'categoryUrl': '/vodshow/{categoryId}--------{page}---.html',
        'categoryUrlWithFilters': '/vodshow/{categoryId}-{area}-{by}-{class}-----{page}---{year}.html',
        'searchUrl': '/vodsearch/-------------.html?wd={keyword}&page={page}',
    },
    'muou': {'name': '木偶'},
    'labi': {'name': '蜡笔', 'categoryUrl': '/index.php/vod/show/id/{categoryId}/page/{page}.html'},
    'zhizhen': {'name': '至臻'},
    'huajuan': {'name': '花卷'},
    'huban': {'name': '虎斑'},
    'kuaiying': {'name': '快映'},
    'shandian': {'name': '闪电'},
    'ouge': {'name': '欧哥'},
    'duoduo': {'name': '多多'},
}
SITES = {
    site_id: {"id": site_id, **SITE_DEFAULTS, **site,
              "defaultCategoriesArray": SITE_CATEGORIES[site_id]}
    for site_id, site in SITES.items()
}

# Search-card presentation hints only, not a drive matcher. Unknown hosts stay
# "other"; the host remains authoritative for parsing and playable line identity.
SEARCH_SHARE_LABELS = {
    "pan.baidu.com": "baidu", "yun.baidu.com": "baidu",
    "pan.quark.cn": "quark", "drive.uc.cn": "uc", "fast.uc.cn": "uc",
    "123pan.com": "a123", "123pan.cn": "a123", "123684.com": "a123",
    "123865.com": "a123", "123912.com": "a123",
    "guangyapan.com": "guangya",
    "caiyun.139.com": "a139", "yun.139.com": "a139", "cloud.189.cn": "a189",
    "115.com": "a115", "115cdn.com": "a115", "anxia.com": "a115",
    "pan.xunlei.com": "xunlei", "pan.xunlei.cloud": "xunlei",
    "aliyundrive.com": "ali", "alipan.com": "ali",
}

# 站源级筛选并集：每站一份、每组一行，选项按值去重并保留原显示顺序。
# 已移除字母、排序；地区、语言、时间依次置于末尾，不保留按分类重复的配置。
SITE_FILTERS = {
    'wanou': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '古装', 'v': '古装'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '微电影', 'v': '微电影'}, {'n': '历史', 'v': '历史'}, {'n': '男频', 'v': '男频'}, {'n': '女频', 'v': '女频'}, {'n': '都市', 'v': '都市'}, {'n': '甜宠', 'v': '甜宠'}, {'n': '年代', 'v': '年代'}, {'n': '穿越', 'v': '穿越'}, {'n': '亲情', 'v': '亲情'}, {'n': '萌宝', 'v': '萌宝'}, {'n': '重生', 'v': '重生'}, {'n': '逆袭', 'v': '逆袭'}, {'n': '虐恋', 'v': '虐恋'}, {'n': '鉴宝', 'v': '鉴宝'}, {'n': '复仇', 'v': '复仇'}, {'n': '修仙', 'v': '修仙'}, {'n': '情感', 'v': '情感'}, {'n': '热血', 'v': '热血'}, {'n': '推理', 'v': '推理'}, {'n': '搞笑', 'v': '搞笑'}, {'n': '萝莉', 'v': '萝莉'}, {'n': '校园', 'v': '校园'}, {'n': '机战', 'v': '机战'}, {'n': '运动', 'v': '运动'}, {'n': '少年', 'v': '少年'}, {'n': '少女', 'v': '少女'}, {'n': '社会', 'v': '社会'}, {'n': '原创', 'v': '原创'}, {'n': '亲子', 'v': '亲子'}, {'n': '益智', 'v': '益智'}, {'n': '励志', 'v': '励志'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '美国', 'v': '美国'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '泰国', 'v': '泰国'}, {'n': '德国', 'v': '德国'}, {'n': '印度', 'v': '印度'}, {'n': '意大利', 'v': '意大利'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
    'muou': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '动画', 'v': '动画'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '微电影', 'v': '微电影'}, {'n': '古装', 'v': '古装'}, {'n': '历史', 'v': '历史'}, {'n': '运动', 'v': '运动'}, {'n': '农村', 'v': '农村'}, {'n': '儿童', 'v': '儿童'}, {'n': '网络电影', 'v': '网络电影'}, {'n': '青春偶像', 'v': '青春偶像'}, {'n': '家庭', 'v': '家庭'}, {'n': '乡村', 'v': '乡村'}, {'n': '情景', 'v': '情景'}, {'n': '商战', 'v': '商战'}, {'n': '网剧', 'v': '网剧'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'tid', 'name': '类型', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国产剧', 'v': '13'}, {'n': '欧美剧', 'v': '14'}, {'n': '日韩剧', 'v': '15'}, {'n': '港台剧', 'v': '16'}, {'n': '泰剧', 'v': '23'}, {'n': '其它剧', 'v': '26'}, {'n': '国产', 'v': '20'}, {'n': '日本', 'v': '21'}, {'n': '欧美', 'v': '22'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '美国', 'v': '美国'}, {'n': '香港', 'v': '香港'}, {'n': '韩国', 'v': '韩国'}, {'n': '英国', 'v': '英国'}, {'n': '台湾', 'v': '台湾'}, {'n': '日本', 'v': '日本'}, {'n': '法国', 'v': '法国'}, {'n': '意大利', 'v': '意大利'}, {'n': '德国', 'v': '德国'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '内地', 'v': '内地'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
    'labi': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '古装', 'v': '古装'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '微电影', 'v': '微电影'}, {'n': '历史', 'v': '历史'}, {'n': '运动', 'v': '运动'}, {'n': '农村', 'v': '农村'}, {'n': '儿童', 'v': '儿童'}, {'n': '网络电影', 'v': '网络电影'}, {'n': '偶像', 'v': '偶像'}, {'n': '家庭', 'v': '家庭'}, {'n': '乡村', 'v': '乡村'}, {'n': '情景', 'v': '情景'}, {'n': '商战', 'v': '商战'}, {'n': '网剧', 'v': '网剧'}, {'n': '热血', 'v': '热血'}, {'n': '推理', 'v': '推理'}, {'n': '搞笑', 'v': '搞笑'}, {'n': '冒险', 'v': '冒险'}, {'n': '校园', 'v': '校园'}, {'n': '机战', 'v': '机战'}, {'n': '少年', 'v': '少年'}, {'n': '少女', 'v': '少女'}, {'n': '社会', 'v': '社会'}, {'n': '原创', 'v': '原创'}, {'n': '亲子', 'v': '亲子'}, {'n': '益智', 'v': '益智'}, {'n': '励志', 'v': '励志'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '脱口秀', 'v': '脱口秀'}, {'n': '选秀', 'v': '选秀'}, {'n': '音乐', 'v': '音乐'}, {'n': '情感', 'v': '情感'}, {'n': '竞技', 'v': '竞技'}, {'n': '访谈', 'v': '访谈'}, {'n': '文化', 'v': '文化'}, {'n': '美食', 'v': '美食'}, {'n': '旅行', 'v': '旅行'}, {'n': '观察', 'v': '观察'}, {'n': '晚会', 'v': '晚会'}, {'n': '生活', 'v': '生活'}, {'n': '职业', 'v': '职业'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '美国', 'v': '美国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '英国', 'v': '英国'}, {'n': '法国', 'v': '法国'}, {'n': '德国', 'v': '德国'}, {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'}, {'n': '意大利', 'v': '意大利'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}, {'n': '更早', 'v': '更早'}]},
    ],
    'zhizhen': [
        {'key': 'tid', 'name': '类型', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '高分电影', 'v': '29'}, {'n': '热播剧集', 'v': '27'}, {'n': '高分外剧', 'v': '30'}, {'n': '国漫之光', 'v': '28'}, {'n': '国产剧', 'v': '13'}, {'n': '日韩剧', 'v': '14'}, {'n': '欧美剧', 'v': '15'}, {'n': '港台剧', 'v': '16'}, {'n': '日韩', 'v': '22'}, {'n': '国产', 'v': '20'}, {'n': '欧美', 'v': '21'}]},
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '动画', 'v': '动画'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '微电影', 'v': '微电影'}, {'n': '古装', 'v': '古装'}, {'n': '历史', 'v': '历史'}, {'n': '运动', 'v': '运动'}, {'n': '农村', 'v': '农村'}, {'n': '儿童', 'v': '儿童'}, {'n': '网络电影', 'v': '网络电影'}, {'n': '家庭', 'v': '家庭'}, {'n': '乡村', 'v': '乡村'}, {'n': '情景', 'v': '情景'}, {'n': '商战', 'v': '商战'}, {'n': '网剧', 'v': '网剧'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '脱口秀', 'v': '脱口秀'}, {'n': '选秀', 'v': '选秀'}, {'n': '音乐', 'v': '音乐'}, {'n': '情感', 'v': '情感'}, {'n': '竞技', 'v': '竞技'}, {'n': '访谈', 'v': '访谈'}, {'n': '文化', 'v': '文化'}, {'n': '益智', 'v': '益智'}, {'n': '美食', 'v': '美食'}, {'n': '亲子', 'v': '亲子'}, {'n': '旅行', 'v': '旅行'}, {'n': '观察', 'v': '观察'}, {'n': '晚会', 'v': '晚会'}, {'n': '生活', 'v': '生活'}, {'n': '职业', 'v': '职业'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '大陆', 'v': '大陆'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '香港', 'v': '香港'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '台湾', 'v': '台湾'}, {'n': '美国', 'v': '美国'}, {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '德国', 'v': '德国'}, {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'}, {'n': '意大利', 'v': '意大利'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
    'huajuan': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '动画', 'v': '动画'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '古装', 'v': '古装'}, {'n': '历史', 'v': '历史'}, {'n': '运动', 'v': '运动'}, {'n': '农村', 'v': '农村'}, {'n': '儿童', 'v': '儿童'}, {'n': '青春偶像', 'v': '青春偶像'}, {'n': '家庭', 'v': '家庭'}, {'n': '乡村', 'v': '乡村'}, {'n': '情景', 'v': '情景'}, {'n': '商战', 'v': '商战'}, {'n': '网剧', 'v': '网剧'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '脱口秀', 'v': '脱口秀'}, {'n': '音乐', 'v': '音乐'}, {'n': '情感', 'v': '情感'}, {'n': '竞技', 'v': '竞技'}, {'n': '访谈', 'v': '访谈'}, {'n': '文化', 'v': '文化'}, {'n': '益智', 'v': '益智'}, {'n': '美食', 'v': '美食'}, {'n': '亲子', 'v': '亲子'}, {'n': '旅行', 'v': '旅行'}, {'n': '观察', 'v': '观察'}, {'n': '晚会', 'v': '晚会'}, {'n': '生活', 'v': '生活'}, {'n': '职业', 'v': '职业'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '香港', 'v': '香港'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '台湾', 'v': '台湾'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '美国', 'v': '美国'}, {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '德国', 'v': '德国'}, {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'}, {'n': '意大利', 'v': '意大利'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
    'huban': [
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}, {'n': '2009', 'v': '2009'}, {'n': '2008', 'v': '2008'}, {'n': '2006', 'v': '2006'}, {'n': '2005', 'v': '2005'}, {'n': '2004', 'v': '2004'}, {'n': '2007', 'v': '2007'}]},
    ],
    'kuaiying': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '动作', 'v': '动作'}, {'n': '爱情', 'v': '爱情'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '冒险', 'v': '冒险'}, {'n': '科幻', 'v': '科幻'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '剧情', 'v': '剧情'}, {'n': '动画', 'v': '动画'}, {'n': '武侠', 'v': '武侠'}, {'n': '战争', 'v': '战争'}, {'n': '歌舞', 'v': '歌舞'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '传记', 'v': '传记'}, {'n': '警匪', 'v': '警匪'}, {'n': '历史', 'v': '历史'}, {'n': '运动', 'v': '运动'}, {'n': '伦理', 'v': '伦理'}, {'n': '灾难', 'v': '灾难'}, {'n': '西部', 'v': '西部'}, {'n': '魔幻', 'v': '魔幻'}, {'n': '枪战', 'v': '枪战'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '记录', 'v': '记录'}, {'n': '古装', 'v': '古装'}, {'n': '偶像', 'v': '偶像'}, {'n': '家庭', 'v': '家庭'}, {'n': '言情', 'v': '言情'}, {'n': '军事', 'v': '军事'}, {'n': '农村', 'v': '农村'}, {'n': '都市', 'v': '都市'}, {'n': '神话', 'v': '神话'}, {'n': '少儿', 'v': '少儿'}, {'n': '搞笑', 'v': '搞笑'}, {'n': '谍战', 'v': '谍战'}, {'n': '年代', 'v': '年代'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '访谈', 'v': '访谈'}, {'n': '情感', 'v': '情感'}, {'n': '选秀', 'v': '选秀'}, {'n': '旅游', 'v': '旅游'}, {'n': '美食', 'v': '美食'}, {'n': '口秀', 'v': '口秀'}, {'n': '曲艺', 'v': '曲艺'}, {'n': '游戏', 'v': '游戏'}, {'n': '生活', 'v': '生活'}, {'n': '音乐', 'v': '音乐'}, {'n': '时尚', 'v': '时尚'}, {'n': '益智', 'v': '益智'}, {'n': '职场', 'v': '职场'}, {'n': '纪实', 'v': '纪实'}, {'n': '盛会', 'v': '盛会'}, {'n': '热血', 'v': '热血'}, {'n': '推理', 'v': '推理'}, {'n': '校园', 'v': '校园'}, {'n': '机战', 'v': '机战'}, {'n': '少年', 'v': '少年'}, {'n': '少女', 'v': '少女'}, {'n': '社会', 'v': '社会'}, {'n': '原创', 'v': '原创'}, {'n': '亲子', 'v': '亲子'}, {'n': '励志', 'v': '励志'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'tid', 'name': '类型', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '日本动漫', 'v': '31'}, {'n': '国产动漫', 'v': '32'}, {'n': '动漫电影', 'v': '33'}, {'n': '欧美动漫', 'v': '34'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'}, {'n': '美国', 'v': '美国'}, {'n': '香港', 'v': '香港'}, {'n': '韩国', 'v': '韩国'}, {'n': '英国', 'v': '英国'}, {'n': '台湾', 'v': '台湾'}, {'n': '日本', 'v': '日本'}, {'n': '法国', 'v': '法国'}, {'n': '意大利', 'v': '意大利'}, {'n': '德国', 'v': '德国'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '泰国', 'v': '泰国'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '香港地区', 'v': '香港地区'}, {'n': '欧美', 'v': '欧美'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}, {'n': '2009', 'v': '2009'}, {'n': '2008', 'v': '2008'}, {'n': '2006', 'v': '2006'}, {'n': '2005', 'v': '2005'}, {'n': '2004', 'v': '2004'}, {'n': '2007', 'v': '2007'}]},
    ],
    'shandian': [
        {'key': 'tid', 'name': '类型', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '动作片', 'v': '12'}, {'n': '喜剧片', 'v': '102'}, {'n': '爱情片', 'v': '103'}, {'n': '科幻片', 'v': '104'}, {'n': '剧情片', 'v': '105'}, {'n': '悬疑片', 'v': '106'}, {'n': '惊悚片', 'v': '107'}, {'n': '恐怖片', 'v': '108'}, {'n': '犯罪片', 'v': '109'}, {'n': '武侠片', 'v': '110'}, {'n': '冒险片', 'v': '111'}, {'n': '奇幻片', 'v': '112'}, {'n': '战争片', 'v': '113'}, {'n': '记录片', 'v': '114'}, {'n': '国产剧', 'v': '201'}, {'n': '港台剧', 'v': '202'}, {'n': '欧美韩剧', 'v': '203'}, {'n': '日韩剧', 'v': '204'}, {'n': '海外剧', 'v': '205'}, {'n': '大陆综艺', 'v': '301'}, {'n': '港台综艺', 'v': '302'}, {'n': '欧美综艺', 'v': '303'}, {'n': '日韩综艺', 'v': '304'}, {'n': '动画片', 'v': '401'}, {'n': '国产动漫', 'v': '402'}, {'n': '日韩动漫', 'v': '403'}, {'n': '欧美动漫', 'v': '404'}, {'n': '港台动漫', 'v': '405'}, {'n': '海外动漫', 'v': '406'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '香港', 'v': '香港'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '台湾', 'v': '台湾'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '美国', 'v': '美国'}, {'n': '韩国', 'v': '韩国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '法国', 'v': '法国'}, {'n': '意大利', 'v': '意大利'}, {'n': '德国', 'v': '德国'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '泰国', 'v': '泰国'}, {'n': '新加坡', 'v': '新加坡'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
    'ouge': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '古装', 'v': '古装'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '经典', 'v': '经典'}, {'n': '青春', 'v': '青春'}, {'n': '文艺', 'v': '文艺'}, {'n': '微电影', 'v': '微电影'}, {'n': '历史', 'v': '历史'}, {'n': '情感', 'v': '情感'}, {'n': '热血', 'v': '热血'}, {'n': '推理', 'v': '推理'}, {'n': '搞笑', 'v': '搞笑'}, {'n': '萝莉', 'v': '萝莉'}, {'n': '校园', 'v': '校园'}, {'n': '机战', 'v': '机战'}, {'n': '运动', 'v': '运动'}, {'n': '少年', 'v': '少年'}, {'n': '少女', 'v': '少女'}, {'n': '社会', 'v': '社会'}, {'n': '原创', 'v': '原创'}, {'n': '亲子', 'v': '亲子'}, {'n': '益智', 'v': '益智'}, {'n': '励志', 'v': '励志'}, {'n': '男频', 'v': '男频'}, {'n': '女频', 'v': '女频'}, {'n': '都市', 'v': '都市'}, {'n': '甜宠', 'v': '甜宠'}, {'n': '年代', 'v': '年代'}, {'n': '穿越', 'v': '穿越'}, {'n': '亲情', 'v': '亲情'}, {'n': '萌宝', 'v': '萌宝'}, {'n': '重生', 'v': '重生'}, {'n': '逆袭', 'v': '逆袭'}, {'n': '虐恋', 'v': '虐恋'}, {'n': '鉴宝', 'v': '鉴宝'}, {'n': '复仇', 'v': '复仇'}, {'n': '修仙', 'v': '修仙'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '脱口秀', 'v': '脱口秀'}, {'n': '选秀', 'v': '选秀'}, {'n': '音乐', 'v': '音乐'}, {'n': '竞技', 'v': '竞技'}, {'n': '访谈', 'v': '访谈'}, {'n': '文化', 'v': '文化'}, {'n': '美食', 'v': '美食'}, {'n': '旅行', 'v': '旅行'}, {'n': '观察', 'v': '观察'}, {'n': '晚会', 'v': '晚会'}, {'n': '生活', 'v': '生活'}, {'n': '职业', 'v': '职业'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '大陆', 'v': '大陆'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '香港', 'v': '香港'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '台湾', 'v': '台湾'}, {'n': '美国', 'v': '美国'}, {'n': '西班牙', 'v': '西班牙'}, {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '泰国', 'v': '泰国'}, {'n': '德国', 'v': '德国'}, {'n': '印度', 'v': '印度'}, {'n': '意大利', 'v': '意大利'}, {'n': '加拿大', 'v': '加拿大'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '法语', 'v': '法语'}, {'n': '德语', 'v': '德语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}, {'n': '2009', 'v': '2009'}, {'n': '2008', 'v': '2008'}, {'n': '2007', 'v': '2007'}, {'n': '2006', 'v': '2006'}, {'n': '2005', 'v': '2005'}, {'n': '2004', 'v': '2004'}, {'n': '2003', 'v': '2003'}, {'n': '2002', 'v': '2002'}, {'n': '2001', 'v': '2001'}, {'n': '2000', 'v': '2000'}]},
    ],
    'duoduo': [
        {'key': 'class', 'name': '剧情', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '喜剧', 'v': '喜剧'}, {'n': '爱情', 'v': '爱情'}, {'n': '恐怖', 'v': '恐怖'}, {'n': '动作', 'v': '动作'}, {'n': '科幻', 'v': '科幻'}, {'n': '剧情', 'v': '剧情'}, {'n': '战争', 'v': '战争'}, {'n': '警匪', 'v': '警匪'}, {'n': '犯罪', 'v': '犯罪'}, {'n': '古装', 'v': '古装'}, {'n': '奇幻', 'v': '奇幻'}, {'n': '武侠', 'v': '武侠'}, {'n': '冒险', 'v': '冒险'}, {'n': '枪战', 'v': '枪战'}, {'n': '悬疑', 'v': '悬疑'}, {'n': '惊悚', 'v': '惊悚'}, {'n': '青春', 'v': '青春'}, {'n': '历史', 'v': '历史'}, {'n': '经典', 'v': '经典'}, {'n': '年代', 'v': '年代'}, {'n': '情感', 'v': '情感'}, {'n': '热血', 'v': '热血'}, {'n': '推理', 'v': '推理'}, {'n': '搞笑', 'v': '搞笑'}, {'n': '校园', 'v': '校园'}, {'n': '机战', 'v': '机战'}, {'n': '运动', 'v': '运动'}, {'n': '少年', 'v': '少年'}, {'n': '少女', 'v': '少女'}, {'n': '亲子', 'v': '亲子'}, {'n': '励志', 'v': '励志'}, {'n': '爽文', 'v': '爽文'}, {'n': '都市', 'v': '都市'}, {'n': '穿越', 'v': '穿越'}, {'n': '逆袭', 'v': '逆袭'}, {'n': '虐恋', 'v': '虐恋'}, {'n': '真人秀', 'v': '真人秀'}, {'n': '选秀', 'v': '选秀'}, {'n': '访谈', 'v': '访谈'}, {'n': '播报', 'v': '播报'}, {'n': '旅游', 'v': '旅游'}, {'n': '音乐', 'v': '音乐'}, {'n': '美食', 'v': '美食'}, {'n': '纪录', 'v': '纪录'}, {'n': '传记', 'v': '传记'}, {'n': '自然', 'v': '自然'}, {'n': '科学', 'v': '科学'}]},
        {'key': 'area', 'name': '地区', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '中国大陆', 'v': '中国大陆'}, {'n': '中国香港', 'v': '中国香港'}, {'n': '中国台湾', 'v': '中国台湾'}, {'n': '美国', 'v': '美国'}, {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}, {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'}, {'n': '德国', 'v': '德国'}, {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'}, {'n': '其他', 'v': '其他'}]},
        {'key': 'lang', 'name': '语言', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '国语', 'v': '国语'}, {'n': '英语', 'v': '英语'}, {'n': '粤语', 'v': '粤语'}, {'n': '闽南语', 'v': '闽南语'}, {'n': '韩语', 'v': '韩语'}, {'n': '日语', 'v': '日语'}, {'n': '其它', 'v': '其它'}]},
        {'key': 'year', 'name': '时间', 'init': '', 'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'}, {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}, {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'}, {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'}, {'n': '2018', 'v': '2018'}, {'n': '2017', 'v': '2017'}, {'n': '2016', 'v': '2016'}, {'n': '2015', 'v': '2015'}, {'n': '2014', 'v': '2014'}, {'n': '2013', 'v': '2013'}, {'n': '2012', 'v': '2012'}, {'n': '2011', 'v': '2011'}, {'n': '2010', 'v': '2010'}]},
    ],
}

# Implementation uses only ordinary HTTP and the public MV host/URL contracts.
import asyncio
import base64
import ipaddress
import hashlib
import json
import re
import socket
import threading
import time
import zlib
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from difflib import SequenceMatcher
from queue import Empty, Queue
from copy import deepcopy
from urllib.parse import quote, urljoin, urlsplit, urlunsplit, urlencode

import httpx
from bs4 import BeautifulSoup
from media_vault.plugins.python_runtime.resolution import (
    is_safe_resolved_http_address,
    validate_public_http_url,
)

MV_PLUGIN = {
    "id": "wanou", "name": "玩偶聚合", "version": "1.1.5",
    "profile": "python-spider-v1",
    "capabilities": {
        "content": True, "network": True, "host_bridge": True, "drive_bridge": True,
    },
    "concurrency": {"content_max_inflight": 1},
    "timeouts": {"content_ms": 120000},
    "content_sources": [{
        "id": "main", "name": "玩偶聚合", "searchable": True,
        "quick_search": False, "filterable": True, "changeable": True,
    }],
    "compatibility": {"upstream": "mv-native-v1"},
    "config_schema": {"type": "object", "properties": {
        "settings": {
            "type": "string", "default": "{}",
            "description": "JSON: domains {site:[public origins]}, sitePriority, linePriority",
        },
    }},
}

GET_BUDGET = 15.0
SEARCH_BUDGET = 4.0
SEARCH_DETAIL_BUDGET = 3.0
# Plugin execution only: host queue/startup and player transport are not included.
SEARCH_TOTAL_BUDGET = 10.0
MAX_DOMAINS = 16
MAX_CANDIDATES = MAX_DOMAINS * len(SITES)
MAX_BODY = 2 * 1024 * 1024
MAX_ITEMS = 200
LEGACY_MAX_ID_MEMBERS = 12
MAX_ID_PAYLOAD = 512 * 1024
MAX_DETAIL_BYTES = 6 * 1024 * 1024  # Leave room for the worker's 8 MiB RPC envelope.
MAX_SHARES = 24  # Per site; successful lines additionally obey quark=3, others=2.
MAX_PLAY_SOURCES = 32  # Native Content ABI ceiling, applied after priority sorting.
CHALLENGES = ("just a moment", "cf-browser-verification", "cf-chl-", "captcha challenge")


class _BoundedRequestExecutor:
    """One in-flight job per origin, at most MAX_CANDIDATES jobs/threads.

    A batch gives each configured origin its own worker opportunity; no first-32
    DNS head-of-line blocking. Later calls cannot multiply a stuck origin's jobs.
    Content uses a fixed pool. No retry/timer/scheduler or domain probes.
    Cancelled queue entries retain their origin slot until actually dequeued.
    """
    def __init__(self, phase):
        self.lock = threading.Lock()
        self.origins = set()
        self.pool = ThreadPoolExecutor(max_workers=MAX_CANDIDATES,
                                       thread_name_prefix="wanou-" + phase)

    def submit(self, origin, fn, *args):
        with self.lock:
            if origin in self.origins:
                return None, "WANOU_ORIGIN_BUSY"
            if len(self.origins) >= MAX_CANDIDATES:
                return None, "WANOU_POOL_SATURATED"
            self.origins.add(origin)
        result = Future()

        def release(_=None):
            with self.lock:
                self.origins.discard(origin)

        def invoke():
            if result.set_running_or_notify_cancel():
                try:
                    result.set_result(fn(*args))
                except BaseException as exc:
                    result.set_exception(exc)

        try:
            # Do not expose the underlying queue future: cancelling it would
            # free a slot before its queued WorkItem is actually removed.
            task = self.pool.submit(invoke)
        except Exception:
            release()
            raise
        task.add_done_callback(release)
        return result, None


_CONTENT_EXECUTOR = _BoundedRequestExecutor("content")
_DNS_EXECUTOR = _BoundedRequestExecutor("dns")


class _RequestCancel(threading.Event):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.readers = set()
        self.bound = False

    def register(self, loop, task):
        with self.lock:
            self.readers.add((loop, task))
            if self.is_set():
                task.cancel()

    def unregister(self, loop, task):
        with self.lock:
            self.readers.discard((loop, task))

    def set(self):
        with self.lock:
            if self.is_set():
                return
            super().set()
            for loop, task in self.readers:
                if not task.done():
                    loop.call_soon_threadsafe(task.cancel)


def _request_origin(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), parsed.hostname.lower().rstrip("."),
            parsed.port or (443 if parsed.scheme.lower() == "https" else 80))


def _content_href(value):
    if (not isinstance(value, str) or not value or len(value.encode()) > 2048
            or any(ord(c) < 33 for c in value) or "\\" in value):
        raise ValueError("invalid detail href")
    parsed = urlsplit(value)
    if parsed.scheme:
        return _public_url(value)
    if parsed.netloc or value.startswith("//") or ":" in parsed.path:
        raise ValueError("invalid relative detail href")
    return value


def _public_url(url, *, dns=False):
    """Shared MV DNS/FakeIP policy, with explicit credentials/port syntax checks."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError("invalid public URL")
    p = urlsplit(url)
    host = (p.hostname or "").lower().rstrip(".")
    if (p.username is not None or p.password is not None or not host
            or host.endswith((".internal", ".lan", ".intra")) or "%" in host
            or "\\" in url or (p.port is not None and not 1 <= p.port <= 65535)):
        raise ValueError("invalid public URL")
    return validate_public_http_url(url, require_dns=dns)


def _origin(url):
    p = urlsplit(_public_url(url))
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _resolve_addresses(url):
    p = urlsplit(_public_url(url))
    try:
        addresses = (str(ipaddress.ip_address(p.hostname)),)
    except ValueError:
        addresses = tuple(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(
            p.hostname, p.port or (443 if p.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )))
    if not addresses or any(not is_safe_resolved_http_address(a) for a in addresses):
        raise ValueError("unsafe DNS result")
    return addresses


async def _safe_get_async(url, deadline, cancel):
    loop, task = asyncio.get_running_loop(), asyncio.current_task()
    bound_origin = _request_origin(url) if cancel.bound or re.search(
        r"/(?:index\.php/vod/detail|voddetail|vod/detail)/", urlsplit(url).path
    ) else None
    cancel.register(loop, task)
    try:
        async with asyncio.timeout(max(0, deadline - time.monotonic())):
            async with httpx.AsyncClient(
                verify=True, trust_env=False, follow_redirects=False,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as client:
                for _ in range(5):
                    if cancel.is_set():
                        raise asyncio.CancelledError()
                    url = _public_url(url)
                    future, rejected = _DNS_EXECUTOR.submit(_request_origin(url), _resolve_addresses, url)
                    if future is None:
                        raise ValueError(rejected)
                    wrapped = asyncio.wrap_future(future)
                    wrapped.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
                    addresses = await asyncio.shield(wrapped)
                    parsed = urlsplit(url)
                    remaining = max(0.001, deadline - time.monotonic())
                    response = None
                    try:
                        for index, address in enumerate(addresses):
                            client.cookies.clear()
                            connecting = []

                            async def trace(event, info):
                                if event == "connection.connect_tcp.complete":
                                    connecting.append(info["return_value"])

                            request = client.build_request(
                                "GET", httpx.URL(url).copy_with(host=address),
                                headers={"Host": parsed.netloc, "User-Agent": "Mozilla/5.0",
                                         "Accept": "text/html,application/xhtml+xml",
                                         "Accept-Encoding": "identity"},
                                extensions={"sni_hostname": parsed.hostname, "trace": trace},
                                timeout=httpx.Timeout(remaining, connect=min(5.0, remaining)),
                            )
                            try:
                                response = await client.send(request, stream=True)
                                break
                            except BaseException as error:
                                for stream in connecting:
                                    await stream.aclose()
                                if not isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)) or index == len(addresses) - 1:
                                    raise
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                raise ValueError("redirect without location")
                            target = _public_url(urljoin(url, location))
                            if bound_origin is not None and _request_origin(target) != bound_origin:
                                raise ValueError("detail redirect changed bound origin")
                            url = target
                            continue
                        if response.status_code != 200:
                            return response.status_code, "", url
                        if int(response.headers.get("Content-Length", "0")) > MAX_BODY:
                            raise ValueError("page too large")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_BODY:
                                raise ValueError("page too large")
                            body.extend(chunk)
                        return 200, body.decode(response.encoding or "utf-8", errors="replace"), url
                    finally:
                        if response is not None:
                            await response.aclose()
                raise ValueError("too many redirects")
    finally:
        cancel.unregister(loop, task)


def safe_get(url, deadline, cancel):
    try:
        return asyncio.run(_safe_get_async(url, deadline, cancel))
    except asyncio.CancelledError:
        raise TimeoutError("request cancelled") from None


def _valid_page(status, body):
    return status == 200 and bool(body.strip()) and not any(x in body.lower() for x in CHALLENGES)


def _pack(members):
    # Self-contained across worker restarts; the host still seals the local ID.
    _validate_members(members)
    raw = json.dumps(members, ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > MAX_ID_PAYLOAD:
        raise ValueError("content reference payload too large")
    value = "wn1_" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
    if len(members) > 1 or len(value) > 1024:
        value = "wn2_" + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")
    # This is the existing host ABI boundary, not a resource/member quota.
    if len(value.encode("utf-8")) > 1024:
        raise ValueError("content reference too large")
    return value


def _unpack(value):
    if (not isinstance(value, str) or value[:4] not in ("wn1_", "wn2_")
            or len(value) > 1024):
        raise ValueError("invalid content reference")
    raw = value[4:]
    raw = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
    if value.startswith("wn2_"):
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(raw, MAX_ID_PAYLOAD + 1)
        except zlib.error as exc:
            raise ValueError("invalid compressed content reference") from exc
        if len(raw) > MAX_ID_PAYLOAD or not decoder.eof or decoder.unused_data:
            raise ValueError("invalid compressed content reference")
    members = json.loads(raw)
    _validate_members(members)
    if value.startswith("wn1_") and len(members) > LEGACY_MAX_ID_MEMBERS:
        raise ValueError("invalid legacy content reference")
    return members


def _validate_members(members):
    if not isinstance(members, list) or not members:
        raise ValueError("invalid content reference")
    for member in members:
        if (not isinstance(member, list) or len(member) != 2
                or not isinstance(member[0], str) or member[0] not in SITES):
            raise ValueError("invalid content reference")
        _content_href(member[1])
        if not urlsplit(member[1]).scheme:
            raise ValueError("detail entry has no bound origin; reload the list")


def _text(node, selector=None):
    value = node.select_one(selector) if selector else node
    return value.get_text(" ", strip=True) if value else ""


def _similarity(left, right):
    left, right = left.lower().strip(), right.lower().strip()
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _document(kind, items=(), page=1, more=False, categories=(), filters=()):
    values = list(items)[:MAX_ITEMS]
    return {
        "schema_version": "mv.python-content.v1", "kind": kind,
        "categories": list(categories), "filters": dict(filters or {}), "items": values,
        "pagination": {"page": page, "page_count": page + int(more),
                       "limit": MAX_ITEMS, "total": len(values)},
        "metadata": {},
    }


class WanouPlugin:
    def __init__(self, context=None):
        context = context or {}
        self.host = context.get("host")
        self.lock = threading.RLock()
        self._request_diagnostics = []
        self._content_succeeded = False
        self._search_deadline = None
        config = dict(context.get("config") or {})
        settings = config.get("settings", "{}")
        if isinstance(settings, str):
            if len(settings) > 32768:
                raise ValueError("settings too large")
            settings = json.loads(settings)
        if not isinstance(settings, dict):
            raise ValueError("settings must be an object")
        self.config = deepcopy(DEFAULT_AGG_CONFIG)
        for key in ("linePriority", "sitePriority"):
            self.config[key] = {
                name: index for index, name in enumerate(self.config[key], start=1)
            }
        for key in self.config:
            if key in settings:
                if isinstance(self.config[key], dict):
                    self.config[key].update(settings[key])
                else:
                    self.config[key] = settings[key]
        self.domains = deepcopy(SITE_DOMAINS)
        manual = settings.get("domains", {})
        for sid, domains in manual.items():
            if sid not in SITES or not isinstance(domains, list) or not 1 <= len(domains) <= MAX_DOMAINS:
                raise ValueError("invalid site domains")
            self.domains[sid] = list(dict.fromkeys(_origin(x) for x in domains))
        self.categories = {sid: deepcopy(s["defaultCategoriesArray"]) for sid, s in SITES.items()}
        if any(not 1 <= len(ds) <= MAX_DOMAINS for ds in self.domains.values()):
            raise ValueError("site candidate count must be between 1 and 16")

    def _valid_result(self, sid, path, status, body, final_url):
        if not _valid_page(status, body):
            return False
        document = BeautifulSoup(body, "html.parser")
        title = document.title.get_text(" ", strip=True) if document.title else ""
        if sid == "labi" and title.casefold() == "your domain is expired":
            return False
        if sid == "huban" and title == "警告" and "该网站疑似诈骗网站" in document.get_text():
            return False
        if re.search(r"/(?:index\.php/vod/detail|voddetail|vod/detail)/", path):
            return bool(self._parse_detail(document, final_url, "") and document.select_one(
                ".module-info, .module-info-content, .module-row-info, .video-info, .vod_content"
            ))
        search = "search" in urlsplit(path).path
        if self._parse_list(sid, body, final_url, search=search)[0]:
            return True
        # 空列表必须仍是站点列表容器，不能让普通200错误页赢得竞速。
        container = document.select_one(
            "#main .module-items, #main .module-poster-items-base, "
            "#main .module-search-list, #main .module-list, #main .module-list-items"
        )
        if container is None or container.select_one(
            ".module-item, .module-search-item, a.module-poster-item, .vod-item"
        ):
            return False
        if not container.get_text(strip=True) and not container.select_one("a[href], img"):
            return True
        marker = container.select_one(".no-data, .empty, .module-none, .search-empty")
        return bool(marker and re.search(r"暂无|没有|未找到|无相关|no results|not found",
                                        marker.get_text(" ", strip=True), re.I))

    def _run_requests(self, requests, budget, contexts=None):
        if len(requests) > MAX_CANDIDATES:
            raise ValueError("request batch exceeds the configured candidate bound")
        deadline = time.monotonic() + budget
        executor = _CONTENT_EXECUTOR
        winners, cancels, origins = {}, {}, {}
        for key, url in requests:
            _public_url(url)
            cancel = cancels.setdefault(key, _RequestCancel())
            cancel.bound = bool(urlsplit((contexts or {}).get(key, (key, url))[1]).scheme)
            origins.setdefault(_request_origin(url), []).append((key, url, cancel))
        # Each request emits at most one result and each origin one completion.
        results = Queue(maxsize=max(1, len(requests) + len(origins)))
        tasks, pending = [], set()

        def diagnose(key, url, code):
            entry = {"phase": "content", "request": str(key), "origin": _origin(url), "code": code}
            if entry not in self._request_diagnostics:
                self._request_diagnostics.append(entry)

        def work(entries):
            try:
                for key, url, cancel in entries:
                    if cancel.is_set() or time.monotonic() >= deadline:
                        continue
                    try:
                        status, body, final_url = safe_get(url, deadline, cancel)
                        _public_url(final_url)
                        sid, path = (contexts or {}).get(key, (key, url))
                        ok = self._valid_result(sid, path, status, body, final_url)
                        code = None if ok else "WANOU_HTTP_UNAVAILABLE"
                    except Exception:
                        status, body, final_url, ok, code = None, "", url, None, "WANOU_REQUEST_FAILED"
                    results.put_nowait((key, url, status, body, final_url, ok, code))
            finally:
                results.put_nowait(None)

        for entries in origins.values():
            key, url, _ = entries[0]
            if time.monotonic() >= deadline:
                task, rejection = None, "WANOU_REQUEST_TIMEOUT"
            else:
                task, rejection = executor.submit(_request_origin(url), work, entries)
            if task is None:
                for key, url, _ in entries:
                    diagnose(key, url, rejection)
            else:
                tasks.append(task)
                pending.update((key, url) for key, url, _ in entries)
        keys, remaining = {key for key, _ in requests}, len(tasks)
        try:
            while remaining and len(winners) < len(keys):
                wait = deadline - time.monotonic()
                if wait <= 0:
                    break
                try:
                    result = results.get(timeout=wait)
                except Empty:
                    break
                if result is None:
                    remaining -= 1
                    continue
                key, url, status, body, final_url, ok, code = result
                pending.discard((key, url))
                if key in winners:
                    continue
                if ok:
                    winners[key] = (body, final_url)
                    cancels[key].set()
                elif code:
                    diagnose(key, url, code)
        finally:
            for cancel in cancels.values():
                cancel.set()
            for task in tasks:
                task.cancel()
            # 仅等待已发出取消的请求清理；不等待未取消的慢响应或底层DNS。
            cleanup_deadline = min(deadline, time.monotonic() + 0.5)
            for task in tasks:
                try:
                    task.result(timeout=max(0, cleanup_deadline - time.monotonic()))
                except Exception:
                    pass
        for key, url in pending:
            if key not in winners:
                diagnose(key, url, "WANOU_REQUEST_TIMEOUT")
        if winners:
            self._content_succeeded = True
        return winners

    def _document(self, *args, **kwargs):
        result = _document(*args, **kwargs)
        if self._request_diagnostics:
            result["metadata"]["request_diagnostics"] = deepcopy(self._request_diagnostics)
            result["metadata"]["request_status"] = "partial" if self._content_succeeded else "unavailable"
        return result

    def _fetch_entries(self, entries, budget):
        if self._search_deadline is not None:
            budget = min(budget, max(0, self._search_deadline - time.monotonic()))
            if budget <= 0:
                return {}
        deadline = time.monotonic() + budget
        requests = []
        contexts = {}
        for key, sid, path in entries:
            contexts[key] = (sid, path)
            _content_href(path)
            # Frozen 4.9: absolute URLs are sent exactly once, without rewriting.
            urls = ([path] if urlsplit(path).scheme else
                    [urljoin(base + "/", path) for base in self.domains[sid]])
            requests.extend((key, url) for url in dict.fromkeys(urls))
        # Many same-title entries can exceed one candidate batch. All batches
        # share one deadline; no per-entry/per-batch timeout multiplication.
        pages = {}
        for start in range(0, len(requests), MAX_CANDIDATES):
            if self._search_expired():
                break
            batch = [(key, url) for key, url in requests[start:start + MAX_CANDIDATES]
                     if key not in pages]
            if batch:
                pages.update(self._run_requests(batch, max(0, deadline - time.monotonic()), contexts))
        return pages

    def _fetch_many(self, paths, budget=None):
        return self._fetch_entries([(sid, sid, path) for sid, path in paths.items()],
                                   GET_BUDGET if budget is None else budget)

    def _parse_list(self, sid, body, base, search=False):
        soup = BeautifulSoup(body, "html.parser")
        if sid == "huajuan":
            selectors = ([".module-search-item", "a.module-poster-item", ".search-result-item",
                          ".module-item", ".vod-item",
                          'a[href*="/index.php/vod/detail/"]',
                          'a[href*="/voddetail/"]', 'a[href*="/vod/detail/"]'] if search else
                         ["#main .module-item", "a.module-poster-item", ".module-poster-items-base > a",
                          ".module-items > a.module-item",
                          'a[href*="/index.php/vod/detail/"]',
                          'a[href*="/voddetail/"]', 'a[href*="/vod/detail/"]'])
        else:
            selectors = [SITES[sid].get("searchListSelector" if search else "listSelector",
                                       ".module-search-item" if search else "#main .module-item")]
        nodes = []
        for selector in selectors:
            nodes = soup.select(selector)
            if nodes:
                break
        items, seen = [], set()
        for node in nodes[:MAX_ITEMS * 2]:
            if search and self._search_expired():
                break
            # A CSS union uses DOM order, not selector priority. Cover buttons
            # often precede the actual detail/title link and point to /vod/play/.
            links = ([node] if node.name == "a" else []) + node.select("a[href]")
            link = next((a for a in links if re.search(
                r"/(?:index\.php/vod/detail|voddetail|vod/detail)/", a.get("href", "")
            )), None)
            if link is None:
                if search:
                    continue
                link = node if node.name == "a" else node.select_one("a[href]")
            image = node.select_one("img")
            heading = node.select_one(".module-poster-item-title, .module-item-title, h3 a, h2 a")
            titles = [_text(heading), link.get("title") if link else "",
                      image.get("alt") if image else "",
                      _text(link) if sid == "huajuan" and link is not None else ""]
            title = next((t.strip() for t in titles if t and not t.strip().startswith(
                ("立刻播放", "立即播放"))), "")
            if not title or link is None or not link.get("href"):
                continue
            href = link["href"]
            try:
                _content_href(href)
                if sid == "huajuan" and not re.search(r"/(?:index\.php/vod/detail|voddetail|vod/detail)/", href):
                    continue
                # Bind each item, not the plugin instance: another list may pick another mirror.
                target = urlsplit(urljoin(base, href))
                href = _origin(base) + urlunsplit(("", "", target.path, target.query, ""))
                item_id = _pack([[sid, href]])
            except ValueError:
                continue
            if item_id in seen:
                continue
            seen.add(item_id)
            item = {"id": item_id, "title": title.strip()[:256], "navigation": "detail",
                    "remark": _text(node, ".module-item-text, .module-item-note, .module-poster-item-sub"),
                    "extra": {"site": sid, "source": SITES[sid]["name"]}}
            if search:
                item["extra"]["source_name"] = SITES[sid]["name"]
            year = _text(node, ".module-item-caption span")
            if year:
                item["year"] = year
            if image:
                poster = image.get("data-original") or image.get("data-src") or image.get("src")
                if poster and not any(x in poster for x in ("load.gif", "loading")):
                    try:
                        item["poster"] = _public_url(urljoin(base, poster))
                    except ValueError:
                        pass
            items.append(item)
            if len(items) >= MAX_ITEMS:
                break
        more = bool(soup.select_one('a[rel="next"], .page-next[href], .pagination .next a[href]'))
        if not more:
            more = any("下一页" in a.get_text() and a.get("href") not in (None, "", "#", "javascript:;")
                       for a in soup.select("a"))
        return items, more

    def _filters(self, sid, category=None, selected=None):
        selected = selected or {}
        result = []
        categories = self.categories[sid]
        if categories:
            result.append({"category_id": sid, "key": "categoryId", "name": "分类",
                           "options": [{"name": n, "value": c} for c, n in categories],
                           "selected": str(category or categories[0][0])})
        for group in SITE_FILTERS[sid]:
            result.append({
                "category_id": sid, "key": group["key"], "name": group["name"],
                "options": [{"name": option["n"], "value": option["v"]}
                            for option in group["value"]],
                "selected": str(selected.get(group["key"], group.get("init", ""))),
            })
        return result

    def _category_path(self, sid, cid, page, selected):
        # Home exposes the union across categories. A selected value from that
        # union must remain usable after switching category; never validate only
        # the active category's literal. URI-encode each bounded field separately.
        allowed_keys = {g["key"] for g in SITE_FILTERS[sid]}
        fields = {}
        for key, value in selected.items():
            # Ignore removed controls retained by a player's old filter cache.
            if key in {"categoryId", "letter", "sort", "by"} or value in (None, ""):
                continue
            value = str(value)
            if (key not in allowed_keys or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", key)
                    or len(value.encode()) > 256 or any(ord(c) < 32 for c in value)
                    or value in (".", "..") or "\\" in value):
                raise ValueError("unsafe or unknown category filter")
            fields["by" if key == "sort" else key] = value
        encode = lambda value: quote(str(value), safe="")
        cid = fields.pop("tid", fields.pop("id", cid))
        site = SITES[sid]
        if site.get("categoryUrlWithFilters"):
            template = site["categoryUrlWithFilters"]
            used = set(re.findall(r"\{(\w+)\}", template))
            path = template.format_map({key: encode(value) for key, value in
                                       {**{k: "" for k in used}, **fields,
                                        "categoryId": cid, "page": page}.items()})
            remainder = {k: v for k, v in fields.items() if k not in used}
            return path + ("?" + urlencode(remainder) if remainder else "")
        if site.get("categoryUrl") and not fields:
            return site["categoryUrl"].format(categoryId=encode(cid), page=page)
        segments = "".join("/" + k + "/" + encode(v) for k, v in fields.items())
        return f"/index.php/vod/show/id/{encode(cid)}{segments}/page/{page}.html"

    def _sorted_sites(self):
        return sorted(SITES, key=lambda sid: self.config["sitePriority"].get(sid, 99))

    def homeContent(self, filter=False):
        with self.lock:
            self._request_diagnostics = []
            self._content_succeeded = False
            # Fast, network-free home with statically configured categories.
            # No synthetic recommendation category, filter, quota, cache or list.
            sites = self._sorted_sites()
            return self._document("home", categories=[
                {"id": "site_" + sid, "name": SITES[sid]["name"]} for sid in sites
            ], filters={"site_" + sid: self._filters(sid) for sid in sites})

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        with self.lock:
            self._request_diagnostics = []
            self._content_succeeded = False
            tid, page = str(tid), max(1, min(10000, int(pg)))
            selected = dict(extend or {})
            sid = tid.removeprefix("site_")
            if sid not in SITES:
                raise ValueError("unknown site")
            categories = self.categories[sid]
            cid = str(selected.get("categoryId") or (categories[0][0] if categories else ""))
            if not re.fullmatch(r"\d{1,12}", cid):
                return self._document("list", page=page, filters={"site_" + sid: self._filters(sid)})
            if cid not in {c for c, _ in categories}:
                raise ValueError("unknown category")
            path = self._category_path(sid, cid, page, selected)
            pages = self._fetch_many({sid: path})
            items, more = self._parse_list(sid, *pages[sid]) if sid in pages else ([], False)
            return self._document("list", items, page, more,
                             filters={"site_" + sid: self._filters(sid, cid, selected)})

    def _search_sort_key(self, item, keyword):
        return (-_similarity(item["title"], keyword),
                self.config["sitePriority"].get(item["extra"]["site"], 99))

    def _search_expired(self):
        return self._search_deadline is not None and time.monotonic() >= self._search_deadline

    def _search_remark(self, sid, shares=()):
        # No host/HTTP calls: these are URL presentation hints, not verified
        # playable lines. Never inspect query strings to infer a drive type.
        labels = [SEARCH_SHARE_LABELS.get(
            (urlsplit(url).hostname or "").lower().rstrip(".").removeprefix("www."), "other"
        ) for url in dict.fromkeys(shares)]
        labels.sort(key=lambda label: self.config["linePriority"].get(label, 99))
        counts, names = {}, []
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
            names.append(label + (f"#{counts[label]}" if counts[label] > 1 else ""))
        return SITES[sid]["name"] + (" | " + "，".join(names) if names else "")

    def _filter_search_resources(self, items):
        entries = [(i, *_unpack(item["id"])[0]) for i, item in enumerate(items)]
        for item in items:
            item["remark"] = self._search_remark(item["extra"]["site"])
        pages = self._fetch_entries(entries, SEARCH_DETAIL_BUDGET) if entries else {}
        retained, unknown, empty = [], 0, 0
        for i, item in enumerate(items):
            if self._search_expired():
                retained.extend(items[i:])
                unknown += len(items) - i
                break
            sid = item["extra"]["site"]
            item["remark"] = self._search_remark(sid)
            if i in pages:
                body, base = pages[i]
                soup = BeautifulSoup(body, "html.parser")
                detail = self._parse_detail(soup, base, item["id"])
                if detail and detail["title"].strip().lower() == item["title"].strip().lower():
                    shares = self._share_links(soup, base)
                    if shares:
                        item["remark"] = self._search_remark(sid, shares)
                        retained.append(item)
                    else:
                        empty += 1
                    continue
            # A failed fetch or an unrecognised page is not proof of zero shares.
            unknown += 1
            retained.append(item)
        return retained, unknown, empty

    def searchContent(self, key, quick=False, pg=1):
        with self.lock:
            self._search_deadline = time.monotonic() + SEARCH_TOTAL_BUDGET
            try:
                return self._search_content(key, quick, pg)
            finally:
                self._search_deadline = None

    def _search_content(self, key, quick=False, pg=1):
        with self.lock:
            self._request_diagnostics = []
            self._content_succeeded = False
            key, page = str(key).strip()[:256], max(1, min(10000, int(pg)))
            if not key:
                return self._document("search", page=page)
            paths = {sid: site.get("searchUrl", "/index.php/vod/search/page/{page}/wd/{keyword}.html")
                     .format(keyword=quote(key, safe=""), page=page) for sid, site in SITES.items()}
            pages = self._fetch_many(paths, SEARCH_BUDGET)
            items, more = [], False
            for sid in SITES:
                if self._search_expired():
                    break
                if sid in pages:
                    values, has_next = self._parse_list(sid, *pages[sid], search=True)
                    for item in values:
                        item["remark"] = self._search_remark(sid)
                    items.extend(x for x in values if key.lower() in x["title"].lower())
                    more = more or has_next
            items.sort(key=lambda item: self._search_sort_key(item, key))
            items, unknown, empty = self._filter_search_resources(items)
            result = self._document("search", items, page, more)
            result["metadata"].update(search_unverified_count=unknown,
                                      search_empty_removed_count=empty)
            if self._search_expired():
                result["metadata"].update(request_status="partial", search_timed_out=True)
            return result

    def _share_links(self, soup, base):
        # Extract page facts, not drive matching. The host recognizes each candidate.
        urls = []
        nodes = soup.select(".module-row-info p, a.down-card-url")
        for node in nodes:
            for attr in ("href", "data-url", "data-clipboard-text"):
                if node.get(attr):
                    urls.append(urljoin(base, node[attr]))
            urls.extend(urljoin(base, a["href"]) for a in node.select("a[href]"))
            urls.extend(re.findall(r'https?://[^\s<>"\'，。]+', node.get_text(" ", strip=True)))
        # Also collect explicit copy controls, never arbitrary footer/navigation
        # links. Drive recognition still belongs to the public host bridge.
        for node in soup.select(".module-row-info a[href], [data-clipboard-text], [data-url]"):
            for attr in ("href", "data-clipboard-text", "data-url"):
                if node.get(attr):
                    urls.append(urljoin(base, node[attr]))
        result = []
        for url in urls:
            try:
                _public_url(url)
                if _origin(url) == _origin(base):
                    continue
            except ValueError:
                continue
            if url not in result:
                result.append(url)
        return result[:MAX_SHARES]

    def _parse_detail(self, soup, base, item_id):
        title = (_text(soup, ".page-title") or _text(soup, "h1"))[:256]
        if not title:
            return None
        extra = {"content": _text(soup, ".module-info-introduction, .module-info-content, .vod_content")}
        # Sites use sibling-based video-info markup.
        for label in soup.select(".video-info-itemtitle, .module-info-item-title"):
            sibling = label.find_next_sibling()
            if sibling is None:
                continue
            key = label.get_text(strip=True)
            anchors = ", ".join(a.get_text(strip=True) for a in sibling.select("a") if a.get_text(strip=True))
            if "剧情" in key or "简介" in key:
                extra["content"] = _text(sibling, "p") or _text(sibling)
            elif "导演" in key:
                extra["director"] = anchors or _text(sibling)
            elif "主演" in key:
                extra["actor"] = anchors or _text(sibling)
        item = {"id": item_id, "title": title, "navigation": "detail", "extra": extra}
        image = soup.select_one(".mobile-play .lazyload") or soup.select_one(
            ".module-info-poster img, .module-item-pic img")
        if image:
            pic = image.get("data-original") or image.get("data-src") or image.get("src")
            if pic:
                try:
                    item["poster"] = _public_url(urljoin(base, pic))
                except ValueError:
                    pass
        return item

    def detailContent(self, ids):
        with self.lock:
            self._request_diagnostics = []
            self._content_succeeded = False
            if not ids:
                return self._document("detail")
            item_id = str(ids[0])
            members = sorted(_unpack(item_id), key=lambda x: self.config["sitePriority"].get(x[0], 99))
            pages = self._fetch_entries([(i, sid, href) for i, (sid, href) in enumerate(members)], GET_BUDGET)
            primary, fallback, sources = None, None, []
            # Reuse host results for identical share URLs, not site quota/line identity.
            share_cache = {}
            seen_lines, line_counts = set(), {}
            multiple_sites = len({member[0] for member in members}) > 1
            for i, (sid, _href) in enumerate(members):
                if i not in pages:
                    continue
                body, base = pages[i]
                soup = BeautifulSoup(body, "html.parser")
                item = self._parse_detail(soup, base, item_id)
                if item is None:
                    continue
                fallback = fallback or item
                info = _text(soup, ".module-info-tag, .module-info-heading")
                media_kind = "movie" if "电影" in info and not any(x in info for x in ("电视剧", "剧集")) else "tv"
                counts = {}
                site_sources = []
                for url in self._share_links(soup, base):
                    if self.host is None:
                        continue
                    try:
                        cache_key = (url, media_kind, item["title"])
                        if cache_key not in share_cache:
                            share_cache[cache_key] = self.host.invoke("drive.list_share", {
                                "share_url": url, "media_kind": media_kind, "media_title": item["title"],
                            })
                        facts = share_cache[cache_key]
                        driver = facts["driver"]
                        if not isinstance(driver, str) or not driver:
                            continue
                        count = counts.get(driver, 0)
                        if count >= (3 if driver == "quark" else 2):
                            continue
                        line_id = "line_" + hashlib.sha256((sid + "\0" + url).encode()).hexdigest()[:20]
                        if line_id in seen_lines:
                            continue
                        episodes = []
                        for index, resource in enumerate(facts["items"][:2000]):
                            ref, label = resource.get("ref"), resource.get("name")
                            if (not isinstance(ref, str) or not 1 <= len(ref.encode()) <= 4096
                                    or ref.lower().startswith(("http:", "https:", "file:", "data:"))
                                    or not isinstance(label, str) or not label):
                                continue
                            episodes.append({"id": str(resource.get("index", index)), "name": label, "ref": ref})
                        if not episodes:
                            continue
                        counts[driver] = count + 1  # Only successful parsed lines consume quota.
                        line_count = line_counts.get((sid, driver), 0) + 1
                        line_counts[(sid, driver)] = line_count
                        name = driver + (f"#{line_count}" if line_count > 1 else "")
                        if multiple_sites:
                            name += "#" + SITES[sid]["name"]
                        seen_lines.add(line_id)
                        site_sources.append({"id": line_id, "name": name, "episodes": episodes,
                                             "_driver": driver})
                    except Exception:
                        continue
                if site_sources:
                    primary = primary or item
                    sources.extend(site_sources)
            item = primary or fallback
            if item is None:
                return self._document("detail")
            sources.sort(key=lambda x: self.config["linePriority"].get(x["_driver"], 99))
            for source in sources:
                source.pop("_driver")
            item["play_sources"] = sources[:MAX_PLAY_SOURCES]
            result = self._document("detail", [item])
            if len(sources) > MAX_PLAY_SOURCES:
                result["metadata"]["omitted_play_sources"] = len(sources) - MAX_PLAY_SOURCES
            if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_DETAIL_BYTES:
                raise ValueError("WANOU_DETAIL_TOO_LARGE")
            return result

    def playerContent(self, flag, ref, vipFlags=None):
        with self.lock:
            self._request_diagnostics = []
            self._content_succeeded = False
            if (not isinstance(ref, str) or not 1 <= len(ref.encode()) <= 4096 or self.host is None
                    or ref.lower().startswith(("http:", "https:", "file:", "data:"))):
                raise ValueError("invalid drive reference")
            result = self.host.invoke("drive.resolve_ref", {"ref": ref})
            if not isinstance(result, dict) or result.get("kind") != "drive_resource":
                raise ValueError("host did not return drive resource facts")
            result = dict(result)
            result.setdefault("schema_version", "mv.python-playback-resolution.v1")
            return result


def create_plugin(context=None):
    return WanouPlugin(context)
