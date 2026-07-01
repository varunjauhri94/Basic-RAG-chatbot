# Mutual Fund FAQ Assistant (Facts-Only RAG)

A facts-only FAQ assistant for mutual fund schemes, sourced exclusively from official Economic Times
factsheet pages. **Facts-only. No investment advice.**

## Live Demo
👉 **[https://et-markets-chatbot.streamlit.app/](https://et-markets-chatbot.streamlit.app/)**

See [`Docs/`](Docs/) for the full design: ProblemStatement, Architecture, implementation_plan,
edge_cases, eval.

## Status

Implemented: **Phases 0–3** (scaffolding, config/corpus, scrape, clean). Chunking onward is pending.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your GROQ_API_KEY (not needed for phases 0-3)
```

## Phases 0–3: scrape + clean (review before chunking)

```bash
# Scrape all 5 ET factsheets and clean them; writes reviewable output to data/cleaned/
python -m ingest.prepare

# Or run the steps individually:
python -m ingest.scrape              # all 5  -> data/raw/{scheme_id}.html (+ .meta.json)
python -m ingest.scrape --scheme 16280
python -m ingest.clean               # all raw -> data/cleaned/{scheme_id}.txt (+ .json)
```

**Review artifacts** (all gitignored under `data/`):
- `data/raw/{scheme_id}.html` — raw scrape snapshot + `{scheme_id}.meta.json` (url, fetch date, status, bytes)
- `data/cleaned/{scheme_id}.txt` — human-readable cleaned facts per scheme
- `data/cleaned/{scheme_id}.json` — structured fields (for the chunk step later)
- `data/cleaned/_review.md` — all 5 schemes in one file for quick review

The corpus (5 schemes) and tunables live in [`config/corpus.yaml`](config/corpus.yaml) and
[`config/pipeline.yaml`](config/pipeline.yaml).

## Disclaimer

Facts-only. No investment advice.
