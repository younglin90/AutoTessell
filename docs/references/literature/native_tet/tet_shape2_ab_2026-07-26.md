# TET-SHAPE-2 offline A/B evidence

Date: 2026-07-26

Protocol: fixed native-tet outputs from `tests/benchmarks/`, with
`AUTO_TESSELL_P4C_PYTETWILD=0`, `AUTO_TESSELL_TET_FLOW2=0`, and
`AUTO_TESSELL_FSL_WAVE1=0`. Each output was held fixed while the isolated
boundary-pinned interior pass ran with `gsm_weight=0.35`, three sweeps, and a
1% mean-edge displacement cap. The input surface vertices and all topological
boundary vertices were hard locked. Metrics are measured on the same tet array
before and after the pass.

| Mesh | Cells / points | sigma(dihedral) | p10 Q | mean Q | Q < 0.01 | min dihedral | max skew proxy | shape2 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| naca0012 | 2535 / 933 | 38.0360782243 -> 37.7854756603 | 0.0090372730 -> 0.0090719061 | 0.1474882592 -> 0.1478862682 | 286 -> 283 | 0.0703660708 -> 0.0703660708 | 2.4979867313e17 -> 2.4979867313e17 | 1.470 |
| cylinder | 212 / 73 | 37.5344894079 -> 36.9344926545 | 0.0156790981 -> 0.0176092005 | 0.1241644327 -> 0.1276934252 | 0 -> 0 | 5.7652280164 -> 6.1400450686 | 3.3172823846 -> 2.8903706986 | 0.095 |
| sphere | 2186 / 735 | 23.9885033299 -> 23.5983437431 | 0.1106980963 -> 0.1122975485 | 0.2526318138 -> 0.2543188402 | 5 -> 0 | 0.4454814994 -> 2.5721288147 | 1.9033245769 -> 1.8698845322 | 1.068 |

All three rows pass the strict distribution and worst-axis checks. Boundary face
keys/area, boundary vertex coordinates, exact Shewchuk orientation signs, cell
count, and point count are unchanged. The sum of native generation plus SHAPE-2
time in this run is 19.890 s; the full A/B script wall clock was below the
59.1 s plan budget.

The same three-geometry run was repeated. All recorded metrics and mesh sizes
were identical (`DETERMINISTIC_METRICS True`); only wall-clock samples varied.

Wiring smoke checks also passed: the default-unset path emitted no SHAPE-2 log,
while `AUTO_TESSELL_TET_SHAPE2=1` accepted the transactional pass on both
naca0012 and cylinder with preserved boundary invariants.

