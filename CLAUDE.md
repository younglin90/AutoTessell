# Tessell — CLAUDE.md

## 프로젝트 개요

STL 파일을 업로드하면 Stripe 결제 후 OpenFOAM polyMesh를 생성해 다운로드할 수 있는 SaaS 서비스.

---

## 아키텍처

```
frontend (Next.js 14)
    │  REST API
    ▼
backend/main.py (FastAPI)
    ├── POST /upload          STL 검증 → S3 업로드 → Stripe PaymentIntent 생성 → Job 생성
    ├── POST /webhook         Stripe 서명 검증 → PAID 마킹 → Celery run_mesh 태스크 enqueue
    ├── GET  /jobs/{id}       상태 폴링
    └── GET  /jobs/{id}/download  S3 presigned URL 반환

worker/tasks.py (Celery + Redis)
    └── run_mesh()
        ├── S3에서 STL 다운로드
        ├── generate_mesh() 호출 (4-tier 파이프라인)
        ├── polyMesh zip → S3 업로드
        └── 실패 시 Stripe 자동 환불 + REFUND_FAILED 마킹

mesh/generator.py
    └── 4-tier 하이브리드 메쉬 파이프라인 (아래 참조)
```

---

## 5-Tier 하이브리드 메쉬 파이프라인

### 공통 전처리 (모든 Tier 공유)

| 라이브러리 | 라이선스 | 역할 |
|-----------|---------|------|
| **trimesh** | MIT | STL 로딩, 수리, BBox 추출 |
| **pyACVD** | MIT | Voronoi 균일 surface remeshing (optional) |

pyACVD 설치 시 모든 Tier 전에 균일한 삼각형 분포로 STL 전처리 → 다운스트림 메쉬 품질 향상.
미설치 시 원본 STL 그대로 사용 (graceful fallback).

### Tier 순서

| Tier | 라이브러리 | 라이선스 | 특징 |
|------|-----------|---------|------|
| 0 | **tessell_mesh / geogram** | BSD-3-Clause | C++/pybind11 tet 메쉬, 2D+3D, 가장 빠름 |
| 0.5 | **Netgen** | LGPL-2.1 | pip 설치 가능, 자체 품질 최적화 내장 |
| 1 | **snappyHexMesh** | OpenFOAM 내장 (GPL) | hex-dominant, 외부 유동 CFD 최고 품질 |
| 2 | **pytetwild** + **MMG** | MPL-2.0 + LGPL-3.0 | 불량 STL 최후 fallback + 품질 후처리 |

### Tier별 상세

- **Tier 0**: `tessell-mesh/` 빌드 필요 (`./build.sh`). `.so` 없으면 자동 skip
- **Tier 0.5**: `pip install netgen-mesher` — Netgen → Gmsh2 .msh → `gmshToFoam`
- **Tier 1**: OpenFOAM 12 Docker 필요. 원본 STL 사용 (reference surface)
- **Tier 2**: `mmg3d` binary가 PATH에 있으면 MMG 품질 후처리 자동 적용 (Medit .mesh 경유)
- 각 tier 실패 시 case_dir 초기화 후 다음 tier 시도
- 모든 tier 종료 후 `checkMesh`로 품질 검증

---

## 디렉터리 구조

```
auto-tessell/
├── backend/
│   ├── main.py                   FastAPI 앱 진입점
│   ├── config.py                 Pydantic settings (DB, Redis, S3, Stripe)
│   ├── db.py                     SQLAlchemy Job 모델 + JobStatus enum
│   ├── api/
│   │   ├── upload.py             POST /upload
│   │   ├── payment.py            POST /webhook (Stripe)
│   │   ├── jobs.py               GET /jobs/{id}
│   │   └── download.py           GET /jobs/{id}/download
│   ├── worker/
│   │   ├── celery_app.py         Celery + Redis 설정
│   │   └── tasks.py              run_mesh Celery 태스크
│   ├── mesh/
│   │   ├── generator.py          4-tier 파이프라인 핵심
│   │   ├── validator.py          STL 바이너리/ASCII 검증
│   │   ├── stl_utils.py          BBox, trimesh 로딩·수리
│   │   ├── openfoam_config.py    blockMeshDict, snappyHexMeshDict 생성
│   │   └── checkmesh.py          checkMesh 출력 파싱
│   ├── tests/
│   │   ├── test_stl_validator.py
│   │   ├── test_checkmesh.py
│   │   ├── test_stripe_refund.py
│   │   └── test_generator.py
│   ├── Dockerfile.api
│   ├── Dockerfile.worker         openfoam/openfoam12-paraview510 기반
│   └── requirements.txt
├── tessell-mesh/                 C++/Python 하이브리드 확장 모듈
│   ├── CMakeLists.txt            FetchContent: pybind11 + geogram + CDT
│   ├── build.sh                  빌드 스크립트 (Ninja)
│   ├── include/tessell/
│   │   ├── types.hpp             Vec2, Vec3, Tri, Tet, Mesh2D, Mesh3D
│   │   ├── mesh2d.hpp            triangulate_2d() 선언
│   │   ├── mesh3d.hpp            tetrahedralize_stl/surface() 선언
│   │   └── of_writer.hpp         write_openfoam_2d/3d() 선언
│   ├── src/
│   │   ├── mesh2d.cpp            CDT 2D 삼각분할
│   │   ├── mesh3d.cpp            geogram 3D 사면체화
│   │   ├── of_writer.cpp         OpenFOAM polyMesh 파일 기록
│   │   └── bindings.cpp          pybind11 Python 바인딩
│   └── tests/
│       ├── test_mesh2d.cpp       CDT 단위 테스트 (doctest)
│       └── test_of_writer.cpp    OpenFOAM writer 단위 테스트
├── frontend/
│   ├── app/
│   │   ├── page.tsx              랜딩 페이지
│   │   ├── mesh/new/page.tsx     STL 업로드 + Stripe 결제 UI
│   │   └── mesh/[jobId]/page.tsx 상태 폴링 + 다운로드
│   └── lib/api.ts                typed API 클라이언트
└── docker-compose.yml            db + redis + api + worker
```

