"""
CFKG TransE-style embedding model.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError:  # pragma: no cover - lazy runtime dependency
    torch = None
    nn = None
    F = None

if TYPE_CHECKING:  # pragma: no cover
    import torch as torch_module


def require_torch():
    if torch is None or nn is None or F is None:
        raise RuntimeError("CFKG 训练和推理依赖 torch，请先安装 PyTorch")
    return torch, nn, F


class TransEModel(nn.Module if nn is not None else object):
    def __init__(self, entity_count: int, relation_count: int, embedding_dim: int):
        _, nn_module, _ = require_torch()
        super().__init__()
        self.entity_embeddings = nn_module.Embedding(entity_count, embedding_dim)
        self.relation_embeddings = nn_module.Embedding(relation_count, embedding_dim)
        nn_module.init.xavier_uniform_(self.entity_embeddings.weight)
        nn_module.init.xavier_uniform_(self.relation_embeddings.weight)

    def distance(self, head_ids, relation_ids, tail_ids):
        _, _, functional = require_torch()
        head = functional.normalize(self.entity_embeddings(head_ids), p=2, dim=-1)
        relation = functional.normalize(self.relation_embeddings(relation_ids), p=2, dim=-1)
        tail = functional.normalize(self.entity_embeddings(tail_ids), p=2, dim=-1)
        return (head + relation - tail).abs().sum(dim=-1)

    def score(self, head_ids, relation_ids, tail_ids):
        return -self.distance(head_ids, relation_ids, tail_ids)

