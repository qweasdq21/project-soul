"""`python -m soul` 入口 → soul.cli.main。"""
from __future__ import annotations
import sys
from soul.cli import main

if __name__ == "__main__":
    sys.exit(main())