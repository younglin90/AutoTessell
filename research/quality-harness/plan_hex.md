# CARD BETA_HEX_WALLFIT (beta1) — 곡면 벽 per-vertex 가드 snap (staircase 제거)

**target_engine**: hex
**모티프**: snappyHexMesh snap-step + fTetWild envelope(ε 내 이동) — 경계 정점을 입력 곡면에 투영하되 solid 불변식·incident-cell 양의부피를 per-vertex 가드.

## 이론적 근거 (측정 기반)

- **문제 정의**: Cartesian hex 는 축비정렬 곡면을 계단(staircase)으로 근사. cylinder(true r=0.5)
  side-wall 정점의 반경편차 dev = |r-0.5|. worst corner dev ≈ 0.5·edge (측정 0.0466 ≈ 0.64·edge).
- **실측 (이 planner, N=2000)**:
  - draft/standard/fine 모두 `wall_dev_max=0.0466` 동일 (mean 0.0214/0.0173/0.0158).
    → snap 은 돌지만 worst corner 는 항상 skip. 원인: `snap.py` 의 cap = max_snap_ratio·edge
    (iterative 0.3, boundary 0.5) < worst dev(0.64·edge) → `if dist>cap: n_skipped_beyond_cap; continue`.
  - 두 snap 함수 cap 을 0.8 로 올리면 standard `wall_dev_max 0.0466→0.0235` (mean 0.0058).
    cap 1.0 은 0.0353 로 **역행(비단조)** — 무딘 cap 상향은 취약(정점이 먼 삼각형에 오투영/overshoot).
  - cube smoke PASS 불변(정점이 평면 위 → snap 거리 ~0).
- **핵심 아이디어**: 무딘 cap 이 아니라 **per-vertex 단조·solid 가드 wall-fit**.
  1. boundary side-wall 정점 중 dev>tol 인 것만 대상.
  2. 각 정점 v 를 closest-point-on-input-triangle p 로 투영 시도 (envelope: |p-v| ≤ r·edge).
  3. **수락 조건 (둘 다)**: (a) v→p 가 v 의 표면거리 **엄격 감소** (비단조 제거),
     (b) v 의 모든 incident hex 의 signed volume 이 여전히 > eps (붕괴/역전 금지).
     하나라도 위반 → 그 정점만 revert (기존 전역 skew-revert 대체, 국소화).
  4. 2-3 iter 반복 → 새 worst 도 흡수, dev 단조 비증가.
- **레퍼런스**: OpenFOAM snappyHexMesh `snapMesh` (point projection + validation),
  fTetWild Hu2020 §3.2 envelope, Garimella2003 collision-guarded extrusion. 코드: `snap.py`
  `_closest_point_on_triangle`(L29), `mesher.py` `_count_neg_vol_hex`(L342), `_build_hex_adjacency`(L33).
- **혁신성**: novelty 2 (guarded 단조 wall-fit, 기존 blunt-cap→per-vertex envelope 가드),
  rigor 2 (dist 엄격감소 + incident 양부피 → 단조·solid 보장), impact 2 (유일한 hex fidelity 격차 해소). 합 6.

## 변경

- 파일: `core/generator/native_hex/mesher.py` (단일 파일)
- 함수: 신규 helper `_wall_fit_snap(pts, hexes, V, F, target_edge, tol, ratio, iters)` +
  `snap_boundary` 블록(L1057~1109) 말미에서 호출.
- 핵심 변경 (≤80줄):
  1. `_build_hex_adjacency` 로 boundary_verts, 그리고 vert→incident-cell map 구성(1회).
  2. tris(V[F]) 로 KDTree; 각 boundary vert 의 현재 표면거리 계산.
  3. iter 루프: dev>tol 정점만 `_closest_point_on_triangle` 투영(cap ratio·edge, ratio≈1.0).
     trial 이동 후 incident hex signed-vol(기존 `_hex_signed_vol` L285 재사용) 전부 >eps &&
     새 표면거리 < 기존 → accept, 아니면 그 정점 좌표 revert.
  4. cube 조기탈출: iter0 에서 이동 정점 0 이면 즉시 return (비용 0).
