# LLM Generation And Citations

Generation remains operator-configurable. Local Docker enables Ollama by default; `LLM_ENABLED=false` keeps a deterministic response composed only from retrieved technical evidence plus clearly labeled asset/analytics context. Ollama and OpenAI-compatible Chat Completions share one provider-neutral request, bounded timeout/retry/context/output controls, and no tools. A bounded social branch handles greetings, identity, capability, thanks, and farewell without retrieval; all technical guidance still requires RAG evidence and citations.

For every Ollama structured-generation request, the non-streaming chat payload sets `think: false`, passes the request JSON Schema through `format`, and preserves the configured output-token limit. The application does not consume reasoning traces: blank content and `done_reason="length"` are provider failures, and thinking text is never parsed, cited, logged, or returned.

Generated output must match `GroundedLLMAnswer`: unknown fields are forbidden, claims are non-empty, normal answers contain at least one recommended check, insufficient evidence requires escalation, and visible content must pass Vietnamese-language and prompt-leak checks.

Every summary, possible cause, check, and source-derived warning carries one or more response-local IDs (`S1`, `S2`, …). Validation requires:

- every ID to exist in the exact supplied context;
- every claim to have citations;
- the top-level citation set to equal the claim-level union;
- a conservative lexical-support check between each claim and its cited chunks.

Lexical overlap catches obvious citation mismatches but is not semantic entailment or technical validation. Any malformed JSON, wrong language, invalid/missing citation, weak support, timeout, or provider failure discards generated output and uses the deterministic grounded fallback.
