"""Tiny JSON store for the data/ directory: load with a default, and save only
when the *material* content changed (ignoring volatile timestamps), so a run
where nothing moved produces no git diff and therefore no empty commit.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# Keys that change every run on their own — excluded from change detection.
VOLATILE = {"updated_utc", "asof_utc", "captured_utc", "frozen_utc", "generated_utc"}


def path(name):
    return os.path.join(DATA, name)


def load(name, default=None):
    p = path(name)
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def save_if_changed(name, obj):
    """Write `obj` to data/<name> only if its material content differs from disk.
    Returns True if it wrote, False if it was a no-op."""
    old = load(name, None)
    if old is not None and _strip(old) == _strip(obj):
        return False
    with open(path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return True
