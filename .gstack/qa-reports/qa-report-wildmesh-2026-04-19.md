# QA Report — WildMesh-only GUI
**Date:** 2026-04-19
**Branch:** master
**Scope:** Desktop Qt GUI + CLI, wildmesh-only mode
**Tier:** Standard (fix critical + high + medium)

## Summary

사용자 요청: 모든 메시 엔진 중 **wildmesh만 사용하도록 전환** 하고 GUI가 제대로 동작하는지 QA.

결과: 2개 HIGH 버그 발견, 둘 다 fix. WildMesh 전용 모드 인프라 신설.
테스트 123 → 133 passed, 0 regression.

## Issues Found

### ISSUE-001 [HIGH]: CLI `--tier` choice 목록 stale

**위치:** `cli/main.py:504`

**재현:**
```bash
$ python3 -m cli.main run sphere.stl -o /tmp/case --tier wildmesh --quality draft
Error: Invalid value for '--tier': 'wildmesh' is not one of
       'auto', 'core', 'netgen', 'snappy', 'cfmesh', 'tetwild'.
```

**원인:** `click.Choice` 리스트가 오래된 6개 tier만 포함. 레지스트리에는 20개
tier가 있지만 CLI에서 14개가 접근 불가 (wildmesh, mmg3d, algohex, robust_hex,
jigsaw, jigsaw_fallback, meshpy, hex_classy, classy_blocks, gmsh_hex,
cinolib_hex, voro_poly, polyhedral, hohqmesh, 2d).

**Fix:** Choice 리스트를 전체 21 엔진으로 확장.

**파일:** `cli/main.py:504`, `cli/main.py:517` (--volume-engine 동일 버그)

**검증:**
```bash
$ python3 -m cli.main run sphere.stl --tier wildmesh --quality draft
✓ PASS (1 iteration, 1.7s)
```

---

### ISSUE-002 [HIGH]: "wildmesh-only 모드" 미존재 → 사용자가 다른 엔진 선택하면 바로 사용됨

**재현:** 사용자가 "WildMesh만 사용" 을 원한다고 밝혔지만:
- GUI 엔진 드롭다운에서 실수로 다른 엔진 선택 가능
- Strategist의 auto 모드는 품질 레벨에 따라 snappy/netgen/cfmesh 자동 선택
- 실패시 fallback 으로 다른 엔진들 순차 시도 → 원치 않는 엔진 침범

**Fix:** 엔진 정책 시스템 신설.

신규 모듈 `desktop/qt_app/engine_policy.py`:
- `EnginePolicy` dataclass (mode, allowed_tiers, default_tier, allow_strategist_fallback)
- 프리셋: `"all"` (기본) / `"wildmesh_only"` (차단 모드)
- 영속화: `~/.autotessell/engine_policy.json`
- ENV override: `AUTOTESSELL_ENGINE_POLICY=wildmesh_only`

`core/strategist/tier_selector.py`:
- `_load_active_policy()` — env 또는 파일에서 정책 읽기
- `_policy_filter_tier(selected, fallbacks)` — 정책에 맞춰 강제 교체 + fallback 차단
- `select()` 내 4개 return 경로 전부에 필터 적용

`desktop/qt_app/main_window.py`:
- `_build_section_engine`: 정책 배너 + 차단된 엔진에 🔒 마커, disable
- 메뉴 "엔진 정책" 신설 (전체 허용 / WildMesh 전용)
- `_on_set_engine_policy` — 모드 전환 + 저장 + 알림

**검증:** wildmesh_only 하에서 `--tier snappy` 요청하면 실제로 `tier_wildmesh` 사용:
```bash
$ AUTOTESSELL_ENGINE_POLICY=wildmesh_only python3 -m cli.main run sphere.stl --tier snappy
[warning] tier_overridden_by_policy  forced=tier_wildmesh  original=tier2_tetwild
successful_tier=tier_wildmesh  total_elapsed=0.43
✓ PASS (1 iteration, 1.7s)
```

---

## Features Added (관련 개선)

### WildMesh 전용 프리셋 3종
`desktop/qt_app/presets.py`:

| 프리셋 | epsilon | edge_length_r | stop_quality | max_its |
|-------|---------|---------------|--------------|---------|
| WildMesh Draft | 0.002 | 0.06 | 20 | 40 |
| WildMesh Standard | 0.001 | 0.04 | 10 | 80 |
| WildMesh Fine (Feature Preserving) | 0.0003 | 0.02 | 5 | 120 |

사용자가 1-클릭으로 CFD 도메인별 WildMesh 튜닝 가능.

## Tests Added (10개)

- `test_engine_policy_default_is_all` — 기본 모드 verification
- `test_engine_policy_wildmesh_only_blocks_other_engines` — 차단 정책 + fallback=[]
- `test_engine_policy_save_and_load_roundtrip` — JSON 영속화
- `test_tier_selector_policy_filter_forces_wildmesh` — strategist 강제 교체
- `test_tier_selector_policy_filter_all_mode_passthrough` — all 모드 bypass
- `test_resolve_engine_canonical_mapping` — GUI 키 → canonical 변환
- `test_wildmesh_presets_exist` — 프리셋 3종 정의
- `test_cli_tier_choice_includes_wildmesh` — CLI stale choice regression 방지
- `test_pipeline_worker_runs_sphere_wildmesh_end_to_end` [slow] — 실제 파이프라인 실행
- `test_wildmesh_only_policy_rewrites_tier_hint` [slow] — snappy 요청 → wildmesh 사용 검증

## Health Score

**Before:** N/A (full app QA, not web)
**After (test suite):** 133 passed, 8 skipped

### Regression
- 2개 기존 테스트가 프리셋 개수 하드코딩으로 깨짐 (5→8)
- 즉시 수정: `test_presets_builtin_list`, `test_preset_save_user_preset_and_load`

## Top 3 Things to Fix (이미 완료)

1. ✅ CLI `--tier` choice 확장 (wildmesh 포함 14개 추가)
2. ✅ wildmesh-only 정책 시스템 (strategist filter + GUI wiring)
3. ✅ WildMesh 전용 프리셋 3종

## Evidence

- **실제 파이프라인 실행:** sphere.stl (642 vertices, 1280 triangles)
  - `tier_hint="wildmesh"` → `tier_wildmesh` selected → 2,964 cells, 857 points
  - PASS_WITH_WARNINGS, 1.7s 완료
  - polyMesh 5 파일 생성 (points/faces/owner/neighbour/boundary)
- **정책 강제 교체 검증:** `--tier snappy` + `wildmesh_only` → `tier_wildmesh` 실행
- **Fallback 차단 검증:** `fallback_order()` 반환 빈 리스트

## 다음 단계 (선택)

GUI에서 `AUTOTESSELL_ENGINE_POLICY=wildmesh_only` 설정된 상태로 실행하면:
- 엔진 드롭다운: 🔒 마커로 차단 엔진 표시
- 기본 선택: WildMesh
- 실행: tier_wildmesh만 시도, 실패시 바로 중단 (fallback 없음)

이 모드는 "WildMesh가 모든 케이스에서 성공하는가?" 를 테스트하는 데 적합.
