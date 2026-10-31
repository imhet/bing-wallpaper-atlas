import { ref } from 'vue'
import { MARKET_LABEL } from './api'

// 界面文案中英双语。语言的判定：用户手动选过就听用户的，否则中文浏览器（含繁体）中文、
// 其余一律英文——站点部署在 GitHub Pages，海外访客占多数。
// 数据的 title/desc 本身是多市场原生的英文/日文等，这里只翻界面骨架。
export const MESSAGES = {
  zh: {
    appTitle: 'Bing 壁纸图集',
    loading: '加载中…',
    semanticWarming: '语义搜索准备中…',
    backToBrowse: '返回浏览',
    backToBrowseArrow: '← 返回浏览',
    updatesEntry: '{n} 张图 · 更新日志 →',
    favoritesEntry: '收藏 {n}',
    themeAuto: '主题 · 自动',
    themeLight: '主题 · 浅色',
    themeDark: '主题 · 深色',
    notFoundHint: '没找到「{q}」，试试它的其他写法：',
    emptyFavorites: '还没有收藏。浏览时点卡片右上角的 ♥，喜欢的图就会留在这里（只存这台浏览器里）。',
    exportFavs: '⬇ 导出收藏',
    importFavs: '⬆ 导入收藏',
    importFailed: '导入失败：不是本站导出的收藏文件',
    importedN: '已导入 {n} 张新收藏',
    loadFailed: '数据加载失败：{msg}',
    footer: '图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。',
    countFound: '找到 {n} 张',
    countAll: '共 {n} 张',
    countFavorites: '共收藏 {n} 张',
    countLoadingSuffix: '（数据加载中…）',
    searchPlaceholder: '搜索标题、地点、画面内容…（如：中国 西藏 雪山；日期如 10-01）',
    searchAria: '搜索',
    random: '🎲 随机看看',
    dimMarket: '市场',
    dimYear: '年份',
    dimMonth: '月份',
    dimRegion: '国家/地区',
    dimPhotographer: '摄影师',
    dimResolution: '分辨率',
    allMarket: '全部市场',
    allYear: '全部年份',
    allMonth: '全部月份',
    allRegion: '全部国家/地区',
    allPhotographer: '全部摄影师',
    allResolution: '全部分辨率',
    monthN: '{n} 月',
    close: '关闭',
    searchDim: '搜索{label}…',
    noMatchDim: '没有匹配的{label}',
    limitHint: '仅显示前 {n} 项，输入关键字可缩小范围',
    dataStillLoading: '数据仍在加载，请稍候…',
    noMatch: '没有匹配的壁纸，试试放宽筛选条件。',
    favorite: '收藏',
    unfavorite: '取消收藏',
    faved: '已收藏',
    immerse: '⛶ 沉浸观赏',
    sceneLabel: '画面',
    factDate: '日期',
    factLocation: '地点',
    factRegion: '国家/地区',
    factPhotographer: '摄影师',
    factGallery: '图库',
    download: '下载 {label}',
    original: '原图',
    backstory: '背后故事 ↗',
    siblings: '同图其他市场（{n}）',
    similar: '相似的图',
    similarAria: '查看相似的图：{title}',
    exitImmersive: '退出沉浸模式',
    prevImage: '上一张',
    nextImage: '下一张',
    immersiveHint: '← → 切换 · 双击收藏 · ↑ 收藏 ↓ 取消 · Esc 退出',
    chooseYear: '选择年份',
    yearN: '{y} 年',
    daysImages: '{d} 天 · {n} 张',
    noDataYear: '该年份暂无数据。',
    scrollMore: '下滑加载更早的日期…',
    backToTop: '返回顶部',
    toTop: '↑ 顶部',
    langSwitch: 'EN', // 按钮显示「切过去的语言」
  },
  en: {
    appTitle: 'Bing Wallpaper Atlas',
    loading: 'Loading…',
    semanticWarming: 'Preparing semantic search…',
    backToBrowse: 'Back to browse',
    backToBrowseArrow: '← Back to browse',
    updatesEntry: '{n} images · Changelog →',
    favoritesEntry: 'Favorites {n}',
    themeAuto: 'Theme · Auto',
    themeLight: 'Theme · Light',
    themeDark: 'Theme · Dark',
    notFoundHint: 'No results for “{q}” — try another spelling:',
    emptyFavorites: 'No favorites yet. Tap the ♥ on any card and it will be saved here (this browser only).',
    exportFavs: '⬇ Export',
    importFavs: '⬆ Import',
    importFailed: 'Import failed: not a favorites file exported by this site',
    importedN: 'Imported {n} new favorites',
    loadFailed: 'Failed to load data: {msg}',
    footer: 'Image copyrights belong to Microsoft and their respective authors/agencies. This site only indexes metadata and links.',
    countFound: '{n} images found',
    countAll: '{n} images',
    countFavorites: '{n} favorites',
    countLoadingSuffix: ' (loading data…)',
    searchPlaceholder: 'Search titles, places, visual content… (e.g. China Tibet snow; date like 10-01)',
    searchAria: 'Search',
    random: '🎲 Surprise me',
    dimMarket: 'Market',
    dimYear: 'Year',
    dimMonth: 'Month',
    dimRegion: 'Country',
    dimPhotographer: 'Photographer',
    dimResolution: 'Resolution',
    allMarket: 'All markets',
    allYear: 'All years',
    allMonth: 'All months',
    allRegion: 'All countries',
    allPhotographer: 'All photographers',
    allResolution: 'All resolutions',
    monthN: '{n}',
    close: 'Close',
    searchDim: 'Search {label}…',
    noMatchDim: 'No matching {label}',
    limitHint: 'Showing the first {n}. Type to narrow down.',
    dataStillLoading: 'Still loading data, please wait…',
    noMatch: 'No wallpapers match. Try relaxing the filters.',
    favorite: 'Favorite',
    unfavorite: 'Unfavorite',
    faved: 'Favorited',
    immerse: '⛶ Immersive view',
    sceneLabel: 'Scene',
    factDate: 'Date',
    factLocation: 'Location',
    factRegion: 'Country',
    factPhotographer: 'Photographer',
    factGallery: 'Agency',
    download: 'Download {label}',
    original: 'Original',
    backstory: 'Backstory ↗',
    siblings: 'Same image in other markets ({n})',
    similar: 'Similar images',
    similarAria: 'View similar image: {title}',
    exitImmersive: 'Exit immersive view',
    prevImage: 'Previous',
    nextImage: 'Next',
    immersiveHint: '← → browse · double-click to favorite · ↑ favorite ↓ unfavorite · Esc exit',
    chooseYear: 'Choose year',
    yearN: '{y}',
    daysImages: '{d} days · {n} images',
    noDataYear: 'No data for this year.',
    scrollMore: 'Scroll for earlier dates…',
    backToTop: 'Back to top',
    toTop: '↑ Top',
    langSwitch: '中文',
  },
}

