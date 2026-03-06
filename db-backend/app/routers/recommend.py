from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional

from app.dependencies import get_current_user, get_mysql_conn
from app.algorithms.hybrid_manager import manager as hybrid_manager
from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations
from app.services import user_service

router = APIRouter(prefix="/api/recommend", tags=["推荐系统"])

@router.get("/personal", summary="个人电影推荐")
async def get_personal_recommendations(
    algorithm: Optional[str] = Query("hybrid", description="推荐算法类型: ppr, content, cf, hybrid"),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(get_current_user),
    conn=Depends(get_mysql_conn)
):
    user_id = user["id"]
    
    # 动态获取当前用户最近打高分的电影作为种子节点
    seeds = user_service.get_high_rated_movie_ids(conn, user_id, limit=5)
    
    # 防止完全冷启动报错，如果没有最近高分历史，退化一下提供备用的种子电影
    if not seeds:
        seeds = ["1292052", "1291546", "1292720"] # 肖申克的救赎, 霸王别姬, 阿甘正传作为退路
        
    try:
        if algorithm == "ppr":
            results = await get_graph_ppr_recommendations(user_id, seeds, limit)
        elif algorithm == "content":
            results = await get_graph_content_recommendations(user_id, seeds, limit)
        elif algorithm == "cf":
            results = await get_graph_cf_recommendations(user_id, limit)
        elif algorithm == "hybrid":
            results = await hybrid_manager.get_hybrid_recommendations(user_id, seeds, limit)
        else:
            raise HTTPException(status_code=400, detail="不支持的算法类型")
            
        return {"items": results, "algorithm": algorithm}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
