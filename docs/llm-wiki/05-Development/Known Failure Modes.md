---
type: development
status: active
updated: 2026-07-26
stability: contract
source_paths: [.claude/rules/lessons-learned.md, .claude/rules/coding-style.md, core/pipeline/orchestrator.py]
tags: [operations, debugging, safety]
---

# 알려진 실패 유형

## 환경과 프로세스

- Windows PowerShell이 subprocess 출력을 CP949로 해석할 수 있으므로 경계에서 UTF-8을 강제한다.
- WSL과 Windows interpreter는 package·extension을 공유하지 않는다.
- UNC path는 일부 Node/npm flow를 깨므로 frontend tool은 WSL의 `/home/...`에서 실행한다.
- PyTetWild 계열 native library는 segfault할 수 있다. Worker subprocess는 필수 격리다.
- Heavy native-tet pytest를 같은 interpreter에서 반복하면 성공 뒤 crash할 수 있다.
- Background thread의 PyVista/VTK가 SIGSEGV를 일으킨 전례가 있어 evaluator는 direct polyMesh parsing을 선호한다.

## 알고리즘 실패 패턴

- Invalid local cell 삭제가 새 void boundary를 만들 수 있다.
- Vertex insertion/remap 전 lock을 재사용하면 진짜 boundary가 보호되지 않는다.
- Convex-hull rescue가 hole/genus를 메워 그럴듯하지만 틀린 mesh를 만들 수 있다.
- 공유 poly face를 cell마다 독립 생성하면 interface mismatch와 void가 생긴다.
- Snap이 wall distance를 줄이는 동시에 wall-normal thickness를 무너뜨려 skew/inversion을 악화할 수 있다.
- Global max metric만으로는 손상이 한 cluster인지 분산인지 알 수 없다. 메커니즘 선택 전 concentration을 측정해야 한다.

## 작업트리 안전

저장소에는 staged/unstaged WIP가 대량으로 공존한다. 격리는 path-scoped stash, 분리 커밋은 interactive staging을 사용한다. 진단 편의를 위해 destructive reset/checkout으로 사용자 작업을 버리면 안 된다.
