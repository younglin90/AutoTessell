#!/bin/bash
# 각 tier를 cube STL에 대해 draft 품질로 실행합니다.
# Usage: bash run_all_tiers_cube.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SINGLE="$SCRIPT_DIR/run_single_tier_cube.py"

declare -a TIERS=(
    "tier2_tetwild core.generator.tier2_tetwild Tier2TetWildGenerator"
    "tier05_netgen core.generator.tier05_netgen Tier05NetgenGenerator"
    "tier1_snappy core.generator.tier1_snappy Tier1SnappyGenerator"
    "tier15_cfmesh core.generator.tier15_cfmesh Tier15CfMeshGenerator"
    "tier_meshpy core.generator.tier_meshpy TierMeshPyGenerator"
    "tier_wildmesh core.generator.tier_wildmesh TierWildMeshGenerator"
    "tier_gmsh_hex core.generator.tier_gmsh_hex TierGmshHexGenerator"
    "tier_cinolib_hex core.generator.tier_cinolib_hex TierCinolibHexGenerator"
    "tier_voro_poly core.generator.tier_voro_poly TierVoroPolyGenerator"
    "tier_mmg3d core.generator.tier_mmg3d TierMMG3DGenerator"
    "tier_robust_hex core.generator.tier_robust_hex TierRobustHexGenerator"
    "tier_algohex core.generator.tier_algohex TierAlgoHexGenerator"
    "tier_jigsaw core.generator.tier_jigsaw TierJigsawGenerator"
    "tier0_core core.generator.tier0_core Tier0CoreGenerator"
    "tier_hohqmesh core.generator.tier_hohqmesh TierHOHQMeshGenerator"
    "tier_hex_classy_blocks core.generator.tier_hex_classy_blocks TierHexClassyBlocksGenerator"
)

echo ""
echo "================================================================================================================================"
echo " Tier 전체 테스트 — cube.stl (1×1×1), Draft Quality"
echo "================================================================================================================================"
printf "%-30s | %-12s | %8s | %s\n" "Tier" "Status" "Time" "Error/Note"
echo "================================================================================================================================"

SUCCESS=0
FAIL=0
TOTAL=0

for entry in "${TIERS[@]}"; do
    read -r tier_name module_path class_name <<< "$entry"
    TOTAL=$((TOTAL + 1))

    TIMEOUT=60
    if [[ "$tier_name" == "tier_robust_hex" ]]; then TIMEOUT=150; fi   # draft=120s + 여유
    if [[ "$tier_name" == "tier_algohex" ]]; then TIMEOUT=180; fi
    if [[ "$tier_name" == "tier_mmg3d" ]]; then TIMEOUT=90; fi
    if [[ "$tier_name" == "tier1_snappy" ]]; then TIMEOUT=90; fi
    if [[ "$tier_name" == "tier15_cfmesh" ]]; then TIMEOUT=90; fi

    RESULT=$(timeout $TIMEOUT python3 "$SINGLE" "$tier_name" "$module_path" "$class_name" 2>/dev/null | tail -1)
    EXIT_CODE=$?

    if [[ $EXIT_CODE -eq 124 ]]; then
        STATUS="timeout"
        ELAPSED=">${TIMEOUT}s"
        ERROR="timed out after ${TIMEOUT}s"
    elif [[ -z "$RESULT" ]]; then
        STATUS="no_output"
        ELAPSED="?"
        ERROR="no JSON output"
    else
        STATUS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "parse_error")
        ELAPSED=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('elapsed',0):.1f}s\")" 2>/dev/null || echo "?")
        ERROR=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','')[:80])" 2>/dev/null || echo "")
    fi

    MARK="✅"
    if [[ "$STATUS" != "success" ]]; then
        MARK="❌"
        FAIL=$((FAIL + 1))
    else
        SUCCESS=$((SUCCESS + 1))
    fi

    printf "%-30s | %-12s | %8s | %s\n" "$MARK $tier_name" "$STATUS" "$ELAPSED" "$ERROR"
done

echo "================================================================================================================================"
echo ""
echo "Total: $TOTAL  |  Success: $SUCCESS  |  Failed: $FAIL"
