# AutoTessell — Agent Instructions

See **[CLAUDE.md](CLAUDE.md)** for the canonical project map, architecture, and conventions.

Scoped rules (coding style, lessons learned, execution model, communication) live in **[.claude/rules/](.claude/rules/)**.

Do not duplicate CLAUDE.md content here — this file is only a pointer.

## Native-engine improvement rounds

For any iterative native meshing, boundary-layer, surface-remeshing, or quality-gate improvement, use the repository skill $native-engine-round before making an implementation change. The skill requires a literature-backed plan before code changes and a durable round report before stopping. The repository Codex hooks enforce the corresponding artifact gates when an improvement round is active.
