/**
 * 将豆瓣图片 URL 转换为通过后端代理的 URL
 * 解决豆瓣 CDN 的 Referer 防盗链 (418 错误)
 */
export function proxyImage(url) {
    if (!url) return "";
    // 只代理豆瓣图片 URL
    if (url.includes("doubanio.com") || url.includes("douban.com/view")) {
        return `/api/proxy/image?url=${encodeURIComponent(url)}`;
    }
    return url;
}
