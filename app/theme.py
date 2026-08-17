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

import re
from functools import lru_cache
from pathlib import Path

import streamlit as st

from datalens.i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, text

# Heights in pixels, chosen against the 768px budget and not by eye:
#   ~45 page title + ~40 source row + ~30 chips + ~95 cards + gaps = ~230 spent,
#   leaving ~470 of a 700px viewport for the one row of charts.
# Measured against the running page, not guessed: the first pass left 250px of
# empty dark at the bottom, which reads as a page that failed to finish loading.
CHART_HEIGHT = 300

_STYLE = """
<style>
  /* ============================================================
     THE ONE-ACCENT DESIGN SYSTEM
     A single highlight colour for the whole interface - the pink/red of the card
     border in the reference - used by every border, button, active state and card.
     Everything else is a neutral surface tone. Nothing here hardcodes a second
     highlight colour anywhere else in the app.
     ============================================================ */
  :root {
      /* The accent IS the border line colour from the reference (#ff4b6e in
         .streamlit/config.toml). One value, consumed everywhere below. */
      --dl-accent:      #ff4b6e;
      --dl-accent-dim:  #e63b5f;          /* hover/active on top of the accent */
      --dl-accent-soft: rgba(255, 75, 110, 0.14);
      --dl-focus:       rgba(255, 75, 110, 0.45);

      /* Neutral surfaces and text. */
      --dl-surface:   #181c26;
      --dl-surface-2: #1d2230;
      --dl-muted:     #8b93a7;
      --dl-text:      #e6e8ee;

      /* Every structural border in the app is the accent. */
      --dl-border:  var(--dl-accent);
      --dl-radius:  10px;
  }

  /* Streamlit reserves 6rem above the first element for a document. This is not a
     document. */
  .block-container { padding: 1.1rem 1.5rem 0.8rem 1.5rem; max-width: 100%; }
  header[data-testid="stHeader"] { height: 0; background: transparent; }
  footer, #MainMenu { visibility: hidden; }

  /* Vertical gap between rows. The default 1rem, three times over, is a whole KPI
     card's worth of nothing. */
  div[data-testid="stVerticalBlock"] { gap: 0.5rem; }

  /* ===== Cards, metrics, panels, bordered containers: ONE frame =====
     Every card in the app - the KPI row, the three chart panels, the three
     simulation cards (st.container(border=True)) and the metric boxes - shares the
     same surface, radius and accent border. Both metric test ids are listed because
     Streamlit renamed this one between versions. */
  div[data-testid="stMetric"],
  div[data-testid="metric-container"],
  .dl-panel,
  div[data-testid="stVerticalBlockBorderWrapper"] {
      background: var(--dl-surface);
      border: 1px solid var(--dl-border);
      border-radius: var(--dl-radius);
      padding: 0.6rem 0.85rem;
  }
  div[data-testid="stMetricValue"] { font-size: 1.5rem; color: var(--dl-text); }
  div[data-testid="stMetricLabel"] { opacity: 0.72; font-size: 0.78rem; }

  /* The chart panels get the same frame as the cards, or the middle of the page
     reads as a hole between two bordered rows. */
  .dl-panel { padding: 0.5rem 0.6rem 0.2rem 0.6rem; }

  /* ===== Buttons: ONE system =====
     Every button - menu actions, download, export, the language switcher and the
     form submit - is the same shape: same radius, same height, same typography,
     same 1px accent border. Primary buttons are filled with the accent; secondary
     (the unselected language) are outlined in it. Both states share the accent, so
     a button cannot come out a different colour somewhere else in the app. */
  div[data-testid="stBaseButton-primary"] button,
  div[data-testid="stBaseButton-secondary"] button,
  div[data-testid="stFormSubmitButton"] button {
      font-family: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      line-height: 1.2;
      min-height: 2.2rem;
      padding: 0.4rem 0.9rem;
      border-radius: 8px;
      cursor: pointer;
      transition: background-color 0.15s ease, border-color 0.15s ease,
                  color 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-testid="stBaseButton-primary"] button,
  div[data-testid="stFormSubmitButton"] button {
      background-color: var(--dl-accent);
      border: 1px solid var(--dl-accent);
      color: #ffffff;
  }
  div[data-testid="stBaseButton-secondary"] button {
      background-color: transparent;
      border: 1px solid var(--dl-accent);
      color: var(--dl-accent);
  }
  div[data-testid="stBaseButton-primary"] button:hover,
  div[data-testid="stFormSubmitButton"] button:hover {
      background-color: var(--dl-accent-dim);
      border-color: var(--dl-accent-dim);
      color: #ffffff;
  }
  div[data-testid="stBaseButton-secondary"] button:hover {
      background-color: var(--dl-accent-soft);
      border-color: var(--dl-accent);
      color: var(--dl-accent);
  }
  div[data-testid^="stBaseButton"] button:active,
  div[data-testid="stFormSubmitButton"] button:active {
      filter: brightness(0.92);
  }
  div[data-testid^="stBaseButton"] button:focus-visible,
  div[data-testid="stFormSubmitButton"] button:focus-visible {
      outline: none;
      box-shadow: 0 0 0 3px var(--dl-focus);
  }
  div[data-testid^="stBaseButton"] button:disabled,
  div[data-testid="stFormSubmitButton"] button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
  }

  /* ===== Inputs and controls: the same accent border ===== */
  div[data-baseweb="input"],
  div[data-baseweb="select"] > div,
  div[data-testid="stTextArea"] textarea {
      background-color: var(--dl-surface-2);
      border: 1px solid var(--dl-border);
      border-radius: 8px;
      color: var(--dl-text);
  }
  div[data-baseweb="input"] input,
  div[data-testid="stTextArea"] textarea { color: var(--dl-text); }
  div[data-baseweb="input"]:focus-within,
  div[data-testid="stTextArea"]:focus-within,
  div[data-testid="stTextInput"]:focus-within,
  div[data-testid="stNumberInput"]:focus-within,
  div[data-testid="stDateInput"]:focus-within {
      box-shadow: 0 0 0 3px var(--dl-focus);
  }

  /* The number input steppers (+/-) use the accent, not a second colour. */
  div[data-testid="stNumberInput"] div[data-baseweb="input"] button {
      color: var(--dl-accent);
      border-color: var(--dl-border);
  }

  /* Selected radio (the page menu) and checked states use the accent. BaseWeb already
     draws the selected dot with the theme's primary colour - this makes the label
     follow so the whole row reads as "active". */
  div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
      color: var(--dl-accent);
      font-weight: 600;
  }
  div[data-testid="stCheckbox"] label:has(input:checked) {
      color: var(--dl-accent);
      font-weight: 600;
  }

  /* The file dropzone and the dataframe frame follow the same border rule. */
  div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
      background-color: var(--dl-surface);
      border: 1px dashed var(--dl-border);
      border-radius: 8px;
  }
  div[data-testid="stDataFrame"],
  div[data-testid="stDataEditor"] {
      border: 1px solid var(--dl-border);
      border-radius: 8px;
      overflow: hidden;
  }
  div[data-testid="stExpander"] {
      border: 1px solid var(--dl-border);
      border-radius: 8px;
      background-color: var(--dl-surface);
  }

  /* The sidebar gets the same accent edge as every card. */
  section[data-testid="stSidebar"] { border-right: 1px solid var(--dl-border); }

  /* ===== Alert boxes share the one accent =====
     st.info/st.warning/st.error are semantic, but their frames must not introduce a
     blue/amber/green border that fights the single accent of the page. */
  div[data-testid="stAlert"] {
      background-color: var(--dl-accent-soft);
      border: 1px solid var(--dl-border);
      border-radius: 8px;
      color: var(--dl-text);
  }
  div[data-testid="stAlert"] svg { color: var(--dl-accent); }
  div[data-testid="stAlert"] [data-testid="stAlertContent"] p { color: var(--dl-text); }

  /* ===== Typography: one family, one hierarchy ===== */
  div[data-testid="stWidgetLabel"],
  div[data-testid="stWidgetLabel"] p {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--dl-text);
      letter-spacing: 0.01em;
  }
  div[data-testid="stCaption"],
  div[data-testid="stCaption"] p {
      font-size: 0.72rem;
      color: var(--dl-muted);
  }

  /* THE FIFTH FILTER WAS INVISIBLE. BaseWeb caps its multiselect at 155px and hides
     the overflow; in a sidebar this narrow each choice takes a line of its own, so the
     fifth tag was clipped away and the reader was filtering by something they could not
     see. A filter you cannot read is worse than no filter - let the control grow. */
  div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
  div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div > div {
      max-height: none; overflow: visible; flex-wrap: wrap;
  }

  /* The placeholder is an instruction, not a value: light grey so it never reads as a
     selection that is already in force. */
  div[data-testid="stMultiSelect"] div[data-baseweb="select"] [class*="placeholder"],
  div[data-testid="stMultiSelect"] input::placeholder {
      color: var(--dl-muted); opacity: 1;
  }

  /* The chips: the row of categories above the numbers in the reference. They are
     labels, not buttons - nothing happens when you click one, so they must not look
     clickable. Hence no hover, no cursor change.

     A chip is the HEADER OF THE CARD UNDER IT, not a free-floating badge: it is drawn
     inside the same column, sits flush on the card, and the two share one outline. The
     first version left an 8px gutter between the two boxes, which read as two unrelated
     rows - and worse, the chip OVERFLOWED its own row and printed on top of the card
     (see the height rules below). */
  .dl-chip {
      display: block; width: 100%; text-align: center;
      background: var(--dl-surface);
      border: 1px solid var(--dl-accent);
      border-bottom: none;
      border-radius: 8px 8px 0 0; padding: 0.3rem 0.5rem;
      font-size: 0.78rem; letter-spacing: 0.02em;
      box-sizing: border-box; height: 2rem;
  }
  .dl-chip span { color: var(--dl-accent); margin-right: 0.35rem; }

  /* STREAMLIT SIZES THE MARKDOWN SLOT AS IF IT HELD A LINE OF TEXT - 16px - and a
     bordered 32px chip inside it simply spills over the card below. Nothing in the
     stylesheet says so, and `height: auto` does not undo it: the slot has to be TOLD
     the chip's height. `2rem` is the same number the chip itself carries, so the two
     cannot drift apart. */
  div[data-testid="stElementContainer"]:has(> div > div > div > .dl-chip),
  div[data-testid="stElementContainer"]:has(.dl-chip) [data-testid="stMarkdown"],
  div[data-testid="stElementContainer"]:has(.dl-chip) [data-testid="stMarkdown"] > div {
      display: block; height: 2rem;
  }

  /* The chip and the card it captions are ONE card. The column's own 0.5rem gap is
     cancelled here rather than globally, because everywhere else on these screens that
     gap is what keeps the rows apart. */
  div[data-testid="stElementContainer"]:has(.dl-chip) { margin-bottom: -0.5rem; }
  div[data-testid="stElementContainer"]:has(.dl-chip)
    + div[data-testid="stElementContainer"] div[data-testid="stMetric"] {
      border-radius: 0 0 10px 10px;
  }

  /* Between the row of cards and the row of charts, the SAME 1rem the columns already
     put between one card and the next. A grid whose vertical gutter is half its
     horizontal one reads as two loose rows instead of one block.
     The selector hangs off the WRAPPER and not off the row itself: Streamlit gives
     every column row a `stLayoutWrapper` of its own, so two rows are never siblings and
     `stHorizontalBlock ~ stHorizontalBlock` matches nothing at all. */
  div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stHorizontalBlock"])
    ~ div[data-testid="stLayoutWrapper"]:has(> div[data-testid="stHorizontalBlock"]) {
      margin-top: 0.5rem;
  }

  /* ===== Brand block =====
     The logo is the network SVG drawn above the wordmark. It is read from
     .private_docs/DataLens icon.svg at draw time (see `brand` below) and injected
     inline, so it can carry the accent colour on the dark surface.

     SIZING RULE: the icon and the wordmark are one block, and the icon is always as
     wide as the DATALENS text. `.dl-brand-word` is an inline-block that shrink-wraps
     to the word only - the visible mark is absolutely positioned, so it contributes
     no width - and an in-flow `.dl-brand-mark-spacer` (an empty box of the same
     aspect ratio, whose empty content contributes no width either) reserves the
     icon's height. The mark is then pinned to the top of that reserved box with
     left:0/right:0, which IS the width of the text, whatever the font renders it to.

     WHY THE SPACER IS MANDATORY: an earlier version anchored the mark with
     `bottom:100%`, i.e. out of flow ABOVE the word. The sidebar's scroll container
     clips everything above its content area, so the logo came out cut at the top.
     The spacer keeps the icon inside the flow, and nothing is ever clipped. */
  .dl-brand { text-align: center; padding: 0.9rem 0; }
  .dl-brand-word {
      position: relative; display: inline-block; max-width: 100%;
  }
  .dl-brand-mark-spacer {
      width: 100%; aspect-ratio: 7173.53 / 6160.09;
  }
  .dl-brand-mark {
      position: absolute; top: 0; left: 0; right: 0;
      aspect-ratio: 7173.53 / 6160.09;
  }
  .dl-brand-mark svg { position: absolute; inset: 0; height: 100%; width: 100%; }
  /* The SVG ships with black strokes (CorelDRAW export). One accent rule wins by
     specificity and turns the logo into the same colour as every border on the page. */
  .dl-brand-mark svg .str0 { stroke: var(--dl-accent); }
  .dl-brand-name {
      width: max-content;
      font-weight: 700; letter-spacing: 0.22em; font-size: 2.1rem;
      margin: 0.35rem auto 0;
  }

  /* "Page: Home" is hidden, and with it the empty space it occupied: the content
     below rises to take its place. The markup stays in the DOM (the tests read it);
     only the box disappears from the screen. */
  .dl-page-title { display: none; }

  .dl-panel-title {
      font-size: 0.85rem; font-weight: 600; opacity: 0.85;
      margin: 0 0 0.2rem 0;
  }

  /* The simulation cards reuse the same typography as the panels: one size for
     the heading, one for the caption, so a card in the row cannot shout over
     its neighbour. */
  .dl-card-title {
      font-size: 0.9rem; font-weight: 600; opacity: 0.9;
      margin: 0 0 0.1rem 0;
  }
  .dl-card-subtitle {
      font-size: 0.72rem; opacity: 0.6; margin: 0 0 0.35rem 0;
  }

  /* The section heading above the three simulation cards: same weight as the
     panel titles, large enough to split the page in two, small enough to stay
     inside the fold. */
  .dl-sim-heading {
      text-align: center; font-size: 1.05rem; font-weight: 600;
      margin: 0 0 0.5rem 0;
  }

  /* ===== The "Tempo de resposta" card =====
     Same frame as every other card: same surface, same radius, same accent border.
     The value may stay prominent, but it is white-on-dark - no new identity colour. */
  .dl-response {
      text-align: center;
      background: var(--dl-surface);
      border: 1px solid var(--dl-border);
      border-radius: var(--dl-radius);
      padding: 0.6rem 0.85rem;
      margin-top: 0.5rem;
  }
  .dl-response-label {
      font-size: 0.78rem; opacity: 0.72; margin-bottom: 0.15rem;
  }
  .dl-response-value {
      font-size: 1.5rem; font-weight: 700; color: var(--dl-text);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  }
</style>
"""