- 단조 가드: per-vertex — (표면거리 엄격감소) AND (incident signed-vol>eps). 전역 revert 아님.
  기존 L1085~1104 전역 skew-revert 는 legacy snap 용으로 **유지**(wall-fit 은 그 뒤 별도 가드).

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
cd "//wsl.localhost/ubuntu/home/younglin90/work/claude_code/AutoTessell"
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 timeout 300 python3 -m pytest tests/test_native_hex_solid_volume.py -q
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 timeout 180 python3 scripts/smoke_native_hex.py 2000
```

## 합격 기준 (validator 가 평가)

- **cylinder wall_dev**: `test_native_hex_curved_wall_fidelity` 를 **standard 모드**로 실행
  (criterion 허용 "standard 또는 이 카드가 켜는 모드", 또한 xfail reason 이 "standard/fine snap path" 명시).
  `wall_dev_max ≤ 0.02` (assert 임계 불가침) + n_side≥20. **XPASS 시 xfail 마커 제거**(strict xfail → 일반 test).
  - 테스트 편집 허용 범위: `quality_level="draft"→"standard"` + `@pytest.mark.xfail(...)` 제거 **뿐**.
    0.02 assert / _cylinder_wall_deviation / 셀수는 불변. (draft 유지 시도 가능하나 draft 는 octree·snap 부재로
    from-scratch 가드 snap 이 worst corner 를 못 옮길 위험 — standard 가 실측상 안전.)
- **solid 4불변식 유지** (표면보존 최우선): smoke_native_hex cube = surface 6.000 / void 0 /
  vol 1.000 / degen 0 / verdict PASS 그대로. cylinder 도 표면덮임=입력면적·void 0 유지
  (가드가 정점을 입력 표면 **위로만** 이동 → 덮임 개선, 악화 불가; neg-vol 0 유지).
- **skew 유한/양호**: standard cylinder `max_skewness` 유한·역전 0 (per-vertex 붕괴 거부).
- **cube 회귀 금지**: cube 4게이트(test L181/200/217/237) 전부 PASS.
- bench 시간 ≤ 기존 +15% (cube 조기탈출로 곡면 없는 케이스 비용 0; standard hex 64.2s 기준).

## 위험·계측 노트 (maker 필독)

- 가드가 표면보존 불변식과 충돌 가능 — **snap 은 정점을 입력 표면으로만 투영**하므로 원리상
  덮임 악화·void 생성 불가. 그래도 maker 는 snap 후 cylinder 표면덮임/void 를 **실측**해 기록.
- cap 비단조성(0.8→0.0235, 1.0→0.0353) 은 **dist 엄격감소 수락조건**으로 제거됨 — 이게 카드 본질.
  단순 cap 상향(snap.py 기본값 변경)만 하는 카드는 금지(비단조·전역revert 취약, 이미 실측 실패).
- 목표 <0.02 미달 시(예 0.0235 에서 정체): iter 증가 또는 ratio 상향 전에 **왜 특정 corner 가
  거부되는지(incident 역전 vs dist 미감소) 로그로 분해**해 벽 기록. 임계 완화·평가자 수정 금지.

## 카드 시퀀스 위치

- "hex 곡면 fidelity(staircase 제거)" 시퀀스 1/2.
- 다음 카드 후보(PASS 후): BETA_HEX_CURV_OCTREE — adaptive octree 가 곡면 벽에서
  실제 세분 안 됨(n_side 가 draft=std=fine 624 동일, 실측). 곡률기반 boundary refinement 로
  staircase 진폭 자체를 축소(snappyHexMesh castellated refinementSurfaces curvature) → wall-fit 부담 경감.
