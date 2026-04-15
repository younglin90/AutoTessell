#!/bin/bash
# 각 tier를 별도 프로세스로 실행하고 결과를 수집합니다.
# Usage: bash run_all_tiers.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SINGLE="$SCRIPT_DIR/run_single_tier.py"

# tier_name, module_path, class_name
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
    "tier_jigsaw_fallback core.generator.tier_jigsaw_fallback TierJigsawFallbackGenerator"
    "tier0_core core.generator.tier0_core Tier0CoreGenerator"
    "tier_hohqmesh core.generator.tier_hohqmesh TierHOHQMeshGenerator"
    "tier_hex_classy_blocks core.generator.tier_hex_classy_blocks TierHexClassyBlocksGenerator"
    "tier_classy_blocks core.generator.tier_classy_blocks TierClassyBlocksGenerator"
    "tier_polyhedral core.generator.polyhedral PolyhedralGenerator"
    "tier0_2d_meshpy core.generator.tier0_2d_meshpy Tier2DMeshPyGenerator"
)

echo ""
echo "=============================================================================================="
printf "%-28s | %-14s | %8s | %s\n" "Tier" "Status" "Time" "Error/Note"
echo "=============================================================================================="

SUCCESS=0
FAIL=0
TOTAL=0

for entry in "${TIERS[@]}"; do
    read -r tier_name module_path class_name <<< "$entry"
    TOTAL=$((TOTAL + 1))

    # 타임아웃 설정
    TIMEOUT=60
    if [[ "$tier_name" == "tier_robust_hex" ]]; then TIMEOUT=90; fi
    if [[ "$tier_name" == "tier_algohex" ]]; then TIMEOUT=120; fi
    if [[ "$tier_name" == "tier_mmg3d" ]]; then TIMEOUT=90; fi

    # 실행 (stderr는 /dev/null, stdout만 캡처)
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
        ERROR=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','')[:60])" 2>/dev/null || echo "")
    fi

    if [[ "$STATUS" == "success" ]]; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAIL=$((FAIL + 1))
    fi

    printf "%-28s | %-14s | %8s | %s\n" "$tier_name" "$STATUS" "$ELAPSED" "$ERROR"
done

echo "=============================================================================================="
echo ""
echo "Total: $TOTAL  |  Success: $SUCCESS  |  Failed/Error: $FAIL"
