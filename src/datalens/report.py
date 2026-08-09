"""Turns a profile into one HTML file someone can open offline.

Two decisions hold this module together.

FIRST, it returns a string and writes nothing. Who decides the destination is who
calls: the app hands it to a download button, a script hands it to the disk. A
function that writes the file itself is hard to test and impossible to reuse.

SECOND, the page is SELF-CONTAINED: the CSS lives in a constant below and the
Plotly javascript is embedded inline, never pulled from a CDN. A report that needs
the network breaks exactly where it matters - on the reader's machine, offline.

And one rule the module never breaks: everything that came from outside is escaped
before it reaches the page. Column names, category values, the title AND the
`source` - the query the user wrote. `WHERE preco < 10` is enough to break the page
with no bad intention at all; `<script>` in a column name is the same bug as SQL
injection one floor up, data being treated as code.
"""

from __future__ import annotations

import html
from typing import Any, Iterable, Mapping

import plotly.graph_objects as go

from .cleaning import CleaningAction
from .profiling import ColumnProfile

# --- Presentation -------------------------------------------------------------
# Embedded on purpose: an external stylesheet is one more thing that has to be
# there when the file is opened, and it never is.

_CSS = """
:root {
  --ink: #16202c;
  --muted: #5d6b7a;
  --rule: #dfe5ec;
  --surface: #ffffff;
  --page: #f4f6f9;
  --accent: #1f6feb;
  --warn: #b4451f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2.5rem 1.25rem 4rem;
  background: var(--page);
  color: var(--ink);
  font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.55;
}
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 2rem; margin: 0 0 .35rem; letter-spacing: -.02em; }
h2 { font-size: 1.15rem; margin: 2.5rem 0 .75rem; }
h3 { font-size: 1.05rem; margin: 0; }
.source {
  margin: 0;
  color: var(--muted);
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: .85rem;
  white-space: pre-wrap;
  word-break: break-word;
}
.card {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: .5rem;
  padding: 1.1rem 1.25rem;
  margin-bottom: 1rem;
}
.card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: .6rem;
  margin-bottom: .6rem;
}
.badge {
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--accent);
  border: 1px solid var(--rule);
  border-radius: 1rem;
  padding: .05rem .55rem;
}
.missing { color: var(--muted); font-size: .85rem; }
.missing.high { color: var(--warn); font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid var(--rule); }
th { color: var(--muted); font-weight: 600; }
td.value { font-variant-numeric: tabular-nums; }
.chart { margin-top: 1rem; overflow-x: auto; }
.empty { color: var(--muted); font-style: italic; }
footer { margin-top: 3rem; color: var(--muted); font-size: .8rem; }
"""

# Above this, the column is more hole than data - and that is the finding, so it
# is coloured instead of hidden.
_HIGH_MISSING_PCT = 50.0

_STAT_LABELS: dict[str, str] = {
    "mean": "mean",
    "median": "median",
    "std": "std",
    "min": "min",
    "max": "max",
    "q1": "q1",
    "q3": "q3",
    "range_days": "range (days)",
    "unique": "unique",
    "avg_length": "avg length",
    "true_count": "true",
    "false_count": "false",
    "is_probable_key": "probable key",
    "is_almost_constant": "almost constant",
    "is_binary_flag": "binary flag",
    "is_identifier": "identifier",
}

# Rendered as their own table instead of as a "top_values: [(...)]" cell.
_TOP_VALUES_KEY = "top_values"


def build_report(
    profiles: Mapping[str, ColumnProfile],
    charts: Mapping[str, go.Figure] | None = None,
    title: str = "DataLens",
    source: str | None = None,
    cleaning_log: Iterable[CleaningAction] | None = None,
) -> str:
    """Builds the whole report and returns it as HTML text.

    `charts` maps a column to the figure drawn for it; the javascript that runs
    them is embedded once, in the first chart. `source` is the provenance - a file
    name or the SQL query - and a report without it is a report nobody can redo.
    """
    safe_title = html.escape(title)
    body = [
        _header(safe_title, source),
        _cleaning_section(cleaning_log),
        _columns_section(profiles, charts or {}),
    ]

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n<main>\n"
        + "\n".join(part for part in body if part)
        + "\n</main>\n</body>\n</html>\n"
    )


# --- Sections -----------------------------------------------------------------


def _header(safe_title: str, source: str | None) -> str:
    """The title and where the data came from - both user text, both escaped."""
    parts = [f"<h1>{safe_title}</h1>"]
    if source:
        parts.append(f'<p class="source">{html.escape(source)}</p>')
    return "<header>\n" + "\n".join(parts) + "\n</header>"


