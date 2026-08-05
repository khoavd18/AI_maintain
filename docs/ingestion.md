# RAG Document Ingestion

`src/rag/document_loader.py` is the validation boundary for the controlled CSV corpus. It accepts canonical fields (`document_id`, `document_type`, `content`) and the existing legacy aliases (`doc_id`, `doc_type`, `clean_text`), but normalizes both into one `MaintenanceDocument` model.

Required logical values are document ID, title, document type, supported asset type, source, content, version, effective date, and language. The loader reports row number, document ID, field, stable error code, and public-safe message for empty fields, invalid ISO dates, invalid versions/language tags, duplicate IDs, unsupported assets, prompt overrides, tool calls, shell commands, and state-changing SQL-like text. `load_documents()` rejects the whole batch if any row is invalid; it never silently drops a bad row.

Chunking is structure-aware for Vietnamese safety, symptom, cause, inspection, treatment, preventive, warning, operating-condition, and reference headings. Continuation chunks repeat the heading. BLAKE2b IDs depend on normalized meaningful content and remain stable across identical runs.

Indexing is operator-only:

```powershell
# Non-destructive added/updated upsert
python -m src.rag.index_documents

# Canonical synchronization; delete only reported obsolete points
python -m src.rag.index_documents --replace

# Explicit destructive collection recreation
python -m src.rag.index_documents --recreate
```

The JSON report includes total/valid/invalid records, validation errors, chunks, added/updated/unchanged/removed/obsolete/active points, vector dimensions, and indexing mode. The API never indexes at startup.
