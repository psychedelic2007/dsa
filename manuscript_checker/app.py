"""Web UI:  streamlit run manuscript_checker/app.py"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow `streamlit run` from anywhere

from manuscript_checker.extract import ROLE_LABELS, ROLES, SUPPORTED_SUFFIXES, guess_role, load_blocks  # noqa: E402
from manuscript_checker.figures import check_figures  # noqa: E402
from manuscript_checker.report import figure_rows, to_dict  # noqa: E402

STATUS_HELP = {
    "OK": "Captioned and cited in the text",
    "UNCITED": "Caption exists but the figure is never cited in the text",
    "MISSING": "Cited in the text but no caption was found",
}

st.set_page_config(page_title="Manuscript Figure Check", layout="wide")
st.title("Manuscript figure check")
st.caption(
    "Upload your manuscript and any separate figure-legend or supplementary files. "
    "Every figure caption is matched against every figure citation (Fig. 2a–c, Figures 1 and S3, "
    "Supplementary Fig. 4, Figure 3.2, …). Files are processed in memory and not stored."
)

uploads = st.file_uploader(
    "Files", type=[s.lstrip(".") for s in SUPPORTED_SUFFIXES], accept_multiple_files=True
)

if not uploads:
    st.info("DOCX gives the most reliable results. PDF works, but caption detection depends on the PDF's text layer.")
    st.stop()

st.subheader("What is each file?")
roles = {}
for up in uploads:
    default = guess_role(up.name)
    roles[up.name] = st.selectbox(
        up.name, ROLES, index=ROLES.index(default), format_func=ROLE_LABELS.get, key=f"role-{up.name}"
    )
st.caption(
    "In a *supplementary* file, an unprefixed “Figure 1” is treated as Supplementary Figure 1. "
    "Text in a *figures/legends* file counts as legend text, never as a citation."
)

blocks, failed = [], False
for up in uploads:
    try:
        blocks += load_blocks(up.name, up.getvalue(), roles[up.name])
    except Exception as exc:  # surface parse errors per file instead of crashing the page
        st.error(f"Could not read {up.name}: {exc}")
        failed = True
if failed or not blocks:
    st.stop()

report = check_figures(blocks)
if not report.figures:
    st.warning("No figure captions or citations were found in the uploaded files.")
    st.stop()

counts = pd.Series([f.status for f in report.figures]).value_counts()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Figures found", len(report.figures))
c2.metric("OK", int(counts.get("OK", 0)))
c3.metric("Uncited", int(counts.get("UNCITED", 0)))
c4.metric("Caption missing", int(counts.get("MISSING", 0)))

st.subheader("Issues")
if not report.issues:
    st.success("No issues found.")
for issue in report.issues:
    {"error": st.error, "warning": st.warning, "info": st.info}[issue.severity](issue.message)

st.subheader("All figures")
df = pd.DataFrame(figure_rows(report))
st.dataframe(df, width="stretch", hide_index=True)
st.caption(" · ".join(f"**{k}**: {v}" for k, v in STATUS_HELP.items()))

st.subheader("Where each figure is cited")
for f in report.figures:
    with st.expander(f"{f.key.label} — {f.status} ({len(f.body_mentions)} citation(s))"):
        for c in f.captions:
            st.markdown(f"**Caption** · {c.block.location}")
            st.text(c.text[:500])
        for m in f.mentions:
            tag = "legend mention (not counted)" if m.in_caption else "citation"
            st.markdown(f"**{tag}** · {m.block.location} · `{m.matched}`")
            st.text(m.snippet)

st.download_button(
    "Download full report (JSON)",
    json.dumps(to_dict(report), indent=2, ensure_ascii=False),
    file_name="figure_check.json",
    mime="application/json",
)
st.download_button("Download table (CSV)", df.to_csv(index=False), file_name="figure_check.csv", mime="text/csv")
