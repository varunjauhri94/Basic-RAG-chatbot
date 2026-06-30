# Problem Statement — Mutual Fund FAQ Assistant (Facts-Only Q&A)

> **Milestone 2 — RAG.** This document is the canonical context for the build. It defines a
> **facts-only** Retrieval-Augmented Generation assistant for mutual fund schemes, using **Groww**
> as the reference product context. The system answers only **objective, verifiable** questions,
> sourced **exclusively from official public sources** (AMC, AMFI, SEBI), and **never** gives
> investment advice. Every answer carries exactly one source link.

---

## 1. One-line summary

Build a lightweight **RAG assistant** that answers **factual** mutual fund questions from a curated
corpus of **official public documents**, returns **concise, source-backed** responses (≤ 3 sentences,
one citation, a "last updated" footer), and **refuses** any advisory or opinion-seeking query.

---

## 2. Objective

Design and implement a RAG-based assistant that:

- Answers **factual** queries about mutual fund schemes.
- Uses a **curated corpus** of official documents.
- Provides **concise, source-backed** responses.

The guiding principle is **accuracy over intelligence** — the assistant prioritizes verified,
citable facts over conversational range.

---

## 3. Target users

| Audience | Value |
|---|---|
| Retail investors | Quickly compare objective scheme facts (expense ratio, exit load, lock-in, etc.) |
| Customer support & content teams | Offload repetitive, factual mutual fund queries with consistent, cited answers |

---

## 4. Scope of work

### 4.1 Corpus definition (original brief)

- Select **one** Asset Management Company (AMC).
- Choose **3–5** mutual fund schemes with **category diversity** (e.g. large-cap, flexi-cap, ELSS).
- Collect **15–25 official public URLs**, including:
  - Scheme **factsheets**
  - **KIM** (Key Information Memorandum)
  - **SID** (Scheme Information Document)
  - AMC **FAQ / help** pages
  - **AMFI / SEBI** guidance pages
  - **Statement & tax document** download guides

### 4.1.1 Selected corpus (locked)

The build uses **Economic Times mutual fund factsheet pages** as the primary data source. Five
schemes are chosen for **category diversity** (ELSS, fund-of-funds, mid-cap, liquid/debt, flexi-cap):

| # | Scheme (Direct Plan – Growth) | AMC | Category | Factsheet URL |
|---|---|---|---|---|
| 1 | SBI ELSS Tax Saver Fund | SBI MF | ELSS (tax saver) | `https://economictimes.indiatimes.com/sbi-elss-tax-saver-fund-direct-plan/mffactsheet/schemeid-16244.cms` |
| 2 | ICICI Prudential BHARAT 22 FOF | ICICI Prudential MF | Fund of Funds | `https://economictimes.indiatimes.com/icici-prudential-bharat-22-fof-direct-plan/mffactsheet/schemeid-36693.cms` |
| 3 | HSBC Midcap Fund | HSBC MF | Mid Cap (equity) | `https://economictimes.indiatimes.com/hsbc-midcap-fund-direct-plan/mffactsheet/schemeid-16280.cms` |
| 4 | Groww Liquid Fund | Groww MF | Liquid (debt) | `https://economictimes.indiatimes.com/groww-liquid-fund-direct-plan/mffactsheet/schemeid-15583.cms` |
| 5 | Bank of India Flexi Cap Fund | Bank of India MF | Flexi Cap (equity) | `https://economictimes.indiatimes.com/bank-of-india-flexi-cap-fund-direct-plan/mffactsheet/schemeid-41018.cms` |

**Scrapability — verified (2026-06-28):** All five URLs return **HTTP 200** (~200–240 KB each) and
render the key facts **server-side in static HTML** — confirmed present without JavaScript:
expense ratio, exit load, minimum investment, riskometer/risk grade, benchmark, fund size (AUM),
fund manager, launch date, return-since-launch, and NAV. A standard
`requests` + `BeautifulSoup` (or readability) scraper is sufficient; **no headless browser required**.

> **Deviations from the original brief (intentional):**
> 1. **Source type** — ET factsheets are an **aggregator** of AMC data, whereas §5 originally
>    restricts sources to AMC/AMFI/SEBI only. ET is treated as the chosen, authoritative-enough
>    corpus for this milestone; where a precise legal/regulatory figure is needed, link back to the
>    underlying AMC factsheet/SID.
> 2. **AMC spread** — the five schemes span **five different AMCs** (not a single AMC), chosen to
>    maximise category diversity across ELSS, FoF, mid-cap, liquid, and flexi-cap.

### 4.2 FAQ assistant requirements

The assistant must answer **facts-only** queries, such as:

- Expense ratio of a scheme
- Exit load details
- Minimum SIP amount
- ELSS lock-in period
- Riskometer classification
- Benchmark index
- Process to download statements or capital gains reports

Each response must:

- Be limited to a **maximum of 3 sentences**.
- Include **exactly one** citation link.
- Include the footer: **"Last updated from sources: &lt;date&gt;"**

### 4.3 Refusal handling

The assistant must **refuse** non-factual or advisory queries, e.g.:

- "Should I invest in this fund?"
- "Which fund is better?"

Refusal responses should:

- Be **polite** and clearly worded.
- Reinforce the **facts-only** limitation.
- Provide a relevant **educational link** (e.g. AMFI or SEBI resource).

### 4.4 User interface (minimal)

A simple interface that includes:

- A **welcome message**.
- **Three example questions**.
- A visible disclaimer: **"Facts-only. No investment advice."**

---

## 5. Constraints

### Data and sources
- Primary corpus for this build: the **Economic Times mutual fund factsheet pages** listed in
  §4.1.1 (an authoritative public source republishing AMC scheme data).
- For regulatory/legal precision, prefer the underlying **AMC / AMFI / SEBI** documents
  (factsheet, KIM, SID) and cite those.
- **Do not** use third-party blogs or opinion/aggregator sites beyond the locked corpus above.

### Privacy and security
Do **not** collect, store, or process:
- PAN or Aadhaar numbers
- Account numbers
- OTPs
- Email addresses or phone numbers

### Content restrictions
- **No** investment advice or recommendations.
- **No** performance comparisons or return calculations.
- For performance-related queries, provide a link to the **official factsheet only**.

### Transparency
- Responses must be **short, factual, and verifiable**.
- Every answer must include a **source link** and a **last updated date**.

---

## 6. Expected deliverables

- **README document** covering:
  - Setup instructions
  - Selected AMC and schemes
  - Architecture overview (RAG approach)
  - Known limitations
- **Disclaimer snippet:** "Facts-only. No investment advice."

---

## 7. Success criteria

- Accurate retrieval of factual mutual fund information.
- Strict adherence to **facts-only** responses.
- Consistent inclusion of valid source citations.
- Proper **refusal** of advisory queries.
- Clean, minimal, and user-friendly interface.

---

## 8. Summary

The goal is to build a **trustworthy, transparent, and compliant** mutual fund FAQ assistant that
prioritizes **accuracy over intelligence**. The system should ensure users receive only verified,
source-backed financial information — without any advisory bias or speculative content.
