# Evaluation Plan — Mutual Fund FAQ Assistant (Facts-Only RAG)

> How to **evaluate each phase** of [implementation_plan.md](implementation_plan.md). Every phase has:
> **What we measure · How (method) · Metric · Pass criteria**. These extend the per-phase Definition
> of Done into concrete, repeatable checks. Stack: **Groq** (gate + generation), **BGE** (local
> embeddings), **ChromaDB** (vector store).
>
> Two layers of evaluation:
> - **Component evals** (Phases 0–10): unit/integration checks per module.
> - **System eval** (Phase 11): an end-to-end gold Q&A set scored on retrieval + answer + refusal.

---

## Eval assets (build once, reuse)

| Asset | Path | Purpose |
|---|---|---|
| Gold Q&A set | `tests/eval_set.yaml` | ~20 items: `{question, scheme, expected_fact, expected_source_url, type}` where `type ∈ {factual, advisory, performance, out_of_scope}` |
| Fixture HTML | `tests/fixtures/{scheme_id}.html` | Frozen ET snapshots so scrape/clean/chunk evals are deterministic |
| Refusal probe set | `tests/refusal_set.yaml` | Advisory / performance / out-of-scope / jailbreak prompts that **must** refuse |

---

## Phase 0 — Scaffolding & Environment

| | |
|---|---|
| **Measure** | Repo installs and imports cleanly; the single secret is wired |
| **Method** | `pip install -r requirements.txt`; `python -c "import groq, chromadb, bs4, sentence_transformers"`; load `.env` and assert `GROQ_API_KEY` present |
| **Metric** | Install exit code; import success; key-present boolean |
| **Pass** | Install succeeds, imports clean, missing `GROQ_API_KEY` fails fast with a clear message |

---

## Phase 1 — Config & Corpus

| | |
|---|---|
| **Measure** | Config integrity and corpus correctness |
| **Method** | `config.load()`; assert exactly **5 schemes**; every `url` matches `economictimes.indiatimes.com/...schemeid-*`; schemas (`Source/Chunk/GateResult/Answer`) instantiate |
| **Metric** | scheme count; URL-pattern pass rate; schema import success |
| **Pass** | 5/5 schemes, 5/5 valid ET URLs, all Pydantic models construct; malformed config raises a named error |

---

## Phase 2 — Scrape

| | |
|---|---|
| **Measure** | All 5 ET pages fetch and snapshot; non-HTML rejected |
| **Method** | Run scraper on the 5 URLs (or fixtures in CI); assert HTTP 200, body size in range, `fetched_at` captured; feed a non-`text/html` response and assert rejection |
| **Metric** | fetch success rate (5/5); size sanity; reject-on-non-HTML boolean |
| **Pass** | 5/5 snapshots saved with dates; non-HTML/PDF responses rejected with a clear error; a 5xx isolates that scheme without corrupting the index |

---

## Phase 3 — Clean

| | |
|---|---|
| **Measure** | Noise removed, own facts retained, no cross-scheme contamination |
| **Method** | Run `clean()` on each fixture; assert output **contains** that scheme's fact labels and **excludes** "FEATURED FUNDS", ticker strings, and the other 4 scheme names |
| **Metric** | fact-label retention %; noise-leakage count (target 0); other-scheme-name count (target 0) |
| **Pass** | ≥ 95% of expected fact labels retained; **0** noise/ticker/other-scheme leaks |

---

## Phase 4 — Chunk

| | |
|---|---|
| **Measure** | Sectioning, metadata completeness, idempotency |
| **Method** | Golden-file the chunk set per scheme; assert all 7 metadata fields present; re-run and diff `chunk_id`s |
| **Metric** | metadata-completeness %; chunk-id stability (must be 100% across runs); label–value co-location check |
| **Pass** | 100% chunks carry all metadata; identical `chunk_id`s across runs; no label split from its value |

---

## Phase 5 — Embeddings + Vector Store + build_index

| | |
|---|---|
| **Measure** | Index builds, is idempotent, query-prefix applied; manifest correct |
| **Method** | `build_index`; count chunks in Chroma; re-run and assert no duplication; unit-test `embed(is_query=True)` prepends the BGE instruction; verify `manifest.json` |
| **Metric** | total chunk count; duplication delta on re-run (must be 0); query-prefix-applied boolean; manifest fields present |
| **Pass** | All 5 schemes indexed; re-run adds 0 duplicates; query prefix verified; manifest lists per-scheme counts, model, build time |

---

## Phase 6 — Retrieval

| | |
|---|---|
| **Measure** | Right chunk retrieved; floor and scheme filter work |
| **Method** | For each gold factual Q, run retrieval; check the top hit's scheme/section; run a nonsense query and assert it falls below the floor; run a generic query and assert the scheme filter prevents leakage |
| **Metric** | **Recall@4** (gold chunk in top-4); **top-1 scheme accuracy**; floor false-pass rate; cross-scheme leak count |
| **Pass** | Recall@4 ≥ 0.90; top-1 scheme accuracy ≥ 0.90; nonsense queries refused by the floor; **0** cross-scheme leaks |

---

