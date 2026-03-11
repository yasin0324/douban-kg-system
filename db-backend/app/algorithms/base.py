"""
推荐算法基类 — 所有推荐算法的统一接口
"""

from abc import ABC, abstractmethod


class BaseRecommender(ABC):
    """推荐算法基类"""

    name: str = "base"
    display_name: str = "基础推荐"

    @abstractmethod
    def recommend(
        self,
        user_id: int,
        n: int = 20,
        exclude_mids: set | None = None,
        exclude_from_training: set | None = None,
    ) -> list[dict]:
        """
        为指定用户生成推荐列表

        Args:
            user_id: 用户 ID
            n: 推荐数量
            exclude_mids: 需要从候选集中排除的电影（如已推荐过的）
            exclude_from_training: 仅从训练集（用户画像）中排除，但保留在候选集里
                                    评估时传入 test_mid，使算法有机会推荐出它

        Returns:
            推荐列表，每项为:
            {
                "mid": str,       # 电影 ID
                "score": float,   # 推荐分数 (0~1)
                "reason": str,    # 推荐理由
            }
        """

    def get_user_positive_movies(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
    ) -> list[dict]:
        """获取用户正向评分的电影（评分 >= threshold）

        Args:
            exclude_mids: 从训练集中排除的电影（leave-one-out 评估时传入 test_mid）
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid, rating FROM user_movie_ratings "
                "WHERE user_id = %s AND rating >= %s "
                "ORDER BY rating DESC",
                (user_id, threshold),
            )
            rows = cursor.fetchall()

        if exclude_mids:
            rows = [r for r in rows if str(r["mid"]) not in exclude_mids]
        return rows

    def get_user_all_rated_mids(self, conn, user_id: int, exclude_mids: set | None = None) -> set:
        """获取用户所有已评分电影的 mid 集合

        Args:
            exclude_mids: 从训练集中排除的电影（leave-one-out 评估时传入 test_mid）
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid FROM user_movie_ratings WHERE user_id = %s",
                (user_id,),
            )
            mids = {str(row["mid"]) for row in cursor.fetchall()}

        if exclude_mids:
            mids -= exclude_mids
        return mids
