#!/usr/bin/env python3
from pathlib import Path
import sys

try:
    from pdfdeal.v3_media import run_cli
except ImportError:  # pragma: no cover - local repo execution fallback
    sys.modules.pop("pdfdeal", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pdfdeal.v3_media import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli("figure"))
