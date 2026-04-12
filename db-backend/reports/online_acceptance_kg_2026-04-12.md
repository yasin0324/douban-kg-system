# KG 线上链路验收

- 生成时间: 2026-04-12T15:07:54.118036
- 总场景数: 45
- 通过: 33
- 失败: 12

## 失败场景
- personal / cohort=light / algorithm=kg_path / status=504 / details={"error": "http 504", "top3": [], "cold_start": null, "total": null}
- personal / cohort=heavy / algorithm=kg_embed / status=504 / details={"error": "http 504", "top3": [], "cold_start": null, "total": null}
- personal / cohort=heavy / algorithm=kg_path / status=504 / details={"error": "http 504", "top3": [], "cold_start": null, "total": null}
- personal_default / cohort=heavy / algorithm=cfkg / status=504 / details={"compare_same_top10": false, "top3": []}
- personal_cold / cohort=cold / algorithm=cfkg / status=503 / details={"top3": [], "cold_start": null, "total": null}
- personal_cold / cohort=cold / algorithm=kg_path / status=503 / details={"top3": [], "cold_start": null, "total": null}
- explain_top1 / cohort=heavy / algorithm=cfkg / status=200 / details={"error": "explain too slow: 87.31s", "meta": {"has_graph_evidence": true, "cold_start": false}, "target_mid": "35376457"}
- explain_top5 / cohort=heavy / algorithm=cfkg / status=200 / details={"error": "explain too slow: 25.11s", "meta": {"has_graph_evidence": true, "cold_start": false}, "target_mid": "30337388"}
- explain_top1 / cohort=heavy / algorithm=kg_embed / status=200 / details={"error": "explain too slow: 24.96s", "meta": {"has_graph_evidence": true, "cold_start": false}, "target_mid": "35376457"}
- explain_top5 / cohort=heavy / algorithm=kg_embed / status=200 / details={"error": "explain too slow: 17.84s", "meta": {"has_graph_evidence": true, "cold_start": false}, "target_mid": "30337388"}
- personal_after_rating_add / cohort=light / algorithm=kg_path / status=504 / details={"top3": [], "total": null}
- personal_after_preference_add / cohort=light / algorithm=kg_path / status=504 / details={"top3": [], "total": null}