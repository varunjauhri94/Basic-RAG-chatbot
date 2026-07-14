"""Phase 10 — Streamlit chat UI (Architecture §11, ProblemStatement §4.4).

Requirements met:
  - Visible disclaimer: "Facts-only. No investment advice."
  - Welcome message
  - 3 example questions (clickable)
  - Auto-expanding textarea input
  - Answer rendered with citation link + "Last updated" footer
  - No login, no history persistence, no PII capture
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

# ensure project root is on the path when running from any directory
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# (Commented out for production to preserve the embedding model LRU cache)
# for mod_name in list(sys.modules.keys()):
#     if mod_name.startswith("app.") or mod_name.startswith("ingest."):
#         importlib.reload(sys.modules[mod_name])

from app.orchestrator import ask  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Mutual Fund FAQ Assistant",
    page_icon="📊",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Auto-expanding textarea CSS
# Uses a MutationObserver to grow the textarea as content is typed.
# Falls back gracefully if JS is unavailable.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Make the textarea start compact and grow with content */
textarea[data-testid="stTextArea"] {
    min-height: 56px !important;
    overflow-y: hidden !important;
    resize: none !important;
    transition: height 0.1s ease;
    font-size: 1rem !important;
    line-height: 1.5 !important;
    padding: 0.6rem 0.75rem !important;
}
/* Hide the Streamlit label since we use label_visibility="collapsed" */
.stTextArea label { display: none !important; }
</style>

<script>
// Auto-expand: grow the textarea to fit its content on every input event.
function autoResize(el) {
    el.style.height = "auto";
    el.style.height = (el.scrollHeight) + "px";
}
function attachAutoResize() {
    const areas = document.querySelectorAll("textarea");
    areas.forEach(el => {
        if (!el.dataset.autoResize) {
            el.dataset.autoResize = "1";
            el.addEventListener("input", () => autoResize(el));
            autoResize(el);
        }
    });
}
// Observe DOM for Streamlit rerenders inserting new textareas
const observer = new MutationObserver(attachAutoResize);
observer.observe(document.body, { childList: true, subtree: true });
attachAutoResize();
</script>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Disclaimer banner — always visible at the top
# ---------------------------------------------------------------------------
st.warning("⚠️ **Facts-only. No investment advice.**")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("📊 Mutual Fund FAQ Assistant")
st.markdown(
    """
Welcome! I answer **factual questions** about 5 mutual fund schemes sourced from official
Economic Times factsheets. Every answer includes a citation link and the date it was last updated.

**Covered schemes:** SBI ELSS Tax Saver Fund · ICICI Prudential BHARAT 22 FOF ·
HSBC Midcap Fund · Groww Liquid Fund · Bank of India Flexi Cap Fund
"""
)

# ---------------------------------------------------------------------------
# Example questions
# ---------------------------------------------------------------------------
EXAMPLES = [
    "What is the exit load of the HSBC Midcap Fund?",
    "What is the lock-in period for the SBI ELSS Tax Saver Fund?",
    "What is the minimum SIP investment for the Groww Liquid Fund?",
]

st.markdown("**Try one of these:**")
cols = st.columns(len(EXAMPLES))
for col, example in zip(cols, EXAMPLES):
    if col.button(example, use_container_width=True):
        st.session_state["query_input"] = example
        st.rerun()

# ---------------------------------------------------------------------------
# Input — auto-expanding textarea bound to session state
# ---------------------------------------------------------------------------
st.divider()

if "query_input" not in st.session_state:
    st.session_state["query_input"] = ""

query = st.text_area(
    "Your question",
    key="query_input",
    placeholder="e.g. Which fund has given highest returns in the last 3 years?\ne.g. What is the expense ratio of Bank of India Flexi Cap Fund?",
    label_visibility="collapsed",
    height=68,          # starting height (~2 lines); JS grows it automatically
)

ask_clicked = st.button("Ask", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------
if ask_clicked and query.strip():
    with st.spinner("Looking up facts…"):
        answer, footer = ask(query.strip())

    st.divider()

    if answer.answer_type == "fact":
        st.markdown(f"**Answer:** {answer.text}")
        if answer.citation_url:
            st.markdown(f"🔗 **Source:** [{answer.citation_url}]({answer.citation_url})")
        if footer:
            st.caption(f"🕒 **Last updated timestamp:** {footer.replace('Last updated from sources: ', '')}")

    elif answer.answer_type == "comparison":
        period_label = answer.comparison_period or "trailing"
        st.markdown(f"**{period_label.capitalize()} return comparison** across all 5 covered funds:")

        if answer.comparison_rows:
            import pandas as pd

            table_data = {
                "Rank": [],
                "Fund": [],
                "Category": [],
                f"{period_label.capitalize()} Return": [],
            }
            for i, row in enumerate(answer.comparison_rows, 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                table_data["Rank"].append(medal)
                table_data["Fund"].append(row.scheme)
                table_data["Category"].append(row.category)
                table_data[f"{period_label.capitalize()} Return"].append(f"{row.return_pct:+.2f}%")

            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("**Sources:**")
            for row in answer.comparison_rows:
                st.markdown(f"- [{row.scheme}]({row.source_url})")

        st.warning(
            "⚠️ **Disclaimer:** Past performance is not indicative of future returns. "
            "This is factual data from official Economic Times factsheets — **not investment advice**."
        )
        if answer.as_of_date:
            st.caption(f"🕒 **Last updated timestamp:** {answer.as_of_date}")

    else:
        st.info(f"ℹ️ {answer.text}")

elif ask_clicked and not query.strip():
    st.warning("Please enter a question.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Facts-only. No investment advice. "
    "Data sourced from Economic Times mutual fund factsheets. "
    "Always verify facts directly with the AMC or SEBI/AMFI before making financial decisions."
)