// 数据侧 region 是中文规范名（77 个，来自 crawler/regions.py 的 COUNTRY_ALIASES）。
// 只影响展示：筛选值、URL 参数仍是中文原值，英文模式只是换个说法。
export const REGION_EN = {
  不丹: 'Bhutan', 中国: 'China', 丹麦: 'Denmark', 乌拉圭: 'Uruguay', 以色列: 'Israel',
  俄罗斯: 'Russia', 保加利亚: 'Bulgaria', 克罗地亚: 'Croatia', 冰岛: 'Iceland', 加拿大: 'Canada',
  匈牙利: 'Hungary', 南极洲: 'Antarctica', 南非: 'South Africa', 博茨瓦纳: 'Botswana', 印度: 'India',
  印度尼西亚: 'Indonesia', 厄瓜多尔: 'Ecuador', 哈萨克斯坦: 'Kazakhstan', 哥伦比亚: 'Colombia',
  哥斯达黎加: 'Costa Rica', 土耳其: 'Turkey', 坦桑尼亚: 'Tanzania', 埃及: 'Egypt', 墨西哥: 'Mexico',
  奥地利: 'Austria', 委内瑞拉: 'Venezuela', 尼泊尔: 'Nepal', 巴基斯坦: 'Pakistan', 巴拿马: 'Panama',
  巴西: 'Brazil', 希腊: 'Greece', 德国: 'Germany', 意大利: 'Italy', 挪威: 'Norway', 捷克: 'Czechia',
  摩洛哥: 'Morocco', 斯洛伐克: 'Slovakia', 斯洛文尼亚: 'Slovenia', 斯里兰卡: 'Sri Lanka',
  新加坡: 'Singapore', 新西兰: 'New Zealand', 日本: 'Japan', 智利: 'Chile', 柬埔寨: 'Cambodia',
  格陵兰: 'Greenland', 比利时: 'Belgium', 沙特阿拉伯: 'Saudi Arabia', 法国: 'France', 波兰: 'Poland',
  泰国: 'Thailand', 澳大利亚: 'Australia', 爱尔兰: 'Ireland', 玻利维亚: 'Bolivia', 瑞典: 'Sweden',
  瑞士: 'Switzerland', 秘鲁: 'Peru', 突尼斯: 'Tunisia', 约旦: 'Jordan', 纳米比亚: 'Namibia',
  缅甸: 'Myanmar', 罗马尼亚: 'Romania', 美国: 'United States', 老挝: 'Laos', 肯尼亚: 'Kenya',
  芬兰: 'Finland', 英国: 'United Kingdom', 荷兰: 'Netherlands', 菲律宾: 'Philippines',
  葡萄牙: 'Portugal', 蒙古: 'Mongolia', 西班牙: 'Spain', 越南: 'Vietnam', 阿根廷: 'Argentina',
  阿联酋: 'United Arab Emirates', 韩国: 'South Korea', 马来西亚: 'Malaysia', 马达加斯加: 'Madagascar',
}

