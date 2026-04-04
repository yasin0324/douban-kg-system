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

    def clear_runtime_caches(self):
        """释放仅对当前评估过程有意义的临时缓存。"""
        return

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

    # 偏好类型 → 兼容评分映射。真正的算法权重应优先使用 signal_weight。
    PREF_COMPAT_RATING = {
        "like": 3.5,
        "want_to_watch": 1.25,
    }
    PREF_SIGNAL_WEIGHT = {
        "like": 0.7,
        "want_to_watch": 0.25,
    }
    KG_SIGNAL_PRIORITY = {
        "rating": 0,
        "like": 1,
        "want_to_watch": 2,
    }

    @staticmethod
    def _rating_signal_weight(rating: float | int | None) -> float:
        try:
            return max(min(float(rating) / 5.0, 1.0), 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _build_rating_signal_row(self, row: dict) -> dict:
        rating = float(row["rating"])
        return {
            "mid": str(row["mid"]),
            "rating": rating,
            "signal_source": "rating",
            "signal_timestamp": row.get("rated_at"),
            "signal_weight": self._rating_signal_weight(rating),
        }

    def _build_pref_signal_row(self, mid: str, pref_type: str, timestamp=None) -> dict | None:
        signal_weight = self.PREF_SIGNAL_WEIGHT.get(pref_type)
        if signal_weight is None:
            return None
        return {
            "mid": str(mid),
            "rating": self.PREF_COMPAT_RATING.get(pref_type),
            "signal_source": pref_type,
            "signal_timestamp": timestamp,
            "signal_weight": float(signal_weight),
        }

    def get_user_positive_movies(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
    ) -> list[dict]:
        """获取用户正向电影（评分 >= threshold + 弱偏好信号）

        融合规则：
        - 评分 >= threshold 的电影直接加入，使用真实评分
        - like（仅在该电影没有任何真实评分时）→ 作为较强弱信号加入
        - want_to_watch（仅在该电影没有任何真实评分时）→ 作为弱兴趣信号加入
        - 只要该电影存在任何真实评分（哪怕低于 threshold），偏好信号都不得覆盖它
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT mid, rating, rated_at FROM user_movie_ratings "
                "WHERE user_id = %s "
                "ORDER BY rating DESC, rated_at DESC",
                (user_id,),
            )
            all_rating_rows = cursor.fetchall()

            cursor.execute(
                "SELECT mid, pref_type, created_at FROM user_movie_prefs WHERE user_id = %s",
                (user_id,),
            )
            pref_rows = cursor.fetchall()

        if exclude_mids:
            all_rating_rows = [row for row in all_rating_rows if str(row["mid"]) not in exclude_mids]

        rated_mid_set = {str(row["mid"]) for row in all_rating_rows}
        positive_rating_rows = [
            row for row in all_rating_rows if float(row["rating"]) >= threshold
        ]
        selected = [self._build_rating_signal_row(row) for row in positive_rating_rows]

        for pref in pref_rows:
            mid = str(pref["mid"])
            if exclude_mids and mid in exclude_mids:
                continue
            if mid in rated_mid_set:
                continue
            signal_row = self._build_pref_signal_row(mid, str(pref["pref_type"]), pref.get("created_at"))
            if signal_row:
                selected.append(signal_row)

        selected.sort(key=lambda row: str(row.get("signal_timestamp") or ""), reverse=True)
        selected.sort(
            key=lambda row: self.KG_SIGNAL_PRIORITY.get(str(row.get("signal_source")), 99)
        )
        selected.sort(key=lambda row: float(row.get("signal_weight") or 0.0), reverse=True)
        return selected

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
                "WHERE user_id = %s "
                "ORDER BY rating DESC, rated_at DESC",
                (user_id,),
            )
            all_rating_rows = cursor.fetchall()

            cursor.execute(
                "SELECT mid, pref_type, created_at FROM user_movie_prefs "
                "WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            pref_rows = cursor.fetchall()

        if exclude_mids:
            all_rating_rows = [row for row in all_rating_rows if str(row["mid"]) not in exclude_mids]

        positive_rating_rows = [
            row for row in all_rating_rows if float(row["rating"]) >= threshold
        ]
        rated_mid_set = {str(row["mid"]) for row in all_rating_rows}
        selected: list[dict] = []

        def _take_rows(rows: list[dict], limit: int) -> None:
            if limit <= 0:
                return
            for row in rows[:limit]:
                selected.append(row)

        _take_rows(
            [self._build_rating_signal_row(row) for row in positive_rating_rows],
            int(max_positive_ratings),
        )

        likes = []
        wishes = []
        for pref in pref_rows:
            mid = str(pref["mid"])
            if exclude_mids and mid in exclude_mids:
                continue
            if mid in rated_mid_set:
                continue
            pref_type = str(pref["pref_type"])
            signal_row = self._build_pref_signal_row(mid, pref_type, pref.get("created_at"))
            if signal_row is None:
                continue
            if pref_type == "like":
                likes.append(signal_row)
            elif pref_type == "want_to_watch":
                wishes.append(signal_row)

        _take_rows(likes, int(max_likes))
        _take_rows(wishes, int(max_wishes))

        selected.sort(key=lambda row: str(row.get("signal_timestamp") or ""), reverse=True)
        selected.sort(
            key=lambda row: self.KG_SIGNAL_PRIORITY.get(str(row.get("signal_source")), 99)
        )
        selected.sort(key=lambda row: float(row.get("signal_weight") or 0.0), reverse=True)
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
