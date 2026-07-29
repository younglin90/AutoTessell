# CARD POLY-S1 (beta2822) — native_poly canonical smoke + solid-invariant gates

**target_engine**: poly
**모티프**: native_tet/native_hex 방법론 이식 — "canonical smoke + solid gates → quality"
(scripts/smoke_native_tet.py, tests/test_native_hex_solid_volume.py).

## 현재 상태 실측 (정본 경로로 직접 측정)

cube.stl / draft / mesh_type=poly / **tier_hint="native_poly" / strict_tier=True**
→ 실제 사용 tier = `tier_native_poly` (native_tet → tet_to_poly_dual harness,
core/generator/native_poly/harness.py:89). scipy Voronoi fallback 아님(harness PASS).

측정 (N=500/1000/2000 모두 동일 — **N은 완전 inert**: dual 경로는 seed_density(=10)
고정, max_cells/target_cells는 bl_layers=0일 때 harness에 전달 안 됨, tier_native_poly.py:35):

| 불변식 | 실측 | 판정 | 게이트 |
|--------|------|------|--------|
| 1. surface coverage (on-plane 면적) | **6.000 (1.00x)** | PASS | permanent |
| 2. void (off-plane 경계 면적) | **7.588** (≤0.30 요구) | **FAIL** | xfail(strict) |
| 3. volume Σ\|cell vol\| | **1.177 (1.18x)** (0.95–1.05 요구) | **FAIL** | xfail(strict) |
| 4. degenerate cells | **0** | PASS | permanent |

부가: cells=15, faces/cell=13.8, time≈45s, skew=2.14, non_ortho=11.9°,
negative_volumes=0, mesh_ok=True, verdict=PASS_WITH_WARNINGS.
→ **기존 checker/verdict는 void·volume 결함에 blind** (총면적 트랩과 동형: on-plane은
완벽 6.0인데 dual 경계 cell이 off-plane open-wall 7.588 + cube 밖으로 bulge하여 1.18x).

## 이론적 근거 (측정·게이트 고정 카드)

- **문제 정의**: native_poly는 ROADMAP상 "~15%, 미측정". 정본 측정 프로토콜 부재로
  결함이 verdict=PASS 뒤에 숨어 있음. 총 경계면적(13.588)은 트랩 — void wall이
  면적 손실을 상쇄하므로 4대 불변식을 **독립적으로** 게이트해야 함(tet suite 교훈).
- **본 카드 아이디어**: mesher 수정 없이 (1) 정본 스모크 + (2) 4대 불변식 게이트를
  신설. tet의 |det|/6은 임의 다면체에 부적용 → hex의 **orientation-free
  centroid-apex 피라미드** 부피(`_cell_volumes`)를 그대로 재사용(poly cell도 convex
  dual이라 유효). 통과 항목은 permanent gate로 고정, 실패 항목은 실측 수치를
  docstring에 박아 xfail(strict)로 결함을 정확히 기록.
- **레퍼런스**: tests/test_native_tet_solid_volume.py (독립 3게이트 교훈),
  tests/test_native_hex_solid_volume.py (`_cell_volumes`/`_boundary_area_split`
  orientation-free 헬퍼), Owen 2007 "Intro to Polyhedral Meshing" (tet→dual).
- **혁신성**: novelty 1 / rigor 2 / impact 2 = 5. 알고리즘 혁신이 아니라 **측정
  인프라 확립** — poly quality 캠페인의 정본 baseline을 만드는 필수 선행 카드.

## 변경 (mesher 코드 수정 없음 — 측정·게이트만)

- 신규 `scripts/smoke_native_poly.py` (≤160줄, tet/hex 스모크와 **동일 1줄 출력 형식**):
  1. PipelineOrchestrator 정본 경로(tier_hint="native_poly", strict_tier=True,
     mesh_type="poly", draft). argv[1]=N(기본 500, inert이나 인터페이스 parity 유지).
  2. hex 스모크의 `_cell_volume_orientation_free` + `_face_area` + on/off-plane
     분류 재사용. 4항 + skew 1줄 출력.
  3. `solid = on_ok AND degen_ok` (현재 통과 부분집합)만 exit-code로 가드 —
     void·volume은 tet 스모크의 skew처럼 **open quality target**으로 출력만.
     "SMOKE OK (solid subset); void/volume are the open targets" / 회귀 시 non-zero.
- 신규 `tests/test_native_poly_solid_volume.py` (4 게이트):
  1. `test_..._covers_input_surface` — on-plane 면적 0.95–1.05x → **permanent** (6.000).
  2. `test_..._has_no_degenerate_cells` — degen==0 → **permanent**.
  3. `test_..._has_no_interior_voids` — off-plane ≤ 0.05*6 → **xfail(strict)**,
     docstring에 "measured 7.588 (dual open-wall)" 기록.
  4. `test_..._encloses_true_volume` — Σvol 0.95–1.05x → **xfail(strict)**,
     docstring에 "measured 1.177x (dual bulge)" 기록.
  - **module-scoped fixture**로 파이프라인 1회만 실행(≈45s) 후 4 게이트 공유
     (tet/hex는 게이트당 재실행하나 poly는 45s/run이라 공유 필수 — 3분 준수).
- 단조 가드: mesher 미변경이므로 tet/hex 회귀 0 자명. 새 게이트는 현 상태를
  정확히 반영(2 permanent PASS + 2 xfail strict).

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 -m pytest tests/test_native_poly_solid_volume.py -q
python3 scripts/smoke_native_poly.py            # ≈45s, 1줄 출력, exit 0
```

## 합격 기준 (validator 가 평가)

- 스모크 3분 내 완주, exit 0, tet/hex 스모크와 동일 출력 포맷.
- 게이트 테스트: surface·degen 2건 permanent PASS, void·volume 2건 xfail(strict)
  (xpass 나면 결함이 사라진 것 → strict가 실패시켜 카드 갱신 요구 = 의도된 안전망).
- 실측 수치가 docstring에 정확히 기록 (void 7.588, volume 1.177x, cells 15).
- tet/hex 기존 테스트 회귀 0 (mesher 미변경으로 자명).

## 카드 시퀀스 위치

- native_poly solid 캠페인의 **1/4** (측정·게이트 고정). 총 ~4카드 예상.
- 다음 카드 후보(POLY-S1 PASS 후): **POLY-S2** — tet→dual **open boundary cell**
  제거(off-plane void 7.588 → ~0). dual.py의 경계 cell capping(누락 neighbour 면을
  입력 표면으로 close)로 void gate를 xfail→permanent 승격. 그 뒤 POLY-S3(volume
  1.18x→1.0 boundary bulge clip), POLY-S4(skew/non-ortho quality).
