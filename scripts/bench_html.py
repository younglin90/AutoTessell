"""Y4 / beta2733 — bench result HTML report.

bench JSON → 색상화된 HTML 표 (grade 별 셀 색).
브라우저 / 이메일 / Slack 으로 공유 가능.

Usage:
    python3 scripts/bench_html.py result.json -o result.html
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


GRADE_COLOR = {
    "A": "#4caf50",   # green
    "B": "#8bc34a",   # light green
    "C": "#ffc107",   # amber
    "D": "#ff9800",   # orange
    "F": "#f44336",   # red
    "?": "#9e9e9e",   # gray
    "":  "#9e9e9e",
}


def _row_html(r: dict) -> str:
    grade = str(r.get("grade", "?"))
    color = GRADE_COLOR.get(grade, "#9e9e9e")
    fields = [
        html.escape(str(r.get("stl", "?"))),
        html.escape(str(r.get("engine", "?"))),
        f"<span style='background:{color};color:white;padding:2px 6px;border-radius:3px;'>{html.escape(grade)}</span>",
        f"{float(r.get('elapsed', 0)):.2f}",
        "✓" if r.get("success") else "✗",
        html.escape(str(r.get("n_tets", "") or r.get("n_cells", ""))),
    ]
    return "<tr>" + "".join(f"<td>{v}</td>" for v in fields) + "</tr>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    if not args.input.exists():
        print(f"[ERR] missing: {args.input}", file=sys.stderr)
        return 1

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print(f"[ERR] not list", file=sys.stderr)
        return 2

    n = len(rows)
    n_a = sum(1 for r in rows if r.get("grade") == "A")
    n_ok = sum(1 for r in rows if r.get("success"))

    output = args.output or args.input.with_suffix(".html")
    body_rows = "\n".join(_row_html(r) for r in rows if isinstance(r, dict))

    title = html.escape(args.input.name)
    page = f"""<!doctype html>
<html><head><meta charset='utf-8'>
<title>bench: {title}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui; margin: 1.5em; color: #222; }}
h1 {{ font-size: 1.4em; }}
.summary {{ background: #f5f5f5; padding: 0.6em 1em; border-radius: 4px; }}
table {{ border-collapse: collapse; margin-top: 1em; }}
th, td {{ border: 1px solid #ddd; padding: 4px 8px; font-size: 13px; }}
th {{ background: #fafafa; text-align: left; }}
tr:nth-child(even) {{ background: #fbfbfb; }}
</style></head><body>
<h1>bench report — {title}</h1>
<div class='summary'>
  <b>Total:</b> {n} · <b>Success:</b> {n_ok}/{n} ({n_ok / max(n, 1) * 100:.1f}%) ·
  <b>Grade A:</b> {n_a}
</div>
<table>
  <thead><tr><th>STL</th><th>Engine</th><th>Grade</th><th>Elapsed (s)</th><th>OK</th><th>Cells</th></tr></thead>
  <tbody>
{body_rows}
  </tbody>
</table>
</body></html>
"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"[OK] {n} rows → {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