const LANGS = ['zh', 'en']
const STORAGE_KEY = 'bwa-lang'

// 浏览器语言缺失/为空时按英文处理：纯中文用户由 zh 前缀识别，覆盖繁体
export function pickLang(stored, browserLang) {
  if (LANGS.includes(stored)) return stored
  return /^zh/i.test(String(browserLang || '')) ? 'zh' : 'en'
}

export function format(tpl, vars) {
  return String(tpl).replace(/\{(\w+)\}/g, (m, k) => (k in (vars || {}) ? String(vars[k]) : m))
}

export function imageCount(l, n) {
  return l === 'en' ? `${n} image${n === 1 ? '' : 's'}` : `${n} 张`
}

export const lang = ref('zh')

// 读 lang.value 让模板建立响应式依赖：切换语言时全部 t() 重新求值
export function t(key, vars) {
  const table = MESSAGES[lang.value] || MESSAGES.zh
  return format(table[key] ?? MESSAGES.zh[key] ?? key, vars)
}

export const regionLabel = (v) => (lang.value === 'en' ? REGION_EN[v] || v : v)

// 市场名中英有别（数据里的市场代码 zh-cn 等不能直接给用户看）
const MARKET_LABEL_EN = {
  'zh-cn': 'Chinese', 'zh-tw': 'Chinese (Traditional)', 'ja-jp': 'Japanese', 'de-de': 'German', 'fr-fr': 'French',
}
export const marketLabel = (m) =>
  lang.value === 'en' ? MARKET_LABEL_EN[m] || MARKET_LABEL[m] || m : MARKET_LABEL[m] || m

export function applyLang() {
  document.documentElement.lang = lang.value === 'en' ? 'en' : 'zh-CN'
  document.title = MESSAGES[lang.value].appTitle
}

export function setLang(l) {
  lang.value = LANGS.includes(l) ? l : 'zh'
  localStorage.setItem(STORAGE_KEY, lang.value)
  applyLang()
}

export function initLang() {
  lang.value = pickLang(localStorage.getItem(STORAGE_KEY), navigator.language)
  applyLang()
}