def _cleaning_section(cleaning_log: Iterable[CleaningAction] | None) -> str:
    """What was DONE to the data - the part that turns a profile into a report."""
    actions = list(cleaning_log or [])
    if not actions:
        return ""

    rows = "\n".join(_cleaning_row(action) for action in actions)
    return (
        "<section>\n<h2>Cleaning log</h2>\n"
        '<div class="card">\n<table>\n'
        "<tr><th>column</th><th>action</th><th>rows</th><th>detail</th></tr>\n"
        f"{rows}\n</table>\n</div>\n</section>"
    )


def _cleaning_row(action: CleaningAction) -> str:
    column = html.escape(action.column) if action.column else "&mdash;"
    detail = html.escape(action.detail) if action.detail else ""
    return (
        f"<tr><td>{column}</td>"
        f"<td>{html.escape(str(action.action))}</td>"
        f'<td class="value">{action.count}</td>'
        f"<td>{detail}</td></tr>"
    )


def _columns_section(
    profiles: Mapping[str, ColumnProfile], charts: Mapping[str, go.Figure]
) -> str:
    """One card per column - every column, including the fully empty one.

    Skipping a 100% missing column hides the strongest finding of the analysis:
    having nothing to say about a column IS what there is to say about it.
    """
    if not profiles:
        return (
            "<section>\n<h2>Columns</h2>\n"
            '<p class="empty">No columns to describe.</p>\n</section>'
        )

    cards = []
    plotly_pending = True
    for name, column_profile in profiles.items():
        chart_html = ""
        figure = charts.get(name)
        if figure is not None:
            chart_html = _chart(figure, include_javascript=plotly_pending)
            plotly_pending = False
        cards.append(_column_card(name, column_profile, chart_html))

    return "<section>\n<h2>Columns</h2>\n" + "\n".join(cards) + "\n</section>"


def _column_card(name: str, column_profile: ColumnProfile, chart_html: str) -> str:
    """One column: its name, its type, how much of it is missing, its statistics."""
    safe_name = html.escape(str(name))
    missing_class = (
        "missing high" if column_profile.missing_pct >= _HIGH_MISSING_PCT else "missing"
    )
    head = (
        '<div class="card-head">'
        f"<h3>{safe_name}</h3>"
        f'<span class="badge">{html.escape(str(column_profile.type))}</span>'
        f'<span class="{missing_class}">'
        f"{column_profile.missing_pct:.1f}% missing "
        f"({column_profile.missing} of {column_profile.missing + column_profile.count})"
        "</span>"
        "</div>"
    )

    return (
        f'<div class="card">\n{head}\n'
        f"{_stats_table(column_profile.stats)}\n"
        f"{_top_values_table(column_profile.stats.get(_TOP_VALUES_KEY))}\n"
        f"{chart_html}\n</div>"
    )


def _stats_table(stats: Mapping[str, Any]) -> str:
    rows = [
        f"<tr><th>{html.escape(_STAT_LABELS.get(key, key))}</th>"
        f'<td class="value">{_format(value)}</td></tr>'
        for key, value in stats.items()
        if key != _TOP_VALUES_KEY
    ]
    if not rows:
        return '<p class="empty">No statistics: the column has no values.</p>'
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def _top_values_table(top_values: Any) -> str:
    """The most frequent labels. These are user data as much as the column name."""
    if not top_values:
        return ""

    rows = "\n".join(
        f"<tr><td>{html.escape(str(value))}</td>"
        f'<td class="value">{int(count)}</td></tr>'
        for value, count in top_values
    )
    return (
        "<table>\n<tr><th>value</th><th>count</th></tr>\n" + rows + "\n</table>"
    )


# --- Values and charts --------------------------------------------------------


def _format(value: Any) -> str:
    """One statistic as text, escaped. `None` becomes a dash, never the word 'nan'."""
    if value is None:
        return "&mdash;"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return html.escape(f"{value:,.4g}")
    return html.escape(str(value))


def _chart(figure: go.Figure, include_javascript: bool) -> str:
    """The figure as a self-contained div.

    `include_plotlyjs=True` writes the whole library INLINE, inside a <script> tag -
    that is the point, and it is why "cdn" is not used here. It is written once, for
    the first chart, because the same 3 MB repeated per column turns a report into a
    download nobody opens.
    """
    return '<div class="chart">' + figure.to_html(
        full_html=False,
        include_plotlyjs=True if include_javascript else False,
    ) + "</div>"
