# RAG Evaluation Quick Reference

Dataset version `2.0.0` is declared in `evaluation/dataset_manifest.json`. It contains six supported synthetic retrieval cases plus unrelated, unsupported-equipment, asset-mismatch, prompt-injection, and prohibited state-change cases.

```powershell
python -m evaluation.run_evaluation --mode deterministic `
  --output reports/rag_evaluation.json

python -m evaluation.run_evaluation --backend configured-qdrant --mode deterministic `
  --output reports/rag_configured_evaluation.json
```

An output path produces machine-readable JSON and a sibling Markdown report. Metrics include Recall@1/3/5, MRR, filter accuracy, no-answer accuracy, unsupported-equipment rejection, asset-mismatch detection, safety coverage, citation validity/coverage, fallback and response-mode rates, and average/p50/p95 latency. Retrieval comparisons cover dense-only, sparse-only, hybrid, and hybrid plus reranking.

The in-memory backend uses hash embeddings and a lexical reranker fixture. It validates determinism and contracts only. Configured Qdrant uses the production embedding and cross-encoder path but still needs an approved representative corpus and human claim labels before any real-world accuracy or safety claim.

See [the detailed evaluation design](RAG_LLM_EVALUATION.md) for modes, limitations, and the human acceptance rubric.
