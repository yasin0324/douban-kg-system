"""
用户行为路由 — /api/users
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_mysql_conn, get_current_user
from app.models.user import UserPreferenceCreate, UserRatingCreate, UserRatingLookupResponse
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["用户行为"])


# ---------- 偏好 ----------

@router.post("/preferences", summary="添加偏好（喜欢/想看）")
def add_preference(body: UserPreferenceCreate, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    result = user_service.add_preference(conn, user["id"], body.mid, body.pref_type)
    return result


@router.delete("/preferences/{mid}", summary="取消偏好")
def remove_preference(mid: str, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    ok = user_service.remove_preference(conn, user["id"], mid)
    if not ok:
        raise HTTPException(status_code=404, detail="偏好记录不存在")
    return {"message": "已取消"}


@router.get("/preferences", summary="获取偏好列表")
def list_preferences(
    pref_type: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    conn=Depends(get_mysql_conn),
):
    return user_service.list_preferences(conn, user["id"], pref_type, page, size)


@router.get("/preferences/check/{mid}", summary="检查偏好状态")
def check_preference(mid: str, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    return user_service.check_preference(conn, user["id"], mid)


# ---------- 评分 ----------

@router.post("/ratings", summary="创建/更新评分")
def add_rating(body: UserRatingCreate, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    try:
        return user_service.add_rating(conn, user["id"], body.mid, body.rating, body.comment_short)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/ratings/{mid}", summary="删除评分")
def remove_rating(mid: str, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    ok = user_service.remove_rating(conn, user["id"], mid)
    if not ok:
        raise HTTPException(status_code=404, detail="评分记录不存在")
    return {"message": "已删除"}


@router.get("/ratings", summary="获取评分列表")
def list_ratings(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    conn=Depends(get_mysql_conn),
):
    return user_service.list_ratings(conn, user["id"], page, size)


@router.get("/ratings/{mid}", response_model=UserRatingLookupResponse, summary="获取某电影评分")
def get_rating(mid: str, user=Depends(get_current_user), conn=Depends(get_mysql_conn)):
    result = user_service.get_rating(conn, user["id"], mid)
    if not result:
        return {
            "mid": mid,
            "has_rating": False,
            "id": None,
            "rating": None,
            "comment_short": None,
            "rated_at": None,
        }
    return {"has_rating": True, **result}
