"""The "Download data" button: runs scripts/download_data.py from the sidebar.

The script regenerates `data/exemplos/finance.db` and the example CSVs - the same
files the app reads. It lives here and not in `streamlit_app.py` so the wiring stays
thin (the line-count guardrail in the tests), and so a test can call `_run()` without
touching Streamlit's widget tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

from datalens.i18n import text

_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = _ROOT / "scripts" / "download_data.py"


def sidebar_button() -> None:
    """One button: regenerate the data, then drop the cache and reload."""
    if not st.sidebar.button(
        text("ui_download_data"),
        help=text("ui_download_data_help"),
        use_container_width=True,
    ):
        return
    with st.spinner(text("ui_downloading")):
        ok, detalhe = _run()
    st.cache_data.clear()
    if ok:
        st.success(text("ui_download_ok"))
        st.rerun()
    else:
        st.error(text("ui_download_fail", detail=detalhe))


def _run() -> tuple[bool, str]:
    """Runs the script and returns (ok, detail). No Streamlit calls here."""
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if resultado.returncode == 0:
        return True, ""
    detalhe = (resultado.stderr or resultado.stdout or "").strip()[-2000:]
    return False, detalhe or f"exit code {resultado.returncode}"
