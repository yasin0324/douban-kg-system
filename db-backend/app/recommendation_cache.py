"""
进程内推荐缓存。
"""
from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Hashable

from cachetools import TTLCache

from app.config import settings

_LOCK = RLock()
_USER_PROFILE_CACHE: TTLCache[int, dict[str, Any]] = TTLCache(
    maxsize=settings.RECOMMEND_USER_PROFILE_CACHE_MAXSIZE,
    ttl=settings.RECOMMEND_USER_PROFILE_CACHE_TTL_SECONDS,
)
_MOVIE_BRIEF_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(
    maxsize=settings.RECOMMEND_MOVIE_CACHE_MAXSIZE,
    ttl=settings.RECOMMEND_MOVIE_CACHE_TTL_SECONDS,
)
_MOVIE_GRAPH_PROFILE_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(
    maxsize=settings.RECOMMEND_MOVIE_CACHE_MAXSIZE,
    ttl=settings.RECOMMEND_MOVIE_CACHE_TTL_SECONDS,
)


def _dedupe_preserve_order(values):
    if not values:
        return []

    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _clone(value: Any) -> Any:
    return deepcopy(value)


def _get_many(
    cache: TTLCache,
    keys: list[Hashable],
) -> tuple[dict[Hashable, Any], list[Hashable]]:
    hits: dict[Hashable, Any] = {}
    missing: list[Hashable] = []
    with _LOCK:
        for key in _dedupe_preserve_order(keys):
            if key in cache:
                hits[key] = _clone(cache[key])
            else:
                missing.append(key)
    return hits, missing


def _set_many(cache: TTLCache, values: dict[Hashable, Any]) -> None:
    if not values:
        return

    with _LOCK:
        for key, value in values.items():
            cache[key] = _clone(value)


def get_user_profile_cache(user_id: int) -> dict[str, Any] | None:
    with _LOCK:
        cached = _USER_PROFILE_CACHE.get(int(user_id))
        return _clone(cached) if cached is not None else None


def set_user_profile_cache(user_id: int, profile: dict[str, Any]) -> None:
    if profile is None:
        return

    with _LOCK:
        _USER_PROFILE_CACHE[int(user_id)] = _clone(profile)


def invalidate_user_profile_cache(user_id: int) -> None:
    with _LOCK:
        _USER_PROFILE_CACHE.pop(int(user_id), None)


def get_movie_brief_cache(movie_ids: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    hits, missing = _get_many(_MOVIE_BRIEF_CACHE, [str(movie_id) for movie_id in movie_ids or []])
    return hits, [str(movie_id) for movie_id in missing]


def set_movie_brief_cache(brief_map: dict[str, dict[str, Any]]) -> None:
    _set_many(_MOVIE_BRIEF_CACHE, {str(movie_id): value for movie_id, value in (brief_map or {}).items()})


def get_movie_graph_profile_cache(
    movie_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    hits, missing = _get_many(_MOVIE_GRAPH_PROFILE_CACHE, [str(movie_id) for movie_id in movie_ids or []])
    return hits, [str(movie_id) for movie_id in missing]


def set_movie_graph_profile_cache(profile_map: dict[str, dict[str, Any]]) -> None:
    _set_many(
        _MOVIE_GRAPH_PROFILE_CACHE,
        {str(movie_id): value for movie_id, value in (profile_map or {}).items()},
    )


def clear_all_recommendation_caches() -> None:
    with _LOCK:
        _USER_PROFILE_CACHE.clear()
        _MOVIE_BRIEF_CACHE.clear()
        _MOVIE_GRAPH_PROFILE_CACHE.clear()
