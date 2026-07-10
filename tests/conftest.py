"""Force SQLite backend for all tests (no AWS credentials required)."""

from __future__ import annotations

import os

os.environ["MIRA_DB_BACKEND"] = "sqlite"
