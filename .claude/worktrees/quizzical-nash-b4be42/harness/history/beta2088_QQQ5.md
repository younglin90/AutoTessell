# CARD QQQ5 (beta2088) — BL local thickness 활성 (collision 위험 vertex thin)

**target_engine**: tet (BL)
**모티프**: Loseille & Löhner 2013 §4 — local thickness adaptation (시퀀스 #4)

## 이론적 근거
- R25 QQQ4 PASS: `_local_thickness_factor(collision_mask, n_vertices, thin_factor=0.5)` skeleton 정의 + flag `_BL_QQQ4_LOCAL_THICKNESS=False`.
- 이번 카드 — flag True 로 활성. `_run_prism_pass` 진입 시 wall vertex 별 collision_mask 산출(QQQ3 의 front-collision 결과를 vertex 단위로 propagate) → helper 호출 → per-vertex factor → 기존 `vertex_scale_pass` 와 곱(merge).
- collision 위험 vertex 만 ×0.5 → thinner prism, 일반 vertex 1.0 유지 → 정상 영역 BL 품질 보존.
- novelty 2 (helper 활성), rigor 3 (per-vertex factor merge), impact 3 (충돌 영역 prism collapse 회피) → 합 8.

## 변경
- 파일: `core/layers/native_bl.py`
- 함수: 모듈 상수 (line 55) + `_run_prism_pass` (line 933).
- 핵심 변경 (≤25줄):

  1. **line 55**: `_BL_QQQ4_LOCAL_THICKNESS = False` → `True`.

  2. **`_run_prism_pass` 초입 (line ~952, `# 5) 새 point 배열 구성` 직전)** 에 다음 블록 추가:
     ```python
     if _BL_QQQ4_LOCAL_THICKNESS and _BL_QQQ1_FRONT_COLLISION:
         try:
             # vertex 단위 collision_mask: 인접 wall vertex 와 법선이 거의 반대(dot<-0.5)
             wall_vn = np.array([vnorm[v] for v in wall_vert_indices])
             dots_v = wall_vn @ wall_vn.T
             np.fill_diagonal(dots_v, 0.0)
             coll_v = (dots_v < -0.5).any(axis=1)  # shape (Nw,)
             factors_w = _local_thickness_factor(coll_v, len(wall_vert_indices), thin_factor=0.5)
             # vertex_scale_pass 와 merge (곱); local copy 로 caller 영향 차단
             vertex_scale_pass = dict(vertex_scale_pass)
             for vi_idx, v in enumerate(wall_vert_indices):
                 vertex_scale_pass[v] = vertex_scale_pass.get(v, 1.0) * float(factors_w[vi_idx])
         except Exception as _exc:
             import logging as _lg
             _lg.getLogger(__name__).warning("native_bl_qqq5_skipped reason=%s", str(_exc)[:120])
     ```

### 변수 매핑 (R22 사고 회피)
- `_local_thickness_factor` 시그니처: `(collision_mask: np.ndarray, n_vertices: int, thin_factor: float = 0.5) -> np.ndarray` (shape `(n_vertices,)`).
- 호출부 매핑:
  - `collision_mask` ← `coll_v` (bool array shape `(Nw,)`, `Nw=len(wall_vert_indices)`).
  - `n_vertices` ← `len(wall_vert_indices)` (전체 mesh point 수가 아닌 wall vertex 수).
  - `thin_factor` ← `0.5`.
- 반환 `factors_w[vi_idx]` 는 wall_vert_indices 의 vi_idx 번째 vertex 에 대응 → `vertex_scale_pass[v]` 곱.
- `vertex_scale_pass` 는 `dict[int, float]`, `_run_prism_pass` 인자로 들어옴 → local copy 후 mutate.

## 검증 명령
```bash
timeout 60 python3 -c "from core.layers.native_bl import _local_thickness_factor, _BL_QQQ4_LOCAL_THICKNESS; print('OK', _BL_QQQ4_LOCAL_THICKNESS)"
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준
- import smoke OK 이고 flag True.
- 회귀 PASS (위 3개 pytest).
- bench 시간 ≤ 720s.
- tet+BL / hex+BL / poly+BL fail 0 (BL 분포 동등 또는 향상).
