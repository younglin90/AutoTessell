# CARD BOOLMERGE3 (S2 — card 3/N) — orchestrator 다중-입력 + 게이트 완화 (2-surface tet union)

**target_engine**: pipeline/server (native_tet 경로) — 최초로 사용자 경로를 바꾸는 카드
**모티프**: fTetWild §3.6 volume-level union. BOOLMERGE1/2 가 만든 판정을 사용자
파이프라인에 배선한다. **단, 조사 결과 "mesher.py:1311 에 filter_tets_to_union 연결"
은 최소 변경이 아니었다** — 아래 근거로 더 안전한 배선으로 좁힌다.

## 조사 근거 (실측/코드 — 재검증됨)

- **표면은 mesher 가 아니라 단일 파일로 진입한다**: `_tier_native_common.run_native_tier`
  `:313` 이 `read_stl(preprocessed_path)` 로 **한 파일**을 읽어
  `runner_fn(m.vertices, m.faces, ...)` 호출. orchestrator→MeshGenerator→tier→harness
  →mesher 5-홉 전부 단일 (V,F). `merge_surfaces: list[(V,F)]` 를 mesher 까지
  내리려면 5개 파일을 고쳐야 하고(≤80줄 위배), `tier_specific_params` 경로는
  **JSON 직렬화 allowlist**(`_TIER_PARAM_KEYS`, `run_native_tier:350`; strategy 는
  `mesh_strategy.json` 으로 저장됨)라 numpy 배열을 실을 수 없다.
- **seeding 은 union bbox 를 덮어야 한다**: mesher 는 입력 (V,F) bbox 로 seed 한다.
  두 번째 body 를 filter 만 union 으로 바꿔도 seed 가 없어 tet 이 안 생긴다.
- **결론(핵심 통찰)**: GWN 은 가법적이다 — 바깥 방향 폐곡면 A,B 에 대해
  `wn_{A∪soup}(p) = wn_A(p)+wn_B(p)` → 겹침 2, 단독 1, 바깥 0. 기존
  `_inside_winding_number`(`mesher.py:1313`, threshold 0.5)를 **결합 soup** 에 그대로
  적용하면 union 이 된다. 즉 두 STL 을 하나로 concat 해 기존 단일-경로에 흘려보내면
  seeding(=union bbox)·filter(=union) 가 **mesher 무변경**으로 동시에 해결된다.
  이는 BOOLMERGE1 `inside_union_winding_number` 와 허용오차(계단화 ±3~9%) 내 동치.

## 이론적 근거 / 혁신성

- pre-merge 는 원본 삼각형을 **수정하지 않고 concat 만** 한다(index offset) → 표면보존
  불변식 1 을 구조적으로 보존(no_repair 로 리메쉬 억제). 내부 겹침벽 face 는 union
  내부 tet 사이에 놓여 **internal face** 가 되지 filter 후 boundary patch 가 안 된다
  → 단일 병합 영역.
- explicit `filter_tets_to_union`(per-surface provenance)은 intersection/difference·
  per-patch BL 에 필요하나, union 만 요구하는 지금은 5-홉 plumbing 을 정당화 못 함 →
  BOOLMERGE4+ 로 명시 이월. 본 카드는 가법성으로 동치 결과를 **무변경 mesher** 로 얻음.
- novelty 2(첫 사용자-경로 병합) / rigor 2(가법성 증명 + e2e 실측 부피 수렴) /
  impact 3(게이트 실제 완화, tet 2-surface union 사용 가능). 합 7 — 진행.

## 변경 (2파일, ~55줄 — 사용자 경로 최초 변경이라 예외적으로 2파일)

1. **`core/pipeline/orchestrator.py`** `run()` (`:80`):
   - 신규 파라미터 `additional_input_paths: list[Path] | None = None` (default None →
     기존 단일-경로 호출자 CLI/GUI 완전 무변경, **하위호환 최우선**).
   - `run()` 최상단(analyze 전)에 가드: `additional_input_paths` 가 있으면
     `_premerge_surfaces_for_union([input_path, *additional_input_paths], work=output_dir)`
     로 결합 STL 생성 → `input_path` 를 그것으로 치환 + `no_repair=True`,
     `surface_remesh=False` 강제(원본 삼각형 보존·리메쉬 억제).
   - 신규 헬퍼 `_premerge_surfaces_for_union(paths, work)` (~28줄): 각 경로
     `read_stl` → vertices concat(누적 offset 으로 faces 재인덱싱) →
     `write_stl_binary`(`core/utils/stl_writer.py`) 로 `output_dir/_work/_merged.stl`.
     docstring 에 GWN 가법성·BOOLMERGE1/2 인용, union 만 명시.
