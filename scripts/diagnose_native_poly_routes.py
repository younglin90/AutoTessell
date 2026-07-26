#!/usr/bin/env python3
"""Run the bounded POLY-ROUTE-ATTRIB1 native_poly diagnostic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.generator.native_poly.route_attribution import main

if __name__ == "__main__":
    raise SystemExit(main())
