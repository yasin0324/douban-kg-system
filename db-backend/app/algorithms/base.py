"""
推荐算法基类 — 所有推荐算法的统一接口
"""

from abc import ABC, abstractmethod


class BaseRecommender(ABC):
    """推荐算法基类"""

    name: str = "base"
    display_name: str = "基础推荐"

    def set_params(self, **params):
        """允许评估器在不重建实例的情况下切换参数。"""
        if not params:
            return
        raise NotImplementedError(f"{self.__class__.__name__} 不支持动态参数更新")

    @classmethod
    def parameter_grid(cls) -> list[dict]:
        """返回验证集调参搜索空间。默认不调参。"""
        return [{}]

    @classmethod
    def ablation_configs(cls) -> dict[str, dict]:
        """返回需要在报告中固定输出的消融配置。"""
        return {}

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

    # 偏好类型 → 合成评分映射
    PREF_SYNTHETIC_RATING = {
        "like": 4.5,
        "want_to_watch": 4.0,
    }
    KG_SIGNAL_PRIORITY = {
        "rating": 0,
        "like": 1,
        "want_to_watch": 2,
    }

    def get_user_positive_movies(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
    ) -> list[dict]:
        """获取用户正向电影（评分 >= threshold + 偏好融合）

        融合规则：
        - 评分 >= threshold 的电影直接加入，使用真实评分
        - like（无评分 or 评分 < threshold）→ 合成评分 4.5
        - want_to_watch（无评分 or 评分 < threshold）→ 合成评分 4.0
        - 同一电影已有 >= threshold 的评分则不叠加偏好
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid, rating FROM user_movie_ratings "
                "WHERE user_id = %s AND rating >= %s "
                "ORDER BY rating DESC",
                (user_id, threshold),
            )
            rated_rows = cursor.fetchall()

            cursor.execute(
                "SELECT mid, pref_type FROM user_movie_prefs WHERE user_id = %s",
                (user_id,),
            )
            pref_rows = cursor.fetchall()

        if exclude_mids:
            rated_rows = [r for r in rated_rows if str(r["mid"]) not in exclude_mids]

        # 已有正向评分的电影 mid 集合
        rated_mid_set = {str(r["mid"]) for r in rated_rows}

        # 融合偏好：同一电影若已有正向评分则跳过
        for pref in pref_rows:
            mid = str(pref["mid"])
            if exclude_mids and mid in exclude_mids:
                continue
            if mid in rated_mid_set:
                continue
            synthetic = self.PREF_SYNTHETIC_RATING.get(pref["pref_type"])
            if synthetic:
                rated_rows.append({"mid": mid, "rating": synthetic})

        # 按评分降序
        rated_rows.sort(key=lambda r: float(r["rating"]), reverse=True)
        return rated_rows

    def get_user_positive_movies_for_kg(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
        *,
        max_positive_ratings: int = 50,
        max_likes: int = 20,
        max_wishes: int = 10,
    ) -> list[dict]:
        """为 KG 分支截断正反馈种子，避免重度用户把图谱算法拖爆。"""
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid, rating, rated_at FROM user_movie_ratings "
                "WHERE user_id = %s AND rating >= %s "
                "ORDER BY rating DESC, rated_at DESC",
                (user_id, threshold),
            )
            rated_rows = cursor.fetchall()

            cursor.execute(
                "SELECT mid, pref_type, created_at FROM user_movie_prefs "
                "WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            pref_rows = cursor.fetchall()

        if exclude_mids:
            rated_rows = [row for row in rated_rows if str(row["mid"]) not in exclude_mids]

        positive_rating_mids = {str(row["mid"]) for row in rated_rows}
        selected: list[dict] = []

        def _take_rows(rows: list[dict], limit: int, signal_source: str) -> None:
            if limit <= 0:
                return
            for row in rows[:limit]:
                selected.append(
                    {
                        "mid": str(row["mid"]),
                        "rating": float(row["rating"]),
                        "signal_source": signal_source,
                        "signal_timestamp": row.get("rated_at") or row.get("created_at"),
                    }
                )

        _take_rows(rated_rows, int(max_positive_ratings), "rating")

        likes = []
        wishes = []
        for pref in pref_rows:
            mid = str(pref["mid"])
            if exclude_mids and mid in exclude_mids:
                continue
            if mid in positive_rating_mids:
                continue
            pref_type = str(pref["pref_type"])
            synthetic_rating = self.PREF_SYNTHETIC_RATING.get(pref_type)
            if synthetic_rating is None:
                continue
            row = {
                "mid": mid,
                "rating": float(synthetic_rating),
                "created_at": pref.get("created_at"),
            }
            if pref_type == "like":
                likes.append(row)
            elif pref_type == "want_to_watch":
                wishes.append(row)

        _take_rows(likes, int(max_likes), "like")
        _take_rows(wishes, int(max_wishes), "want_to_watch")

        selected.sort(key=lambda row: str(row.get("signal_timestamp") or ""), reverse=True)
        selected.sort(
            key=lambda row: self.KG_SIGNAL_PRIORITY.get(str(row.get("signal_source")), 99)
        )
        selected.sort(key=lambda row: float(row["rating"]), reverse=True)
        return selected

    def get_user_all_rated_mids(self, conn, user_id: int, exclude_mids: set | None = None) -> set:
        """获取用户所有已交互电影的 mid 集合（评分 + 偏好）

        Args:
            exclude_mids: 从训练集中排除的电影（leave-one-out 评估时传入 test_mid）
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid FROM user_movie_ratings WHERE user_id = %s",
                (user_id,),
            )
            mids = {str(row["mid"]) for row in cursor.fetchall()}

            cursor.execute(
                "SELECT mid FROM user_movie_prefs WHERE user_id = %s",
                (user_id,),
            )
            mids |= {str(row["mid"]) for row in cursor.fetchall()}

        if exclude_mids:
            mids -= exclude_mids
        return mids