## Phase 7 — Guardrails (PII Scrubber + Intent Gate)

| | |
|---|---|
| **Measure** | PII removed; intent classified correctly |
| **Method** | PII: table of inputs with PAN/Aadhaar/phone/email/account → assert all redacted before any log/LLM call. Gate: run `refusal_set.yaml` + factual probes through the Groq gate |
| **Metric** | PII redaction recall (target 100%); **gate accuracy** per class; advisory/performance **leak rate** (must be 0) |
| **Pass** | 100% PII redacted; gate accuracy ≥ 0.90 overall; **0** advisory/performance queries classified as `factual`; malformed gate JSON fails closed (→ refusal) |

---

## Phase 8 — Generation (Facts-Only Contract)

| | |
|---|---|
| **Measure** | Output obeys the contract and is grounded |
| **Method** | With mocked + live Groq, feed retrieved chunks; assert valid `Answer` JSON, ≤ 3 sentences, `citation_url` ∈ provided sources; feed context **lacking** the fact and assert `answer_type="refusal"` |
| **Metric** | schema-valid rate; ≤3-sentence rate; citation-in-set rate; **groundedness** (every fact traceable to a chunk); refuse-when-absent rate |
| **Pass** | 100% schema-valid after retry; 100% ≤3 sentences; 100% citation-in-set; refuses when the fact is absent; invalid JSON recovers via one retry then refuses |

---

## Phase 9 — Orchestrator (Wire + Validate)

| | |
|---|---|
| **Measure** | End-to-end path + independent validation downgrade |
| **Method** | `python -m app.orchestrator --query ...` across factual + each refusal type; inject a forced hallucinated citation and assert downgrade; remove `as_of_date` and assert downgrade |
| **Metric** | correct-shape rate (answer vs. refusal) per query type; downgrade-on-violation rate; footer-format correctness |
| **Pass** | Correct shape for all gold + refusal probes; **100%** of contract violations downgrade to refusal; footer reads `Last updated from sources: <date>` |

---

## Phase 10 — UI

| | |
|---|---|
| **Measure** | UI meets the problem-statement requirements; no persistence |
| **Method** | Launch Streamlit; verify disclaimer always visible, welcome + 3 examples present; run an example (cited answer), an advisory (refusal), and an error path; refresh and confirm no history |
| **Metric** | required-elements checklist; refusal renders correctly; no-persistence boolean |
| **Pass** | Disclaimer on every state; examples return cited answers; advisory shows refusal; nothing persists across refresh; no PII captured |

---

## Phase 11 — System Eval Harness (the core eval)

| | |
|---|---|
| **Measure** | End-to-end factual accuracy, citation correctness, refusal correctness |
| **Method** | Run `tests/eval_set.yaml` + `tests/refusal_set.yaml` through the orchestrator; auto-score each item |
| **Metrics** | • **Answer accuracy** — answered facts that match `expected_fact`  • **Citation accuracy** — `citation_url == expected_source_url`  • **Refusal precision/recall** — advisory/performance/out-of-scope correctly refused  • **False-answer rate** — should-refuse items that got a factual answer (the critical safety metric) |
| **Pass** | Answer accuracy ≥ 0.90; citation accuracy ≥ 0.95; refusal recall = **1.0** (every should-refuse refuses); **false-answer rate = 0**; harness is CI-runnable and prints a per-item report |

> **The non-negotiable number is false-answer rate = 0.** A wrong refusal is acceptable; an unsourced
> or advisory answer is not ("accuracy over intelligence").

---

## Phase 12 — Observability & Hardening

| | |
|---|---|
| **Measure** | Logs are useful and PII-free; failures degrade gracefully; README is sufficient |
| **Method** | Inspect logs after an eval run for PII (must be none) and presence of intent/similarity/refusal-reason/latency/citation/tokens; simulate Groq 429/5xx and BGE load failure; have a fresh user follow the README |
| **Metric** | PII-in-logs count (must be 0); log-field completeness; graceful-degradation boolean; README "cold start to running UI" success |
| **Pass** | **0** PII in logs; all required fields logged; 429/5xx and model-load failures show graceful messages (no stack traces); a new user can install → build index → run UI from the README alone |

---

## Rollup — Project Acceptance (maps to ProblemStatement §7)

| Success criterion | Evidenced by |
|---|---|
| Accurate retrieval of factual MF info | Phase 6 (Recall@4) + Phase 11 (answer accuracy) |
| Strict facts-only responses | Phase 8 (≤3 sentences, grounded) + Phase 9 (validation) |
| Consistent valid citation + last-updated footer | Phase 8 (citation-in-set) + Phase 9 (footer) + Phase 11 (citation accuracy) |
| Proper refusal of advisory/performance/out-of-scope | Phase 7 (gate) + Phase 11 (refusal recall = 1.0, false-answer = 0) |
| Clean, minimal UI with disclaimer | Phase 10 checklist |

---

## Related Documents

- [implementation_plan.md](implementation_plan.md) — the phases these evals score.
- [edge_cases.md](edge_cases.md) — corner scenarios; many become negative test cases here.
- [Architecture.md](Architecture.md) · [ProblemStatement.md](ProblemStatement.md)
