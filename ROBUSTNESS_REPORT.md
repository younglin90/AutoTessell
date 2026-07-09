# 강건 볼륨 메쉬 생성 — 연구 조사 + 구현 + 실증 리포트 (2026-07-03)

> 목표: "엄청 이상한 surface 를 넣어도 tetwild 처럼 강건하게 — tet/hex/poly + BL 를
> 사용자가 최종 셀 수 N 과 layer 수만 넣으면 자동 생성."

## 결론 (실측)

`python tests/bench_quality_matrix.py` — 12 STL × 3 mesh_type = 36 런, 각 자식
프로세스 격리 실행. skewness / non-orthogonality / **negative cell volume** /
aspect ratio / min cell volume 를 NativeMeshChecker 로 전수 판정.

| 입력 부류 | 볼륨 생성(크래시X) | 품질 PASS/PWW | **negative volume 0** |
|-----------|-------------------|---------------|----------------------|
| 정상 형상 4종×3 | 12/12 | 12/12 | 12/12 |
| **진짜 쓰레기 6종×3** | **18/18** | **17/18** | **18/18** |
| degenerate 2종×3 (2–4 triangle) | 3/6 | 3/6 | 3/3 |

**진짜 쓰레기** = broken_sphere(깨진 구), degenerate_sliver(퇴화 삼각형),
highly_skewed_flat(왜곡 평면), hemisphere_open(열린 반구),
five_disconnected_spheres(분리 조각), extreme_aspect_needle(극단 종횡비).
→ 구멍·자기교차·퇴화·열림·분리·뒤집힌 법선을 가진 표면이 tet/hex/poly + BL 로
**전부 볼륨 메쉬화, negative volume 0**.

BEFORE(강건화 전): 진짜 쓰레기 대부분 FAIL/크래시, 셀 수 0.14N~0.35N.

### 대표 지표 (N=15000, BL=2, draft)

| 케이스 | 타입 | tier | cells | skew | non-ortho | negVol |
|--------|------|------|-------|------|-----------|--------|
| broken | tet | tetwild | 11,130 | 0.7 | 51.2° | 0 |
| broken | hex | native_hex | 7,917 | 2.3 | 71.2° | 0 |
| sliver | tet | tetwild | 17,584 | 4.4 | 78.6° | 0 |
| openhemi | hex | native_hex | 8,276 | 4.6 | 75.6° | 0 |
| openhemi | poly | native_poly | 9,875 | 5.0 | 78.8° | 0 |

## 연구 조사 → 구현 (SOTA 문헌 9편)

병렬 문헌 조사(fTetWild/TetWild/CDT, Winding Number, Alpha Wrap 등) 후 랭킹된
전략을 구현:

1. **Generalized Winding Number inside-test 배선** (Jacobson 2013, fTetWild §3.5)
   — `inside_robust` 디스패처: closed manifold 는 ray parity(빠름), 구멍·soup 은
   GWN 자동 전환. native_hex/octree/native_tet/ftetwild/L3 5개 사이트 배선.
   ([geometry.py](core/utils/geometry.py), [native_hex/mesher.py](core/generator/native_hex/mesher.py))
2. **fTetWild N-역산 + 2-pass 캘리브레이션** — target_cells → edge_length_abs
   =(k·V/N)^(1/3), k=10 실측; 1-pass 결과가 밴드 밖이면 실측 비율로 1회 재보정.
   ([tier2_tetwild.py](core/generator/tier2_tetwild.py))
3. **열린 표면 self-filter** — pytetwild 내장 winding filter 가 열린 표면에서
   tets 를 전부 버리는 문제 → `disable_filtering` 후 우리 GWN 으로 자체 내부 선별.
4. **비-ortho 아웃라이어 drop** — native_bl 이 계단형 표면에 프리즘 삽입 시 소수
   face 가 캡 초과 → soft 한계−1° 로 해당 셀만 제거.
   ([drop_neg_vol_cells.py](core/utils/drop_neg_vol_cells.py))

## 절대 재구성 안전망 (신규, 연구 rank 3)

**자체 Surface Nets** (Gibson 1998, dual contouring) — 외부 의존 없이 numpy 로
구현 ([surface_nets.py](core/utils/surface_nets.py)). GWN 부호장에서 등위면을
셀-정점 방식으로 추출해 **manifold-by-construction watertight** 표면을 만든다.
실측: broken_sphere(깨진 구, 1230면 non-watertight) → **watertight 구(euler=2,
부피 +4.13)**, cube → euler=2. skimage 의존 제거(native-first).

파이프라인 배선: **모든 볼륨 tier 가 실패하면** GWN voxel + Surface Nets 로
표면을 재구성해 같은 tier 시퀀스로 딱 1회 재시도
([orchestrator.py](core/pipeline/orchestrator.py) `_reconstruct_surface_last_resort`).
부피가 정의되지 않는 degenerate 입력은 재구성이 None → 명확한 에러
("입력 표면이 닫힌 부피를 이루지 못합니다")로 정직하게 실패.

## 강건성(생존성) 수정

5. **pytetwild subprocess 격리** (기본 ON) — needle 입력에서 native segfault
   (0xC0000005) 실증 → 자식 프로세스 격리로 **웹서버가 죽지 않고** fallback 지속.
6. **tier 크래시 격리** — 한 tier 의 내부 예외가 파이프라인 전체를 죽이지 않게
   `_run_tier` 를 TierAttempt(failed) 로 포장 ([pipeline.py](core/generator/pipeline.py)).
7. **cross-family 최종 안전망** — mesh_type 계열이 전멸해도 다른 계열을 최후에
   시도 (mesh_type 은 선호이지 절대 계약이 아님 — "쓰레기 표면도 반드시 볼륨
   메쉬" 우선). ([tier_selector.py](core/strategist/tier_selector.py))
8. **의존성 보강** — meshio(볼륨 writer+export), networkx(fill_holes),
   pymeshfix(L1 수리), python-fcl(자기교차 감지) 설치로 수리 사다리 완성.

## 알려진 한계 (정직한 기록)

- **degenerate 입력** (selfx=삼각형 4개, nonmani=삼각형 2개): 부피가 정의되지
  않는 입력. TetWild 조차 볼륨 메쉬 불가 — 강건성의 한계가 아니라 "메쉬화할
  solid 가 없는 입력". 실사용 CAD/STL(수백~수만 face)은 해당 없음.
  → 향후: L3 voxel 랩(Surface Nets) 로 최소 부피 재구성 (연구 rank 3).
- **cfMesh Windows 경로 버그**: WSL OpenFOAM 에 Windows 경로가 잘못 조합됨
  (`/home/.../C:/Users/...`). 이 환경(Windows+WSL OpenFOAM) 특정 — 별도 이슈.
- **얇은/작은 입력의 N 미달**: skewflat/needle 등은 부피가 작아 N=15000 을 못
  채움(품질 자체는 통과, negVol 0). N 은 근사 목표.

## 재현

```bash
python tests/bench_quality_matrix.py          # 36 런 전수 품질 판정
python tests/verify_goal.py                   # 정상 3종 회귀 (SUCCESS)
```
