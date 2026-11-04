// heyitao.com/wallpaper/* → Cloudflare Pages 项目
//
// Cloudflare Pages 的 Custom domains 只接受域名/子域名，不接受子路径，所以博客下的
// /wallpaper 只能靠 Worker 在入站侧改写请求转发。站点本身全是相对路径（vite base './'、
// api.js 用 './data/'、sw.js 按自身 URL 推部署根），转发后无需重写 HTML。
//
// 部署：cd worker && CLOUDFLARE_ACCOUNT_ID=<nolanhet 账号> npx wrangler deploy

const PREFIX = '/wallpaper'
const ORIGIN = 'https://bing-wallpaper-atlas-5n6.pages.dev'

export default {
  async fetch(request) {
    const url = new URL(request.url)
    // 无尾斜杠时补上：页面里的 './assets/…' 要靠尾斜杠才能解析到 /wallpaper/ 下面
    if (url.pathname === PREFIX) return Response.redirect(`${url.origin}${PREFIX}/${url.search}`, 301)

    const rest = url.pathname.slice(PREFIX.length) || '/'
    const resp = await fetch(new Request(new URL(rest + url.search, ORIGIN), request))

    const headers = new Headers(resp.headers)
    // Pages 返回的路径相对 Location（目录补斜杠等）要补回前缀，否则会跳到博客根目录
    const loc = headers.get('location')
    if (loc?.startsWith('/')) headers.set('location', PREFIX + loc)
    return new Response(resp.body, { status: resp.status, headers })
  },
}
