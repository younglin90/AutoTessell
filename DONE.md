# DONE — 자율 루프 목표 달성 (2026-07-02)

## 목표
사용자가 ① STL/CAD 파일 업로드 ② 최종 격자 갯수 N 입력 ③ tet / hex-dominant /
poly-dominant 선택 ④ boundary layer 갯수 입력 → **자동으로 해당 메쉬 생성**,
웹 GUI(`desktop/web/` + `desktop/server.py`)에서 end-to-end 동작.

## 판정
`python tests/verify_goal.py` — **연속 2회 exit 0 (SUCCESS)**.

| mesh_type | verdict | 성공 tier | cells (N=15000) | BL | 시간 |
|-----------|---------|-----------|-----------------|----|------|
| tet | PASS | tier2_tetwild (pytetwild) | 5,305 | 2층 삽입 | 22.3s |
| hex_dominant | PASS | tier_native_hex (자체) | 11,849 | 2층 삽입 (+6,936 prism) | 36.4s |
| poly | PASS | tier_native_poly (자체) | 13,608 | 2층 삽입 | 43.8s |

검증 항목: GUI 4개 컨트롤(업로드/N/mesh_type/BL) · N→target_cells+max_cells 전파 ·
bl_layers→strategy.boundary_layers 전파 · WS E2E 생성 · verdict PASS/PWW ·
0.3N ≤ cells ≤ 3N · 성공 tier가 선택한 mesh_type 계열인지.

## 이번 루프에서 고친 것 (핵심 4건)

1. **generator fallback 버그** ([core/generator/pipeline.py](core/generator/pipeline.py))
   — 명시 tier(=mesh_type 매핑 결과)가 실패하면 `strategy.fallback_tiers` 를
   **무시하고 즉사**하던 버그 수정 (docstring과 코드 불일치). 이제 체인을 따름.
   단일 tier 강제는 기존대로 `strict_tier=True`.

2. **mesh_type 계열 fallback 강화** ([core/strategist/tier_selector.py](core/strategist/tier_selector.py))
   — tet/hex 계열 목록에 자체 구현 tier(`tier_native_tet/hex`, `tier_cfmesh_tet`)
   추가 → 외부 엔진 전무한 환경(이 Windows 박스)에서도 mesh_type 계약 유지.
   mesh_type 명시 시 fallback 을 **같은 계열로 제한** (tet 요청이 hex 로 새지 않음).
   신규 helper `mesh_type_family_tiers()`.

3. **meshio 설치** — tier2_tetwild(볼륨 writer)와 11종 export 가 이 박스에서 실동작.
   (tet 이 native_tet 72k 셀 → tetwild 5k 셀 + 1.2s 로 개선.)

4. **cinolib in-request 자동빌드 가드** ([core/generator/tier_cinolib_hex.py](core/generator/tier_cinolib_hex.py))
   — 메쉬 요청 도중 `git clone`(네트워크 ≤120s)+cmake 빌드하던 것을
   `AUTO_TESSELL_TIER_AUTOBUILD=1` 명시 시에만 허용 (기본 OFF, 결정적 fast-fail).

부수 수정: 서버가 **실제 성공 tier** 보고 + tier별 시도/실패 사유를 WS 로그로
전달 ([desktop/server.py](desktop/server.py)) · GUI 라벨 "목표 셀 수 N" 정리 ·
HOHQMesh control 파일 cp949 인코딩 버그 수정 · 계약 변경에 맞춘 테스트 갱신
(tests/test_generator.py) · 판정 스크립트 신규 (tests/verify_goal.py).

## 실행 방법
```bash
./start_web_gui.sh          # 또는 start_web_gui.bat → http://localhost:9720/
python tests/verify_goal.py # 목표 재검증 (~2분)
```

## 알려진 잔여 이슈 (목표 밖, 기록용)
- **pre-existing 테스트 드리프트 35건**: BETA2835/2845 정책 변경(draft→wildmesh,
  vendored primary, stop_quality 20→10) 후 미갱신된 tests/test_strategist.py ·
  test_tier_selector_native.py · test_generator.py 일부 — 커밋본(HEAD)에서도 동일 실패 확인.
- **hex 1회 간헐 실패 관측** (2.1s all-tiers-failed, 재현 불가 5회 중 1회):
  cinolib in-request 네트워크 빌드가 유력 후보였으며 가드 적용 후 미재현.
- tet 셀 수는 N 대비 ~0.35 (범위 내지만 하한 근접) — tetwild target_cells
  캘리브레이션 여지 있음.
- 이 박스 미설치 외부 엔진: wildmeshing/netgen/meshpy/gmsh/cadquery/OCP/OpenFOAM
  (STEP 미리보기·일부 tier 는 설치 시 자동 활성).