def apply() -> None:
    """Injects the stylesheet. Called once, at the top of the script."""
    st.markdown(_STYLE, unsafe_allow_html=True)


_LOGO_SVG_PATH = Path(__file__).resolve().parent.parent / ".private_docs" / "DataLens icon.svg"


@lru_cache(maxsize=1)
def _logo_svg() -> str:
    """The DataLens icon, ready to be inlined.

    Cached: the file does not change while the app is running, and reading it on every
    rerun would be the same bytes over and over. A missing file returns an empty
    string, so `brand` falls back to the text mark instead of crashing the page.

    The prolog (`<?xml ...?>`, `<!DOCTYPE ...>`) is CorelDRAW's file header, not part
    of an element - a browser ignores it inside HTML, but inlining it is sloppy, so it
    is stripped before the markup reaches the page.
    """
    try:
        markup = _LOGO_SVG_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    return re.sub(r"<\?xml[^?]*\?>\s*|<!DOCTYPE[^>]*>\s*", "", markup)


def brand(name: str, mark: str) -> None:
    """The logo block at the top of the sidebar: the icon above the wordmark.

    When the icon file is present, its SVG replaces the text mark and is given the
    same width as the DATALENS word below it (see the `.dl-brand-mark` sizing rule).
    The `mark` parameter stays as the fallback for when the file cannot be read.
    """
    logo = _logo_svg() or mark
    st.sidebar.markdown(
        f'<div class="dl-brand">'
        f'<div class="dl-brand-word">'
        f'<div class="dl-brand-mark-spacer"></div>'
        f'<div class="dl-brand-mark">{logo}</div>'
        f'<div class="dl-brand-name">{name}</div>'
        f"</div>"
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


def chip(label: str, mark: str = "▮") -> None:
    """The category label that caps the card drawn straight after it.

    It captions that card and nothing else - which is why it is markup and not
    `st.button`: a chip that looks pressable and does nothing is worse than no chip.

    DRAWN INTO THE CALLER'S COLUMN, never as a row of its own. A separate `st.columns`
    for the chips looked identical until the numbers changed width: two independent
    column rows are two independent layouts, and the caption drifted off the card it was
    captioning. One column, chip then card, is the only arrangement that cannot drift.
    """
    st.markdown(
        f'<div class="dl-chip"><span>{mark}</span>{label}</div>',
        unsafe_allow_html=True,
    )


def panel_title(text: str) -> None:
    st.markdown(f'<div class="dl-panel-title">{text}</div>', unsafe_allow_html=True)


def language_buttons(current: str) -> None:
    """The language switcher, as buttons below the main menu.

    The endonyms never change, so the labels are safe in every language. The selected
    language is a filled accent button and the others are outlined accent buttons - one
    system, one colour, exactly like every button in the app.
    """
    st.sidebar.markdown("**Language / Idioma**")
    columns = st.sidebar.columns(len(SUPPORTED_LANGUAGES))
    for column, code in zip(columns, SUPPORTED_LANGUAGES):
        with column:
            st.button(
                LANGUAGE_NAMES[code],
                key=f"lang_{code}",
                type="primary" if code == current else "secondary",
                use_container_width=True,
            )


def response_time(seconds: float) -> None:
    """The load-time card at the bottom of the sidebar, framed like every card."""
    st.sidebar.markdown(
        f'<div class="dl-response">'
        f'<div class="dl-response-label">Tempo de resposta</div>'
        f'<div class="dl-response-value">{seconds:.2f} s</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def panel():
    """A bordered surface to draw a chart inside, as a context manager.

    `st.container(border=True)` and not a `<div>` of our own: HTML written around a
    Streamlit widget does not wrap it - the widget is rendered into its own node
    elsewhere in the tree, and the div closes empty. The container is the only way to
    put a real box around a real chart.
    """
    return st.container(border=True)
