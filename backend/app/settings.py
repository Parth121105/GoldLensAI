"""Runtime limits, overridable with environment variables (no secrets live here)."""

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


# One upload. MCX's full-market date-wise download (an HTML table saved as .xls) is
# about 17 MB per trading day; the CSV Bhavcopy is far smaller.
DEFAULT_MAX_UPLOAD_BYTES = 25_000_000
# Session limits. Files are parsed in memory and only the accepted gold rows (about 30
# per daily file) are kept, never the raw bytes. 2,000 files is about eight years of
# daily Bhavcopies; the byte limit caps the cumulative size of everything uploaded.
DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_TOTAL_BYTES = 40_000_000_000


@dataclass(frozen=True, slots=True)
class Settings:
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_files: int = DEFAULT_MAX_FILES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_upload_bytes=_int_env("GOLDLENS_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
            max_files=_int_env("GOLDLENS_MAX_FILES", DEFAULT_MAX_FILES),
            max_total_bytes=_int_env("GOLDLENS_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL_BYTES),
        )
