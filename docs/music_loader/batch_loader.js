/**
 * 书院管家 - 批量音乐源加载器
 * 在 PeekPro 音乐→导入脚本→在线链接 中填入此 URL，
 * 会自动从仓库拉取全部音乐源并加载。
 *
 * 格式：洛雪音乐 LX 自定义源
 */

const REPO_BASE = 'https://huoliuli.github.io/shuyuan-keeper';
const MUSIC_LIST_URL = REPO_BASE + '/peek_music.json';

// 缓存已加载的源
let loadedSources = null;
let sourceMap = {};

async function fetchSourceList() {
  if (loadedSources) return loadedSources;
  try {
    const resp = await fetch(MUSIC_LIST_URL);
    const list = await resp.json();
    loadedSources = list.filter(m => m.url && m.url.endsWith('.js'));
    return loadedSources;
  } catch (e) {
    console.error('[batch_loader] fetch list failed:', e);
    return [];
  }
}

// 动态加载单个音乐源脚本
async function loadSourceScript(sourceUrl) {
  try {
    const resp = await fetch(sourceUrl);
    const code = await resp.text();
    // 在沙箱中执行
    const module = { exports: {} };
    const fn = new Function('module', 'exports', 'require', code);
    fn(module, module.exports, require);
    return module.exports.default || module.exports;
  } catch (e) {
    console.error('[batch_loader] load source failed:', sourceUrl, e);
    return null;
  }
}

const batchLoader = {
  async init() {
    const list = await fetchSourceList();
    for (const src of list) {
      const mod = await loadSourceScript(src.url);
      if (mod) {
        sourceMap[src.name] = mod;
      }
    }
    console.log('[batch_loader] loaded', Object.keys(sourceMap).length, 'music sources');
  },

  async musicSearch(keyword, page = 1, limit = 25) {
    const results = [];
    for (const [name, mod] of Object.entries(sourceMap)) {
      if (mod.musicSearch && mod.musicSearch.search) {
        try {
          const r = await mod.musicSearch.search(keyword, page, limit);
          if (r && r.list) {
            results.push(...r.list.map(s => ({ ...s, source: name })));
          }
        } catch (e) {}
      }
    }
    return { list: results, total: results.length };
  },

  async getMusicUrl(songInfo, type) {
    const sourceName = songInfo.source;
    const mod = sourceMap[sourceName];
    if (mod && mod.getMusicUrl) {
      return await mod.getMusicUrl(songInfo, type);
    }
    // 尝试所有源
    for (const [name, m] of Object.entries(sourceMap)) {
      if (m.getMusicUrl) {
        try {
          return await m.getMusicUrl(songInfo, type);
        } catch (e) {}
      }
    }
    throw new Error('No source found for this song');
  },

  async getLyric(songInfo) {
    const mod = sourceMap[songInfo.source];
    if (mod && mod.getLyric) return await mod.getLyric(songInfo);
    return '';
  },

  async getPic(songInfo) {
    const mod = sourceMap[songInfo.source];
    if (mod && mod.getPic) return await mod.getPic(songInfo);
    return '';
  },
};

export default batchLoader;
