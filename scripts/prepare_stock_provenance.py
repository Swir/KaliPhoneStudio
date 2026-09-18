#!/usr/bin/env python3
"""Compatibility wrapper for the shared offline stock provenance ingress."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.stock_baseline_ingress import prepare_stock_provenance_main


if __name__ == "__main__":
    raise SystemExit(prepare_stock_provenance_main())
