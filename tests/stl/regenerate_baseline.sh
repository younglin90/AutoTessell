#!/usr/bin/env bash
# beta81 — bench baseline 재생성 스크립트.
#
# Usage:
#   bash tests/stl/regenerate_baseline.sh            # draft 15 조합 (권장, ~5 min)
#   bash tests/stl/regenerate_baseline.sh --limit 30 # draft+standard 30 조합 (10+ min)
#
# 주의: standard quality 의 ultra_knot STL 은 300s+ 소요.
# CI baseline 은 --limit 15 (draft only) 으로 유지하고 drift-check 도 동일 범위로.
#
# 결과물: tests/stl/bench_v04_baseline.json
# 이후 CI drift 감지:
#   python3 tests/stl/bench_v04_matrix.py --limit 15 \
#       --drift-check tests/stl/bench_v04_baseline.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BASELINE="$SCRIPT_DIR/bench_v04_baseline.json"
LIMIT="${1:---limit 15}"

cd "$REPO_ROOT"
echo "[bench] $LIMIT 조합으로 baseline 생성 → $BASELINE"
python3 tests/stl/bench_v04_matrix.py $LIMIT --regenerate-baseline "$BASELINE"
echo "[bench] 완료. $(jq length "$BASELINE") 조합 저장됨."
