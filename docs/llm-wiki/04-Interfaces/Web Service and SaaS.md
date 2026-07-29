---
type: interface
status: active
updated: 2026-07-26
stability: implemented
source_paths: [frontend, backend/main.py, backend/api, backend/worker, backend/mesh]
tags: [web, saas, nextjs, fastapi]
---

# 웹 서비스와 SaaS

`frontend/`는 Next.js 16·React 19 기반으로 upload/job/payment 화면과 Stripe 연결을 가진다. `backend/`는 SQL persistence, job API, download URL, payment webhook, upload, worker/Celery, object storage hook, 별도 mesh adapter를 가진 FastAPI 서비스다.

| 항목 | 로컬 desktop server | SaaS backend |
|---|---|---|
| 상태 | in-process/local temp registry | DB-backed job |
| 계산 | local pipeline task | worker/background task |
| 저장 | local file과 ZIP response | local/S3 계열 upload와 signed download |
| 결제 | 없음 | Stripe payment/webhook |
| UI | bundled vanilla web + Electron | Next.js frontend |

Frontend landing 문구는 오래된 5-tier pipeline을 설명한다. 현재 routing 명세로 사용하면 안 되며 [[Contradictions and Open Questions|불일치 원장]]에 기록돼 있다.