---

## Job 상태 머신

```
PENDING → PAID → PROCESSING → DONE
                            ↘ FAILED → (Stripe 환불 시도)
                                     → REFUND_FAILED (환불도 실패)
```

---

## tessell-mesh 빌드 방법

```bash
# Linux / Docker 환경에서 실행
cd tessell-mesh
./build.sh

# 빌드 결과: backend/mesh/tessell_mesh.so
```

CMake FetchContent로 자동 다운로드되는 의존성:
- **pybind11** v2.13.1
- **geogram** v1.9.5 (GEOGRAM_WITH_GRAPHICS=OFF, GEOGRAM_LIB_ONLY=ON)
- **CDT** v1.4.5

---

## tessell_mesh Python API

```python
import tessell_mesh as tm

# 3D: STL → tet mesh → OpenFOAM
result = tm.tetrahedralize_stl("input.stl", quality=2.0)
result.write_openfoam("/path/to/case")
print(result.num_vertices, result.num_tets)

# 3D: 직접 surface mesh에서 생성
result = tm.tetrahedralize_surface(vertices, triangles, quality=2.0)

# 2D: CDT 삼각분할 → OpenFOAM (1-cell 두께 extrude, empty BC)
result = tm.triangulate_2d(boundary, holes=[], extrude_thickness=0.1)
result.write_openfoam("/path/to/case")
print(result.num_vertices, result.num_triangles)
```

---

## OpenFOAM 도메인 설정

snappyHexMesh Tier에서 STL BBox 기반으로 자동 계산:

| 방향 | 비율 |
|------|------|
| 업스트림 (x-) | 10L |
| 다운스트림 (x+) | 20L |
| 측면 (y±, z±) | 5L |
| 전체 도메인 | 30L × 10L × 10L |

`locationInMesh`는 geometry 업스트림 외부에 자동 배치.

---

## 라이선스 정책 (SaaS 상업용)

| 라이브러리 | 라이선스 | SaaS 사용 |
|-----------|---------|---------|
| trimesh | MIT | ✅ 안전 |
| pyACVD | MIT | ✅ 안전 |
| geogram | BSD-3-Clause | ✅ 안전 |
| CDT | MPL-2.0 | ✅ 안전 (소스 수정분만 공개) |
| pytetwild | MPL-2.0 | ✅ 안전 |
| Netgen | LGPL-2.1 | ✅ 안전 (동적 링크) |
| MMG | LGPL-3.0 | ✅ 안전 (동적 링크) |
| meshio | MIT | ✅ 안전 |
| OpenFOAM | GPL v3 | ✅ 서버 내부 실행, 배포 아님 |
| pymeshfix | LGPL | ✅ 동적 링크 시 안전 |
| TetGen v1.6+ | AGPL | ❌ SaaS 불가 |
| Gmsh | GPL | ❌ SaaS 불가 (CLI는 가능하나 주의) |

---

## 개발 환경

- Python 3.12
- Node.js 20 (Next.js 14)
- OpenFOAM 12 (Docker: `openfoam/openfoam12-paraview510`)
- PostgreSQL 16
- Redis 7
- C++17 (tessell-mesh, CMake + Ninja)

### 테스트 실행

```bash
# Python (Windows — python3.14 경로 사용)
/c/Users/user/AppData/Local/Python/bin/python3.14 -m pytest backend/tests/ -v

# C++ (Linux/Docker)
cd tessell-mesh/build && ctest --output-on-failure
```

---

## Stripe 웹훅 설정

`payment_intent.succeeded` 이벤트만 처리. 웹훅 시크릿은 `STRIPE_WEBHOOK_SECRET` 환경 변수.

실패 시 자동 환불 흐름:
1. Celery 태스크 실패 → `_mark_failed_and_refund()` 호출
2. `stripe.Refund.create(payment_intent=pi_id)` 시도
3. Stripe도 실패 시 → Job 상태 `REFUND_FAILED` (수동 처리 필요)

---

## 환경 변수

```env
DATABASE_URL=postgresql://user:pass@db:5432/tessell
REDIS_URL=redis://redis:6379/0
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=tessell-stl
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
MAX_STL_SIZE_MB=50
MAX_JOBS_PER_USER=2
```
