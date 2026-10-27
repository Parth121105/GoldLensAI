"""Read the first HTML table in a document as rows of cell text.

MCX's date-wise Bhavcopy download (for example BhavCopyDateWise_23102026.xls)
is not an Excel workbook: it is an HTML ``<table>`` saved with an .xls
extension. This reads it with the standard library only; nothing in the file is
executed or fetched.
"""

from __future__ import annotations

from html.parser import HTMLParser


def looks_like_html_table(text: str) -> bool:
    head = text.lstrip()[:2048].lower()
    return head.startswith("<") and "<table" in head


class _FirstTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._depth = 0
        self._done = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        if tag == "table":
            self._depth += 1
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._done = True
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def read_html_table(text: str) -> list[list[str]]:
    """Rows of the first top-level table, each a list of whitespace-normalised cell texts."""
    parser = _FirstTable()
    parser.feed(text)
    parser.close()
    return parser.rows
