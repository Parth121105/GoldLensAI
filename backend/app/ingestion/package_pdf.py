"""Recover the package CSV tables from the text of Gold_Lens_AI_MCX_Gold_Complete.pdf.

The PDF's appendix prints each table as a block between ``===BEGIN <name>`` and
``===END <name>``. Text extraction (``pdftotext``) joins a block's lines with
spaces; no value in the package contains a space, so splitting on whitespace
recovers the original lines exactly. Every recovered line must have the header's
column count, otherwise extraction fails rather than guessing.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_BLOCK = re.compile(r"===BEGIN (\S+)\s+(.*?)\s*===END \1", re.DOTALL)
# Page furniture that pdftotext interleaves when a block crosses a page break: the
# running footer, the page number and the form feed. Nothing else is removed.
_FOOTER = re.compile(r"^Gold Lens AI - MCX gold training dataset \| .*$", re.MULTILINE)
_PAGE_NUMBER = re.compile(r"^Page \d+$", re.MULTILINE)


def strip_page_furniture(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    return _PAGE_NUMBER.sub("", _FOOTER.sub("", text))


class PackageExtractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    file_name: str
    csv_text: str
    rows: int  # data rows, excluding the header

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.csv_text.encode("utf-8")).hexdigest()


def extract_blocks(text: str) -> list[ExtractedTable]:
    tables = []
    for name, body in _BLOCK.findall(strip_page_furniture(text)):
        lines = body.split()
        if not lines:
            raise PackageExtractError(f"Block {name} is empty")
        width = lines[0].count(",") + 1
        bad = [i for i, line in enumerate(lines[1:], start=2) if line.count(",") + 1 != width]
        if bad:
            raise PackageExtractError(
                f"Block {name}: lines {bad[:5]} do not have {width} columns; extraction is not exact"
            )
        tables.append(ExtractedTable(name, "\n".join(lines) + "\n", len(lines) - 1))
    if not tables:
        raise PackageExtractError("No ===BEGIN/===END CSV blocks found in the text")
    names = [t.file_name for t in tables]
    if len(set(names)) != len(names):
        raise PackageExtractError(f"Duplicate block names: {names}")
    return tables


def pdf_to_text(pdf: Path) -> tuple[str, str]:
    """Text of a PDF via pdftotext (poppler). Returns (text, tool version)."""
    tool = shutil.which("pdftotext")
    if tool is None:
        raise PackageExtractError("pdftotext was not found on PATH (it ships with poppler and with Git for Windows)")
    version = subprocess.run([tool, "-v"], capture_output=True, text=True, check=False)
    first = (version.stderr or version.stdout).strip().splitlines()
    out = subprocess.run([tool, "-enc", "UTF-8", str(pdf), "-"], capture_output=True, check=True)
    return out.stdout.decode("utf-8"), first[0] if first else "pdftotext"
