# Codex WildMesh GUI Crash Session Summary — 2026-04-19

이 문서는 `test_cube.stl`을 GUI에서 열고 WildMesh 엔진으로 실행할 때 발생한
GUI 종료, `BadWindow`, `Segmentation fault (core dumped)` 관련 조사와 개선
내용을 기록한다.

## 배경

- 사용자가 실제 GUI 실행 중 다음 문제를 보고했다.
  - Qt QSS 경고: `Unknown property box-shadow`
  - X11/Qt 오류: `BadWindow (invalid Window parameter)`
  - WildMesh 실행 시 프로세스 종료: `Segmentation fault (core dumped)`
- `test_cube.stl` + WildMesh 코어 파이프라인은 CLI 직접 실행에서 PASS까지 완료되는
경로가 확인됐다.
- 따라서 문제를 두 갈래로 분리했다.
  - GUI/VTK/PyVistaQt 미리보기 native window 문제
  - `wildmeshing` native binding이 GUI 프로세스 내부에서 segfault를 내는 문제

## 수행한 개선

### 1. Qt QSS 경고 제거

- 파일: `desktop/qt_app/main_window.py`
- Qt stylesheet가 지원하지 않는 `box-shadow` 속성을 제거했다.
- 관련 테스트를 추가했다.
  - `tests/test_qt_app.py::test_main_window_qss_avoids_unsupported_box_shadow`

### 2. PyVistaQt/VTK 실행 안정화 옵션 추가

- 파일: `desktop/qt_app/mesh_viewer.py`
- headless/offscreen 환경 감지 helper를 추가했다.
- `AUTOTESSELL_STATIC_VIEWER=1` 환경변수로 PyVistaQt interactive viewer 대신
  정적 PNG viewer를 강제할 수 있게 했다.
- `QT_QPA_PLATFORM=offscreen` 또는 display 없는 Linux 환경에서는 PyVistaQt
  native window를 만들지 않도록 했다.

### 3. OpenFOAM polyMesh 미리보기 crash 위험 축소

- 파일: `desktop/qt_app/mesh_viewer.py`
- 기존 interactive viewer는 결과 case에 `constant/polyMesh`가 있으면
  `pv.OpenFOAMReader`로 polyMesh를 직접 읽었다.
- 이 경로가 일부 X11/VTK 조합에서 native crash를 유발할 수 있어,
  `foamToVTK`가 생성한 preview 파일을 우선 사용하도록 변경했다.
- 우선순위:
  - `*.vtu`
  - `*.vtk`
  - `*.vtp`
  - `*.vtm`
- polyMesh 직접 preview는 기본 비활성화했다.
- 필요할 때만 `AUTOTESSELL_POLYMESH_DIRECT_PREVIEW=1`로 opt-in 가능하다.

### 4. WildMesh native segfault 격리

- 파일: `core/generator/tier_wildmesh.py`
- 기존 문제:
  - 부모 GUI 프로세스가 `wildmeshing` native extension을 직접 import하고
    `Tetrahedralizer`를 실행했다.
  - native segfault는 Python `try/except`로 잡을 수 없어 GUI 프로세스 전체가
    종료됐다.
- 변경 후:
  - 부모 프로세스는 `importlib.util.find_spec("wildmeshing")`로 설치 여부만 확인한다.
  - 실제 `wildmeshing` import와 tetrahedralize 실행은 별도 Python subprocess에서 수행한다.
  - 입력/출력은 임시 `.npz` 파일로 교환한다.
  - child process가 `SIGSEGV`로 죽으면 부모는 RuntimeError로 변환한다.
  - 오류 메시지는 `wildmeshing subprocess failed: SIGSEGV (segmentation fault)` 형태가 된다.
- 기대 효과:
  - WildMesh native crash가 발생해도 GUI 전체가 죽지 않고 파이프라인 실패로 처리된다.

### 5. Compare visual test 안정화

- 파일: `desktop/qt_app/compare_dialog.py`
- 기존 placeholder histogram seed가 전체 임시 경로 문자열에 의존했다.
- `pytest-2`, `pytest-11` 같은 임시 디렉터리 번호가 바뀌면 visual diff가 발생했다.
- seed를 `path.name` 기반으로 고정해 visual baseline이 흔들리지 않게 했다.

## 추가한 테스트

- 파일: `tests/test_qt_app.py`
  - `test_mesh_viewer_runtime_detects_headless_and_static_flag`
  - `test_main_window_qss_avoids_unsupported_box_shadow`
  - `test_mesh_viewer_prefers_foam_to_vtk_preview`
  - `test_interactive_polymesh_load_uses_preview_before_openfoam_reader`
  - `test_interactive_polymesh_direct_preview_is_opt_in`

- 파일: `tests/test_generator.py`
  - WildMesh 성공 mock 테스트를 subprocess 경계 mock 방식으로 수정
  - `test_tier_wildmesh_subprocess_segfault_is_reported`

## 검증 결과

### 통과

```bash
python3 -m pytest tests/test_generator.py -k "wildmesh" -q
# 9 passed
```

