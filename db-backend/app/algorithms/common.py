"""
推荐算法公共工具
"""


def dedupe_preserve_order(values):
    if not values:
        return []

    seen = set()
    items = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def run_query(session, query: str, timeout_ms: int | None = None, **params):
    if timeout_ms:
        timeout_seconds = max(timeout_ms, 100) / 1000
        try:
            with session.begin_transaction(timeout=timeout_seconds) as tx:
                return list(tx.run(query, **params))
        except TypeError:
            pass
    return list(session.run(query, **params))
