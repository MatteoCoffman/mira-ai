#!/usr/bin/env python3
"""Smoke test: seed DB and verify tenant exists."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.sqlite import get_tenant, init_db
from scripts.seed import main


def test_seed_smoke():
    init_db()
    main()
    tenant = get_tenant("daves-hvac")
    assert tenant is not None
    assert tenant["business_name"] == "Dave's HVAC"
    print("Seed smoke test passed.")


if __name__ == "__main__":
    test_seed_smoke()
