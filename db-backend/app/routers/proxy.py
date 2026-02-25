"""
图片代理路由 — /api/proxy
将豆瓣图片请求通过后端代理,添加正确的 Referer 头以绕过防盗链
"""
import httpx
from fastapi import APIRouter, Query, Response
from fastapi.responses import Response as FastResponse

router = APIRouter(prefix="/api/proxy", tags=["代理"])

# 允许代理的域名白名单
ALLOWED_HOSTS = {"img1.doubanio.com", "img2.doubanio.com", "img3.doubanio.com",
                 "img4.doubanio.com", "img5.doubanio.com", "img6.doubanio.com",
                 "img7.doubanio.com", "img8.doubanio.com", "img9.doubanio.com",
                 "img1.douban.com", "img2.douban.com", "img3.douban.com",
                 "img4.douban.com", "img5.douban.com", "img6.douban.com",
                 "img7.douban.com", "img8.douban.com", "img9.douban.com"}


@router.get("/image", summary="图片代理")
async def proxy_image(url: str = Query(..., description="原始图片 URL")):
    """代理外部图片请求，添加正确的 Referer 以绕过防盗链"""
    from urllib.parse import urlparse
    parsed = urlparse(url)

    # 安全检查：只代理白名单域名
    if parsed.hostname not in ALLOWED_HOSTS:
        return Response(status_code=403, content="Forbidden: domain not allowed")

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "Referer": "https://movie.douban.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                },
            )
            if resp.status_code != 200:
                return Response(status_code=resp.status_code)

            content_type = resp.headers.get("content-type", "image/webp")
            return FastResponse(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except Exception:
        return Response(status_code=502, content="Bad Gateway")
