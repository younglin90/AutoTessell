# AutoTessell

AutoTessell은 CAD·표면 메쉬 입력을 OpenFOAM `polyMesh`로 변환하는
quality-first 메쉬 생성 도구입니다. CLI와 데스크톱 백엔드를 제공하며,
OpenFOAM이 설치되어 있지 않아도 native 품질 검사를 수행할 수 있습니다.

> 상태 안내: 이 저장소는 개발 중인 snapshot입니다. 아래의 release 상태는
> 엔진별 실제 authority·topology·quality·provenance 증거를 기준으로
> 작성했으며, fixture 통과나 셀 개수 근접만으로 release를 주장하지 않습니다.

## 현재 제품 방향

AutoTessell의 native 경로는 다음 순서를 지킵니다.

1. 입력 source와 provenance를 고정합니다.
2. topology와 shape 보존을 검사합니다.
3. positive measure 및 mesh quality를 검사합니다.
4. boundary layer을 적용하고 그 geometry/ledger를 검증합니다.
5. 마지막으로 target cell/face count를 조정합니다.

skewness, non-orthogonality, aspect ratio가 count 목표보다 우선합니다.
품질 또는 authority gate를 통과하지 못한 결과는 publish하지 않고 명시적으로
거부합니다.

## 엔진 상태

| 엔진 | 현재 상태 | BL 상태 | release 해석 |
| --- | --- | --- | --- |
| Native Tet | receipt-bound persisted child와 stage/destination 재검증 구현 | BL=0 검증, BL≥1은 writer geometry 없으면 거부 | synthetic receipt 기반 실제 route 증거; CAD/STL release corpus는 추가 필요 |
| Native Hex | native 구현 및 BL 구성요소 존재 | 실제 CAD/B-Rep boundary binding과 positive BL matrix 필요 | experimental/default-off |
| Native Poly | deterministic/protected branch 보존 | positive BL·authority·복잡 형상 matrix 필요 | experimental/default-off |
| Native Tri | strict source ingress 구성 | 독립 actual release route와 source certificate 필요 | experimental/default-off |
| Strict Quad | fixed-pair artifact/검증 구성 | 실제 source authority와 corpus 필요 | Tri와 별도 product, experimental/default-off |
| TRI+QUAD | mixed-topology fixed-pair 구성 | 자체 source/output authority와 corpus 필요 | no-op Tri clone 금지, experimental/default-off |
| Surface wall-edge BL | surface-layer 구성요소 존재 | BL=0/BL≥1 모두 실제 wall-edge geometry 증거 필요 | release 경로 아님 |

### Boundary-layer 정책

- `BL=0`: layer work가 없고 pre/post artifact identity가 보존되어야 합니다.
- `BL>=1`: writer-owned layer geometry, exact layer count, first height,
  growth ratio, face/layer lineage가 없으면 거부합니다.
- wall edge를 기준으로 하는 surface BL도 동일한 정책을 적용합니다.
- positive BL이 아직 release-ready가 아니라는 사실은 실패가 아니라
  source/geometry 증거가 없는 결과를 조용히 publish하지 않는 안전장치입니다.

## 품질 및 authority gate

release 후보는 최소한 다음을 만족해야 합니다.

- duplicate, non-manifold, open/inverted topology: `0`
- 모든 volume cell의 positive measure
- source bytes/canonical geometry와 output의 독립 digest
- feature, boundary patch, physical group, component, provenance 보존
- sealed quality policy의 non-orthogonality, skewness, aspect ratio 통과
- stage와 atomic publish 이후 destination의 재검증
- 동일 source의 독립 replay에서 deterministic artifact/certificate

현재 Tet persisted-child live smoke 측정값은 다음과 같습니다.

| Metric | 측정값 |
| --- | ---: |
| duplicate / non-manifold / inverted | `0 / 0 / 0` |
| min Tet volume | `0.16666666666666663` |
| max aspect ratio | `1.4142135623730951` |
| max non-orthogonality | `0.0°` |
| max skewness | `0.47140452079103157` |

이 값은 synthetic tetra receipt의 bounded route 증거이며, 복잡한 CAD/STL
release corpus 전체의 품질 보증을 의미하지 않습니다.

## 설치

```bash
git clone https://github.com/younglin90/AutoTessell.git
cd AutoTessell
python -m pip install -e .
```

개발 및 테스트 환경:

```bash
python -m pip install -e ".[dev,native-build]"
```

