"""O5 / beta2664 — CLI command tree dump (markdown).

cli/main.py 의 모든 click command + option 을 markdown 표로 dump.
docs/guides/usage.md 보강 / 자동 reference 생성.

Usage:
    python3 scripts/dump_cli_tree.py [-o cli_reference.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import click
    from cli.main import cli as click_app

    lines = ["# Auto-Tessell CLI Reference (auto-generated)\n"]

    if not isinstance(click_app, click.Group):
        print("[ERR] cli is not a click.Group", file=sys.stderr)
        return 1

    cmds = click_app.commands  # type: ignore[attr-defined]
    lines.append(f"Total commands: {len(cmds)}\n")
    lines.append("| Command | Description (1-line) | # Options |")
    lines.append("|---------|---------------------|-----------|")
    for name in sorted(cmds.keys()):
        cmd = cmds[name]
        help_text = (cmd.help or "").split("\n")[0].strip()[:80]
        n_opts = sum(
            1 for p in cmd.params  # type: ignore[attr-defined]
            if isinstance(p, click.Option)
        )
        lines.append(f"| `{name}` | {help_text} | {n_opts} |")

    # Per-command option detail.
    for name in sorted(cmds.keys()):
        cmd = cmds[name]
        opts = [
            p for p in cmd.params  # type: ignore[attr-defined]
            if isinstance(p, click.Option)
        ]
        if not opts:
            continue
        lines.append(f"\n## `{name}`\n")
        lines.append((cmd.help or "(no description)").strip())
        lines.append("\n| Option | Type | Default | Help |")
        lines.append("|--------|------|---------|------|")
        for opt in opts:
            opt_str = " / ".join(f"`{f}`" for f in opt.opts)
            type_str = str(opt.type)[:30]
            default_str = (
                "—" if opt.default is None else str(opt.default)[:30]
            )
            help_text = (opt.help or "").split("\n")[0][:80]
            lines.append(f"| {opt_str} | {type_str} | {default_str} | {help_text} |")

    out_text = "\n".join(lines) + "\n"
    out = args.output
    if out is None:
        out = repo / "docs" / "cli_reference.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_text, encoding="utf-8")
    print(f"[OK] {out} ({len(cmds)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