2. **`desktop/server.py`** 게이트(`:919-936`):
   - `n_surfaces >= 2` 일 때: `mesh_type == "tet" and n_surfaces == 2` 이면 **허용** —
     `run_kwargs["additional_input_paths"] = [Path(job["surfaces"][1]["path"])]`
     설정 후 정상 진행. 그 외(n>2, 또는 tet 아님/auto)는 **기존 "boolean" 메시지로
     거부**(문구 무변경).
- **mesher.py / tier / harness / MeshGenerator 무변경** — 5-홉 plumbing 회피.

## 단조 가드 / revert 조건

- 게이트는 **명시 `mesh_type=="tet"` + 정확히 2** 에서만 열림. `auto`/`hex`/`poly`/
  `n>2` 는 거부 유지 → 기존 계약 무손상.
- **e2e 부피 실측이 아래 band 밖이면**(no_repair 결합 soup 이 mesher 에서 뭉개지면):
  server.py 게이트 완화를 **revert**(게이트 닫힘 유지)하고 orchestrator 헬퍼만 착지 →
  BOOLMERGE4 에서 게이트 재개. (스켈레톤 안전 강등.)

## 검증 명령 (unit_tester 가 그대로 실행 — 각 측정 <3분)

```bash
python -m pytest tests/test_boolean_merge_e2e.py -q
python -m pytest tests/test_desktop_server.py::TestMultiSurface -q
python -m pytest tests/test_geometry_boolean_merge.py tests/test_native_tet_boolean_merge.py -q
```

## 합격 기준 (정직한 정본 실측)

- **신규 `tests/test_boolean_merge_e2e.py`** — 두 겹치는 큐브 STL 합성
  (A=[0,1]³, B=[0.5,1.5]³, 해석 union=1.875), `PipelineOrchestrator().run(input_path=A,
  additional_input_paths=[B], mesh_type="tet", quality="draft", auto_retry="off")`:
  - polyMesh 생성 성공, `result.success is True`, `n_cells > 0`.
  - **부피**: Σ cell vol ∈ **[1.60, 2.05]** (union 1.875 ± 계단화/seeding). 그리고
    `vol_merged > vol_single_cube(≈1.0) + 0.5` — 병합이 실제로 일어남(큐브 하나 아님).
  - **4대 불변식**(정본 `NativeMeshChecker`): void 없음, degen 셀 0(또는 기존
    draft 허용치 이내), surface coverage ≥ 기존 단일-큐브 draft 분포.
  - **표면보존 불변식 1**: A 와 B **각각**의 face 샘플이 출력 경계 envelope
    (eps=bbox_diag·0.02) 내 보존 — 병합 후에도 두 원본 표면 소실 없음.
  - 실행 <3분(draft 두 큐브 ~수십초 예상).
- **게이트(`TestMultiSurface`)**:
  - `test_two_surfaces_generation_rejected`: 입력이 `mesh_type` 미지정(server default
    `"auto"`) → **여전히 거부** → **기대값 무변경**(green 유지).
  - `test_single_surface_not_gated`: **무변경**.
  - **신규** `test_two_surface_tet_union_allowed`: `mesh_type="tet"` + 2 surface →
    거부 안 됨(`_run_mesh_pipeline` mock 으로 result 도달 확인). 그리고
    `test_three_surface_still_rejected`(tet + 3) → "boolean" 거부 유지.
- **회귀 0**: 기존 단일-경로 pipeline 테스트·`TestMultiSurface` 그대로 PASS
  (default None → 코드경로 완전 동일).

## 카드 시퀀스 위치 (S2)

- 1/N ✔ BOOLMERGE1: `inside_union_winding_number`(geometry.py).
- 2/N ✔ BOOLMERGE2: `filter_tets_to_union`(native_tet, 격리 헬퍼).
- **3/N (본 카드)**: orchestrator `additional_input_paths` + pre-merge(GWN 가법성) +
  게이트를 tet 2-surface union 으로 완화. 사용자 경로 최초 변경. e2e 부피 실측.
- **4 후보**: server POST→ws 실파일 업로드 e2e + 계단화 오차 축소를 위해 결합-soup
  대신 per-surface `filter_tets_to_union` 로 교체(intersection/difference 준비) +
  envelope/Hausdorff 표면보존 gate 강화.
- **5 후보**: N>2 surface + intersection/difference(`inside_boolean_winding_number`
  + ops) + hex/poly 경로 배선 + per-patch BL(B0 patch ontology 공유).
