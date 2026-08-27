"""Which backend src.store dispatches every read/write to: "local"
(SQLite, default) or "supabase". The selection is tracked in a small
local file rather than in either backend, since it's what decides
which backend to even look at."""

from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "data_source.txt"
VALID = ("local", "supabase")
DEFAULT = "local"


def get_data_source():
    if PATH.exists():
        value = PATH.read_text().strip()
        if value in VALID:
            return value
    return DEFAULT


def set_data_source(value):
    if value not in VALID:
        raise ValueError(f"Unknown data source: {value!r}")
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(value)
