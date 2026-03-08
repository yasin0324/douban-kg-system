"""
CFKG training helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import random
from statistics import mean
from typing import Any

from app.algorithms.cfkg.artifacts import (
    DEFAULT_MODEL_ROOT,
    RELATION_SCHEMA,
    ensure_dir,
    resolve_model_path,
)
from app.algorithms.cfkg.dataset import ExportedCFKGDataset, load_exported_dataset
from app.algorithms.cfkg.model import TransEModel, require_torch
from tqdm.auto import tqdm


@dataclass
class TrainingConfig:
    dataset_dir: str | None = None
    output_dir: str | Path = DEFAULT_MODEL_ROOT
    embedding_dim: int = 64
    epochs: int = 12
    batch_size: int = 256
    learning_rate: float = 1e-3
    margin: float = 1.0
    hard_negative_weight: float = 0.35
    seed: int = 20260308
    device: str | None = None
    show_progress: bool = False


DEFAULT_EXPERIMENT_GRID = {
    "embedding_dim": (48, 64),
    "epochs": (6, 10),
    "learning_rate": (1e-3, 5e-4),
    "hard_negative_weight": (0.35, 0.6),
}


def default_experiment_configs(base_config: TrainingConfig) -> list[TrainingConfig]:
    configs = []
    for embedding_dim in DEFAULT_EXPERIMENT_GRID["embedding_dim"]:
        for epochs in DEFAULT_EXPERIMENT_GRID["epochs"]:
            for learning_rate in DEFAULT_EXPERIMENT_GRID["learning_rate"]:
                for hard_negative_weight in DEFAULT_EXPERIMENT_GRID["hard_negative_weight"]:
                    configs.append(
                        TrainingConfig(
                            dataset_dir=base_config.dataset_dir,
                            output_dir=Path(base_config.output_dir) / (
                                f"ed{embedding_dim}-ep{epochs}-lr{learning_rate:g}-hn{hard_negative_weight:g}"
                            ),
                            embedding_dim=embedding_dim,
                            epochs=epochs,
                            batch_size=base_config.batch_size,
                            learning_rate=learning_rate,
                            margin=base_config.margin,
                            hard_negative_weight=hard_negative_weight,
                            seed=base_config.seed,
                            device=base_config.device,
                            show_progress=base_config.show_progress,
                        )
                    )
    return configs


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[3] / path).resolve()
    return ensure_dir(path)


def choose_device(requested: str | None = None) -> str:
    torch_module, _, _ = require_torch()
    if requested:
        return requested
    if torch_module.backends.mps.is_available():
        return "mps"
    if torch_module.cuda.is_available():
        return "cuda"
    return "cpu"


def set_random_seed(seed: int) -> None:
    torch_module, _, _ = require_torch()
    random.seed(seed)
    torch_module.manual_seed(seed)
    if torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)


def _iter_batches(items: list[tuple[int, int, int]], batch_size: int):
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


def _sample_negative_movie(
    dataset: ExportedCFKGDataset,
    user_entity_id: int,
    excluded_movie_id: int,
    rng: random.Random,
) -> int:
    explicit_pair_candidates = dataset.interaction_explicit_negative_pools.get(
        (user_entity_id, excluded_movie_id),
        [],
    )
    if explicit_pair_candidates:
        return rng.choice(explicit_pair_candidates)

    semantic_pair_candidates = dataset.interaction_semantic_negative_pools.get(
        (user_entity_id, excluded_movie_id),
        [],
    )
    if semantic_pair_candidates:
        return rng.choice(semantic_pair_candidates)

    explicit_negatives = sorted(dataset.user_negative_items.get(user_entity_id, set()))
    if explicit_negatives:
        return rng.choice(explicit_negatives)

    positives = dataset.user_positive_items.get(user_entity_id, set())
    candidates = [
        movie_entity_id
        for movie_entity_id in dataset.movie_entity_ids
        if movie_entity_id != excluded_movie_id and movie_entity_id not in positives
    ]
    if not candidates:
        return excluded_movie_id
    return rng.choice(candidates)


def _sample_negative_triple(
    triple: tuple[int, int, int],
    dataset: ExportedCFKGDataset,
    rng: random.Random,
) -> tuple[int, int, int]:
    head_id, relation_id, tail_id = triple
    relation_name = dataset.relation_id_to_name[relation_id]
    schema = RELATION_SCHEMA[relation_name]

    if relation_name == "interact":
        return head_id, relation_id, _sample_negative_movie(dataset, head_id, tail_id, rng)

    corrupt_head = rng.random() < 0.5
    if corrupt_head:
        candidates = dataset.entity_ids_by_type[schema["head_type"]]
        replacement = rng.choice(candidates)
        while replacement == head_id and len(candidates) > 1:
            replacement = rng.choice(candidates)
        return replacement, relation_id, tail_id

    candidates = dataset.entity_ids_by_type[schema["tail_type"]]
    replacement = rng.choice(candidates)
    while replacement == tail_id and len(candidates) > 1:
        replacement = rng.choice(candidates)
    return head_id, relation_id, replacement


def _sample_hard_negative_pairs(
    interact_triples: list[tuple[int, int, int]],
    dataset: ExportedCFKGDataset,
    rng: random.Random,
) -> list[tuple[int, int, int]]:
    hard_pairs = []
    for head_id, relation_id, tail_id in interact_triples:
        negative_movie_id = _sample_negative_movie(dataset, head_id, tail_id, rng)
        if negative_movie_id == tail_id:
            continue
        hard_pairs.append((head_id, relation_id, negative_movie_id))
    return hard_pairs


def _write_sidecar_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def _artifact_payload(
    model: TransEModel,
    dataset: ExportedCFKGDataset,
    config: TrainingConfig,
    device_name: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "embedding_dim": config.embedding_dim,
            "epochs": config.epochs,
            "batch_size": config.batch_size,
            "learning_rate": config.learning_rate,
            "margin": config.margin,
            "hard_negative_weight": config.hard_negative_weight,
            "seed": config.seed,
            "device": device_name,
            "entity_count": len(dataset.entities),
            "relation_count": len(dataset.relations),
            "dataset_dir": str(dataset.dataset_dir),
        },
        "model_state": model.state_dict(),
        "entity_key_to_id": dataset.entity_key_to_id,
        "entity_id_to_key": dataset.entity_id_to_key,
        "entity_id_to_type": dataset.entity_id_to_type,
        "entity_id_to_label": dataset.entity_id_to_label,
        "relation_name_to_id": dataset.relation_name_to_id,
        "relation_id_to_name": dataset.relation_id_to_name,
        "movie_entity_ids": dataset.movie_entity_ids,
        "movie_entity_id_to_mid": dataset.movie_entity_id_to_mid,
        "user_entity_to_user_id": dataset.user_entity_to_user_id,
        "metrics": metrics,
    }


def train_cfkg_model(config: TrainingConfig) -> dict[str, Any]:
    torch_module, _, _ = require_torch()
    set_random_seed(config.seed)
    rng = random.Random(config.seed)

    dataset = load_exported_dataset(config.dataset_dir)
    device_name = choose_device(config.device)
    device = torch_module.device(device_name)

    model = TransEModel(
        entity_count=len(dataset.entities),
        relation_count=len(dataset.relations),
        embedding_dim=config.embedding_dim,
    ).to(device)
    optimizer = torch_module.optim.Adam(model.parameters(), lr=config.learning_rate)
    train_triples = list(dataset.train_triples)
    interact_relation_id = dataset.relation_name_to_id["interact"]
    total_batches = math.ceil(len(train_triples) / max(config.batch_size, 1))

    epoch_metrics = []
    epoch_iterator = range(config.epochs)
    if config.show_progress:
        epoch_iterator = tqdm(
            epoch_iterator,
            total=config.epochs,
            desc="CFKG epochs",
            unit="epoch",
            dynamic_ncols=True,
        )

    for epoch_index in epoch_iterator:
        rng.shuffle(train_triples)
        batch_losses = []
        interact_batch_losses = []
        batch_iterator = _iter_batches(train_triples, config.batch_size)
        if config.show_progress:
            batch_iterator = tqdm(
                batch_iterator,
                total=total_batches,
                desc=f"epoch {epoch_index + 1}/{config.epochs}",
                unit="batch",
                leave=False,
                dynamic_ncols=True,
            )

        for batch in batch_iterator:
            negative_batch = [_sample_negative_triple(item, dataset, rng) for item in batch]
            positive_tensors = [
                torch_module.tensor([item[idx] for item in batch], dtype=torch_module.long, device=device)
                for idx in range(3)
            ]
            negative_tensors = [
                torch_module.tensor([item[idx] for item in negative_batch], dtype=torch_module.long, device=device)
                for idx in range(3)
            ]
            positive_distance = model.distance(*positive_tensors)
            negative_distance = model.distance(*negative_tensors)
            loss = torch_module.relu(
                config.margin + positive_distance - negative_distance
            ).mean()

            interact_batch = [item for item in batch if item[1] == interact_relation_id]
            if interact_batch:
                hard_negative_pairs = _sample_hard_negative_pairs(interact_batch, dataset, rng)
                if hard_negative_pairs:
                    positive_interact_tensors = [
                        torch_module.tensor([item[idx] for item in interact_batch], dtype=torch_module.long, device=device)
                        for idx in range(3)
                    ]
                    hard_negative_tensors = [
                        torch_module.tensor([item[idx] for item in hard_negative_pairs], dtype=torch_module.long, device=device)
                        for idx in range(3)
                    ]
                    positive_interact_distance = model.distance(*positive_interact_tensors)
                    hard_negative_distance = model.distance(*hard_negative_tensors)
                    interact_loss = torch_module.relu(
                        config.margin + positive_interact_distance - hard_negative_distance
                    ).mean()
                    loss = loss + config.hard_negative_weight * interact_loss
                    interact_batch_losses.append(float(interact_loss.detach().cpu()))

            optimizer.zero_grad()
            loss.backward()
            torch_module.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            loss_value = float(loss.detach().cpu())
            batch_losses.append(loss_value)
            if config.show_progress:
                batch_iterator.set_postfix({
                    "loss": f"{loss_value:.4f}",
                    "hard": (
                        f"{interact_batch_losses[-1]:.4f}"
                        if interact_batch_losses
                        else "-"
                    ),
                })

        epoch_summary = {
            "epoch": epoch_index + 1,
            "loss": round(mean(batch_losses), 6) if batch_losses else 0.0,
            "interact_loss": round(mean(interact_batch_losses), 6) if interact_batch_losses else 0.0,
        }
        epoch_metrics.append(epoch_summary)
        if config.show_progress:
            epoch_iterator.set_postfix({
                "loss": f"{epoch_summary['loss']:.4f}",
                "hard": f"{epoch_summary['interact_loss']:.4f}",
                "batches": total_batches,
            })

    output_dir = _resolve_output_dir(config.output_dir)
    latest_model_path = resolve_model_path(output_dir / "latest.pt")
    metrics = {
        "epochs": epoch_metrics,
        "final_loss": epoch_metrics[-1]["loss"] if epoch_metrics else 0.0,
        "train_triple_count": len(train_triples),
        "holdout_user_count": dataset.metadata.get("holdout_user_count", 0),
    }
    artifact = _artifact_payload(model, dataset, config, device_name, metrics)
    torch_module.save(artifact, latest_model_path)

    _write_sidecar_json(output_dir / "config.json", artifact["config"])
    _write_sidecar_json(output_dir / "metrics.json", metrics)
    _write_sidecar_json(output_dir / "entity_index.json", {
        entity.entity_key: entity.entity_id
        for entity in dataset.entities
    })
    _write_sidecar_json(output_dir / "relation_index.json", dataset.relation_name_to_id)

    return {
        "model_path": str(latest_model_path),
        "output_dir": str(output_dir),
        "device": device_name,
        "metrics": metrics,
        "dataset_dir": str(dataset.dataset_dir),
    }