선택 기능:

```bash
python -m pip install -e ".[cad]"       # STEP/IGES/CAD adapter
python -m pip install -e ".[desktop]"   # desktop.server / Qt backend
python -m pip install -e ".[legacy-preprocess]"
```

native C++ target을 직접 빌드하려면 CMake, C++23 호환 컴파일러,
pybind11 개발 의존성이 필요합니다.

## 빠른 시작

```bash
# 입력 분석
auto-tessell analyze model.stl

# 일반 파이프라인
auto-tessell run model.stl -o ./case --quality standard

# native Tet 경로를 명시
auto-tessell run model.stl -o ./case \
  --tier native_tet --quality standard --prefer-native

# native checker 사용
auto-tessell run model.stl -o ./case \
  --tier native_tet --checker-engine native

# 생성 결과
find ./case/constant/polyMesh -maxdepth 1 -type f
```

OpenFOAM solver 실행은 생성 후 별도 단계입니다.

```bash
cd ./case
simpleFoam > log.simpleFoam
```

## 사용자 조정 parameter

target cell/face count와 boundary-layer count만으로 품질을 안정적으로
제어할 수 없으므로, 지원되는 parameter는 CLI의 `--tier-param KEY=VAL`
또는 데스크톱 parameter panel에서 조정합니다. 대표 항목은 다음과 같습니다.

- `target_cells`, `target_edge_length`
- `sliver_quality_threshold`
- `preserve_features`, `feature_angle_deg`
- `max_cells_per_axis`, `max_tet_cells`
- `bl_layers`, first-layer height, growth ratio
- native BL collision safety, feature lock, quality checks

실제 적용 여부는 결과 receipt의 requested/effective/origin 값으로 확인해야
하며, 지원되지 않는 parameter를 코드 내부 기본값으로 조용히 대체하지 않는
것이 native route의 원칙입니다.

## 개발 및 검증

```bash
# Python syntax
python -m py_compile core/generator/native_tet/receipt_stage.py

# C++ native targets
cmake -S auto_tessell_core -B auto_tessell_core/build
cmake --build auto_tessell_core/build -j2

# Tet persisted route focused regression
PYTHONPATH=auto_tessell_core/build pytest -q \
  tests/test_native_tet_production_receipt_live.py \
  tests/test_native_tet_production_receipt_ingress.py \
  tests/test_native_tet_persisted_volume_child_cpp23.py \
  tests/test_native_tet_persisted_volume_aqte_binding_cpp23_v2.py
```

round별 계획, literature review, 측정값, refusal 사례는
[`docs/qa/rounds/`](docs/qa/rounds/)에 보관합니다. Native Engine Round는
계획·문헌·public code 검토 후 구현하고, 각 round 종료 시 결과와 worktree
audit를 남깁니다.

## 입력 및 출력

주요 입력은 STL, OBJ, PLY, OFF, Gmsh mesh, VTK 및 환경에 따라 STEP/IGES/
BREP입니다. 출력은 OpenFOAM `constant/polyMesh`의 `points`, `faces`,
`owner`, `neighbour`, `boundary`와 품질/authority evidence입니다.

OpenFOAM이 없는 환경에서도 `NativeMeshChecker`와 persisted native child가
topology·volume·품질을 독립적으로 재검증합니다.

## 설계 원칙

- native core의 hot path와 topology/quality/transaction gate는 C++23을
  우선합니다. Python은 orchestration, adapter, test, evidence 수집에
  사용합니다.
- 외부 프로젝트의 알고리즘은 문헌·public source 참고 대상으로만 사용하며,
  호환성·license 검토 없이 코드를 복사하거나 runtime dependency로 만들지
  않습니다.
- protected Poly branch와 기존 사용자 변경은 삭제·merge하지 않습니다.
- quality, topology, source authority, provenance가 count 목표보다 먼저입니다.

## 관련 문서

- [`CLAUDE.md`](CLAUDE.md) — architecture와 project conventions
- [RELEASE_NOTES.md](RELEASE_NOTES.md)
- [docs/qa/native_release_authority_gate.md](docs/qa/native_release_authority_gate.md)
- [`docs/llm-wiki/05-Development/Native-Engine-Round-Log.md`](docs/llm-wiki/05-Development/Native-Engine-Round-Log.md)
- [`docs/qa/rounds/native-all-production-gate-070/`](docs/qa/rounds/native-all-production-gate-070/)
