---
type: literature-artifact-manifest
status: verified
updated: 2026-07-26
stability: measured
source_paths:
  - C:/Users/user/Downloads/xu2018.pdf
  - C:/Users/user/Downloads/wei2015.pdf
  - C:/Users/user/Downloads/1-s2.0-S0010448524001520-main.pdf
tags:
  - native-hex
  - pdf
  - full-read
---

# 사용자 제공 PDF 보관 원장

2026-07-26에 Windows Downloads의 원본을 WSL 프로젝트의 `papers/pdf/`에 복사했다. 원본과 보관본은 SHA-256이 일치한다. `papers/pdf/`는 저장소의 대용량 문헌 보관 정책에 따라 Git에서 무시되므로, 이 원장이 보관 경로·식별자·무결성의 추적점이다.

| 원본 | 프로젝트 보관본 | 논문 | DOI | 페이지 | SHA-256 | 판독 |
|---|---|---|---|---:|---|---|
| `C:/Users/user/Downloads/xu2018.pdf` | `papers/pdf/52_xu_2018_hexahedral_mesh_quality_improvement_edge_angle_optimization.pdf` | Xu, Gao, Chen, *Hexahedral mesh quality improvement via edge-angle optimization* | `10.1016/j.cag.2017.07.002` | 11 | `cba14ba0eabe2196820fc2df2c8fa90ab6f7688cf94b941853f3b9b929b806df` | `FULL_READ` |
| `C:/Users/user/Downloads/wei2015.pdf` | `papers/pdf/53_wei_2015_hexahedral_mesh_smoothing_local_regularization_global_optimization.pdf` | Wei, De, Huang, Wang, *Hexahedral mesh smoothing via local element regularization and global mesh optimization* | `10.1016/j.cad.2014.09.003` | 13 | `db184709febb53efd35b4471cc401646af50145c8838318b79aa1ce11ad0983e` | `FULL_READ` |
| `C:/Users/user/Downloads/1-s2.0-S0010448524001520-main.pdf` | `papers/pdf/54_zheng_2025_feature_aware_singularity_structure_optimization_hex_mesh.pdf` | Zheng, Duan, Lei, Luo, *Feature-aware Singularity Structure Optimization for Hex Mesh* | `10.1016/j.cad.2024.103825` | 13 | `d4dee6eb57f9050eba95e0dcc98ede2f56762b2b2033dc13bb79df61d6f31655` | `FULL_READ` |

## 판독 요약

- Xu et al.: 2-ring local region, fixed-region boundary, inversion count 증가 시 rollback, feature/tangent/corner 제약.
- Wei et al.: dual-element local regularization을 volumetric Laplacian과 feature/normal constraint로 stitch; 현재 iteration의 경계·feature 집합 정합성이 전제.
- Zheng et al.: valence/ideal-degree 기반 feature-aware sheet collapse/inflation; boundary edge energy와 non-manifold surface를 별도 필터링하지만, provenance가 틀리거나 boundary/internal surface가 결합된 경우의 무한 반복·비매니폴드 한계를 직접 보고.

## 적용 순서

현재 native_hex에는 transition template, hanging-node lineage, sheet 시작/종료 edge, patch/feature provenance가 결과 메타데이터로 남지 않는다. 따라서 다음 카드는 production repair가 아니라 해당 provenance의 존재 여부와 결정론적 census를 먼저 확인한다. provenance가 확인될 때만 Xu식 local rollback 또는 Zheng식 sheet operation을 검토한다.
