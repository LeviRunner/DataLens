"""The one bridge between a browser upload and a connector.

Connectors take a path, because a path is what a CSV, a workbook and a JSON dump all
have in common - and because the CLI and the HTML report feed them files, not browser
objects. An upload is bytes in memory. Somebody has to write those bytes down.

It lives in its own module so that both screens use the SAME bridge: two copies of a
tempfile helper drift into two different suffix rules, and the day one of them writes
a `.csv` without the extension the Excel reader stops recognising the file.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def to_temporary_path(uploaded) -> str:
    """Writes an uploaded file to disk and returns the path.

    The suffix is taken from the uploaded name and not from a parameter: the reader
    that opens the file downstream sometimes decides by extension, and guessing it
    twice in two places is how the two guesses stop agreeing.
    """
    suffix = Path(uploaded.name).suffix or ".dat"
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary.write(uploaded.getvalue())
    temporary.close()
    return temporary.name
