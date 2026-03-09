"""
CFKG dataset and model artifact helpers.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

RELATION_NAMES = (
    "interact",
    "rev_interact",
    "has_genre",
    "genre_of",
    "directed_by",
    "directs",
    "acted_by",
    "acts_in",
)
RELATION_SCHEMA = {
    "interact": {"head_type": "User", "tail_type": "Movie"},
    "rev_interact": {"head_type": "Movie", "tail_type": "User"},
    "has_genre": {"head_type": "Movie", "tail_type": "Genre"},
    "genre_of": {"head_type": "Genre", "tail_type": "Movie"},
    "directed_by": {"head_type": "Movie", "tail_type": "Person"},
    "directs": {"head_type": "Person", "tail_type": "Movie"},
    "acted_by": {"head_type": "Movie", "tail_type": "Person"},
    "acts_in": {"head_type": "Person", "tail_type": "Movie"},
}
ENTITY_TYPE_ORDER = {
    "User": 0,
    "Movie": 1,
    "Person": 2,
    "Genre": 3,
}

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = BACKEND_ROOT / "tmp" / "cfkg" / "datasets"
DEFAULT_MODEL_ROOT = BACKEND_ROOT / "output" / "models" / "cfkg"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_ROOT / "latest.pt"
DEFAULT_RERANKER_ROOT = DEFAULT_MODEL_ROOT / "reranker"
DEFAULT_RERANKER_PATH = DEFAULT_RERANKER_ROOT / "latest.json"
LATEST_POINTER_NAME = "latest.txt"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_version() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def natural_sort_key(value: str) -> tuple[int, int | str]:
    text = str(value)
    if text.isdigit():
        return (0, int(text))
    return (1, text)


def make_entity_key(entity_type: str, raw_id: str) -> str:
    return f"{entity_type.lower()}:{raw_id}"


def relation_records() -> list[dict[str, int | str]]:
    return [
        {"relation_id": index, "relation_name": relation_name}
        for index, relation_name in enumerate(RELATION_NAMES)
    ]


def write_latest_pointer(root: Path, name: str) -> None:
    ensure_dir(root)
    (root / LATEST_POINTER_NAME).write_text(name, encoding="utf-8")


def resolve_latest_dataset_dir(
    dataset_dir: str | Path | None = None,
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
) -> Path:
    if dataset_dir is not None:
        path = Path(dataset_dir)
        return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()

    root = Path(dataset_root)
    root = root if root.is_absolute() else (BACKEND_ROOT / root).resolve()
    pointer = root / LATEST_POINTER_NAME
    if pointer.exists():
        latest_name = pointer.read_text(encoding="utf-8").strip()
        if latest_name:
            latest_dir = root / latest_name
            if latest_dir.exists():
                return latest_dir

    candidates = sorted([item for item in root.iterdir() if item.is_dir()]) if root.exists() else []
    if not candidates:
        raise FileNotFoundError(f"未找到 CFKG 数据集目录: {root}")
    return candidates[-1]


def resolve_model_path(model_path: str | Path | None = None) -> Path:
    if model_path is None:
        return DEFAULT_MODEL_PATH
    path = Path(model_path)
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


def resolve_reranker_path(reranker_path: str | Path | None = None) -> Path:
    if reranker_path is None:
        return DEFAULT_RERANKER_PATH
    path = Path(reranker_path)
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()
