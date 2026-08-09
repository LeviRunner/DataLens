"""The look of the dashboard: the brand block, the chips, and one page that fits.

WHY THIS FILE EXISTS AT ALL. The palette lives in `.streamlit/config.toml`, not here -
that is what makes the Plotly charts come out dark along with everything else. What
is left over is the part Streamlit has no setting for: vertical space.

THE CONSTRAINT THAT DRIVES EVERY NUMBER BELOW: the home page has to be readable
WITHOUT SCROLLING, on a laptop, at 768px of usable height. Streamlit's defaults spend
roughly a third of that on padding - 6rem above the title alone - which is generous
for a document and fatal for a dashboard. A KPI you have to scroll to reach is a KPI
nobody reads, and the whole point of the shape being copied here is that the answer is
already on screen when the page opens.

So the CSS below only ever does two things: it removes space Streamlit added, and it
draws the card borders that turn a flat column of widgets into panels.

The four colours at the top ARE duplicated from the config, and that is a compromise
worth naming: Streamlit does not expose its theme as CSS custom properties, so a rule
written against `var(--background-color)` resolves to nothing and the border silently
disappears. Four literals that have to be edited twice beat a stylesheet that looks
correct and renders flat.
"""

from __future__ import annotations

import streamlit as st

from datalens.i18n import text

# Heights in pixels, chosen against the 768px budget and not by eye:
#   ~45 page title + ~40 source row + ~30 chips + ~95 cards + gaps = ~230 spent,
#   leaving ~430 of a 700px viewport for the one row of charts.
# Measured against the running page, not guessed: the first pass left 250px of
# empty dark at the bottom, which reads as a page that failed to finish loading.
CHART_HEIGHT = 430

_STYLE = """
<style>
  /* The two surface tones and the accent, written once.

     They are literal values and not `var(--background-color)`: Streamlit does not
     publish its theme as CSS custom properties, so a rule built on those variables
     resolves to nothing and the card silently loses its border - which is exactly
     what happened on the first pass here. These four have to be kept in step with
     .streamlit/config.toml by hand; there are four of them for that reason. */
  :root {
      --dl-surface: #181c26;
      --dl-border:  #2a3040;
      --dl-accent:  #ff4b6e;
      --dl-muted:   #8b93a7;
  }

  /* Streamlit reserves 6rem above the first element for a document. This is not a
     document. */
  .block-container { padding: 1.1rem 1.5rem 0.8rem 1.5rem; max-width: 100%; }
  header[data-testid="stHeader"] { height: 0; background: transparent; }
  footer, #MainMenu { visibility: hidden; }

  /* Vertical gap between rows. The default 1rem, three times over, is a whole KPI
     card's worth of nothing. */
  div[data-testid="stVerticalBlock"] { gap: 0.5rem; }

  /* The panels. A border and a slightly lighter surface is the entire difference
     between "a page of widgets" and "a dashboard" - the eye groups what shares an
     edge. Both test ids are listed because Streamlit renamed this one between
     versions and the older name is still what some builds emit. */
  div[data-testid="stMetric"],
  div[data-testid="metric-container"],
  .dl-panel {
      background: var(--dl-surface);
      border: 1px solid var(--dl-border);
      border-radius: 10px;
      padding: 0.6rem 0.85rem;
  }
  div[data-testid="stMetricValue"] { font-size: 1.5rem; }
  div[data-testid="stMetricLabel"] { opacity: 0.72; font-size: 0.78rem; }

  /* The chips: the row of categories above the numbers in the reference. They are
     labels, not buttons - nothing happens when you click one, so they must not look
     clickable. Hence no hover, no cursor change. */
  .dl-chip {
      display: block; width: 100%; text-align: center;
      background: var(--dl-surface);
      border: 1px solid var(--dl-accent);
      border-radius: 8px; padding: 0.3rem 0.5rem;
      font-size: 0.78rem; letter-spacing: 0.02em;
  }
  .dl-chip span { color: var(--dl-accent); margin-right: 0.35rem; }

  /* The chart panels get the same frame as the cards, or the middle of the page
     reads as a hole between two bordered rows. */
  .dl-panel { padding: 0.5rem 0.6rem 0.2rem 0.6rem; }

  /* The brand block. `letter-spacing` and not a logo file: an image in the repo is
     one more thing to keep in sync, and this is a study project, not a company. */
  .dl-brand { text-align: center; padding: 0.4rem 0 0.9rem 0; }
  .dl-brand-mark { font-size: 2.1rem; line-height: 1; }
  .dl-brand-name {
      font-weight: 700; letter-spacing: 0.22em; font-size: 1.05rem;
      margin-top: 0.35rem;
  }
  .dl-brand-note { opacity: 0.55; font-size: 0.7rem; margin-top: 0.2rem; }

  /* The page heading, in the "Page: Home" shape of the reference. */
  .dl-page-title { font-size: 1.35rem; font-weight: 700; margin: 0 0 0.5rem 0; }
  .dl-page-title span { opacity: 0.5; font-weight: 400; }

  .dl-panel-title {
      font-size: 0.85rem; font-weight: 600; opacity: 0.85;
      margin: 0 0 0.2rem 0;
  }
</style>
"""


def apply() -> None:
    """Injects the stylesheet. Called once, at the top of the script."""
    st.markdown(_STYLE, unsafe_allow_html=True)


def brand(name: str, mark: str, note: str) -> None:
    """The logo block at the top of the sidebar."""
    st.sidebar.markdown(
        f'<div class="dl-brand">'
        f'<div class="dl-brand-mark">{mark}</div>'
        f'<div class="dl-brand-name">{name}</div>'
        f'<div class="dl-brand-note">{note}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def page_title(page: str) -> None:
    """`Page: Home` - the word "Page" greyed, so the eye lands on the name.

    `page` is the menu's stable identifier, never a sentence: the name printed here is
    looked up in the catalog, so the title follows the session's language while the
    branch that compares `page == HOME` keeps comparing the same string in all three.
    """
    st.markdown(
        f'<div class="dl-page-title"><span>{text("ui_page")}</span> '
        f"{text(f'ui_page_{page}')}</div>",
        unsafe_allow_html=True,
    )


def chips(labels: list[str], mark: str = "▮") -> None:
    """The row of category labels above the numbers.

    They caption the cards below them and nothing else - which is why they are markup
    and not `st.button`: a chip that looks pressable and does nothing is worse than no
    chip at all.
    """
    for column, label in zip(st.columns(len(labels)), labels):
        column.markdown(
            f'<div class="dl-chip"><span>{mark}</span>{label}</div>',
            unsafe_allow_html=True,
        )


def panel_title(text: str) -> None:
    st.markdown(f'<div class="dl-panel-title">{text}</div>', unsafe_allow_html=True)


def panel():
    """A bordered surface to draw a chart inside, as a context manager.

    `st.container(border=True)` and not a `<div>` of our own: HTML written around a
    Streamlit widget does not wrap it - the widget is rendered into its own node
    elsewhere in the tree, and the div closes empty. The container is the only way to
    put a real box around a real chart.
    """
    return st.container(border=True)