```bash
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q
# 193 passed, 8 skipped
```

```bash
env NUMBA_CACHE_DIR=/tmp/numba_cache python3 -m pytest tests/test_generator.py -q
# 122 passed, 1 skipped
```

### 실제 파이프라인 확인

다음 조건으로 `test_cube.stl` WildMesh 코어 파이프라인을 실행했다.

- `quality_level=draft`
- `tier_hint=wildmesh`
- `max_iterations=1`
- `surface_remesh=True`
- WildMesh params:
  - `wildmesh_epsilon=0.002`
  - `wildmesh_edge_length_r=0.06`
  - `wildmesh_stop_quality=20.0`
  - `wildmesh_max_its=40`

결과:

- WildMesh subprocess tetrahedralize 완료
- OpenFOAM polyMesh 작성 완료
- `checkMesh` 실행 완료
- `foamToVTK` 실행 완료
- 최종 `PASS`

## 확인된 실패 및 환경 이슈

### 1. `BadWindow` / X11 window 오류

- 사용자가 실제 GUI 실행 중 보고했다.
- 원인 후보:
  - WSL/X server 상태
  - Qt platform plugin 상태
  - PyVistaQt/VTK native window 생성
- 대응:
  - `AUTOTESSELL_STATIC_VIEWER=1` 정적 viewer 우회 옵션 추가
  - `polyMesh` 직접 preview 대신 `foamToVTK` preview 우선 사용

### 2. `Segmentation fault (core dumped)`

- 사용자가 `test_cube.stl` + WildMesh GUI 실행 중 보고했다.
- 원인 후보:
  - `wildmeshing` native binding
  - PyVistaQt/VTK preview
- 대응:
  - WildMesh native 호출을 subprocess로 격리
  - 부모 GUI 프로세스에서 `wildmeshing` 직접 import 제거
  - preview 경로에서 `OpenFOAMReader` 직접 사용 기본 비활성화

### 3. `tests/test_generator.py` 전체 실행 중 classy_blocks import 실패

- 일반 실행에서 다음 실패가 있었다.
  - `RuntimeError: cannot cache function '_rotation_matrix': no locator available`
- 원인:
  - `classy_blocks` import 시 `numba` cache locator가 현재 환경에서 잡히지 않음
- 우회:
  - `NUMBA_CACHE_DIR=/tmp/numba_cache` 지정 시 전체 generator 테스트 통과
- 이번 WildMesh 수정과 직접 관련 없는 환경성 실패로 판단했다.

### 4. 외부 리메시 도구 경고

`test_cube.stl` 실제 파이프라인 실행 중 다음 외부 도구 실패가 로그에 남았다.

- `quadwild`
  - `mamba` lock file 관련 실패
  - `/home/younglin90/.cache/mamba/proc/proc.lock`
- `vorpalite`
  - geogram stacktrace와 함께 실패

파이프라인은 fallback으로 `pyacvd + igl_laplacian` 경로를 사용했고 최종 PASS했다.

## 사용자 실행 권장 명령

기본 GUI 실행:

```bash
unset QT_QPA_PLATFORM
python3 -m desktop.qt_app
```

PyVistaQt/VTK 창 문제가 계속되면 정적 viewer로 실행:

```bash
unset QT_QPA_PLATFORM
AUTOTESSELL_STATIC_VIEWER=1 python3 -m desktop.qt_app
```

polyMesh 직접 OpenFOAMReader preview를 실험적으로 켜려면:

```bash
unset QT_QPA_PLATFORM
AUTOTESSELL_POLYMESH_DIRECT_PREVIEW=1 python3 -m desktop.qt_app
```

단, 이 옵션은 `BadWindow` 또는 native crash 재현 가능성이 있어 기본 사용은 권장하지 않는다.

## 현재 작업트리 참고

이번 세션의 관련 수정 파일:

- `core/generator/tier_wildmesh.py`
- `desktop/qt_app/mesh_viewer.py`
- `desktop/qt_app/main_window.py`
- `desktop/qt_app/compare_dialog.py`
- `tests/test_generator.py`
- `tests/test_qt_app.py`
- `docs/plans/codex-wildmesh-gui-crash-summary-2026-04-19.md`

기존부터 작업트리에 남아 있던 별도 변경:

- `.claude/scheduled_tasks.lock` 삭제
- `products/web/reference-ui/next-env.d.ts` 수정

이 두 항목은 이번 GUI/WildMesh crash 대응과 무관하므로 건드리지 않았다.

## 남은 확인 사항

- 사용자가 실제 GUI에서 `test_cube.stl`을 열고 WildMesh 엔진으로 다시 실행해
  segfault 대신 정상 완료 또는 실패 메시지로 남는지 확인해야 한다.
- 그래도 GUI 프로세스가 죽으면 WildMesh가 아니라 PyVistaQt/VTK preview 또는 X11 쪽
  native crash 가능성이 높다.
- 그 경우 `AUTOTESSELL_STATIC_VIEWER=1` 실행 로그와 crash 시점을 기준으로
  viewer 초기화 단계인지, 결과 preview 단계인지 다시 분리해야 한다.
