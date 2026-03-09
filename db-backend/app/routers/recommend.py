from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user, get_mysql_conn
from app.services import recommend_service

router = APIRouter(prefix="/api/recommend", tags=["推荐系统"])

@router.get("/personal", summary="个人电影推荐")
async def get_personal_recommendations(
    algorithm: Optional[str] = Query(
        "cfkg",
        description="推荐算法类型: cfkg, ppr, content, cf, hybrid, itemcf, tfidf",
    ),
    limit: int = Query(20, ge=1, le=50),
    exclude_movie_ids: Optional[List[str]] = Query(None, description="重新生成时希望尽量避开的电影"),
    reroll_token: Optional[str] = Query(None, description="重新生成请求的随机标识"),
    user=Depends(get_current_user),
    conn=Depends(get_mysql_conn),
):
    try:
        return await recommend_service.build_personal_recommendation_payload(
            conn=conn,
            user_id=user["id"],
            algorithm=algorithm,
            limit=limit,
            exclude_movie_ids=exclude_movie_ids,
            reroll_token=reroll_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain", summary="推荐结果解释图")
def explain_recommendation(
    target_mid: str = Query(..., description="目标推荐电影 ID"),
    algorithm: Optional[str] = Query(
        "cfkg",
        description="推荐算法类型: cfkg, ppr, content, cf, hybrid, itemcf, tfidf",
    ),
    user=Depends(get_current_user),
    conn=Depends(get_mysql_conn),
):
    try:
        return recommend_service.build_recommendation_explain_payload(
            conn=conn,
            user_id=user["id"],
            target_mid=target_mid,
            algorithm=algorithm,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
