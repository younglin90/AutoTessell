cmake_minimum_required(VERSION 3.20)
project(auto_tessell_core CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ???? Build options ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
option(BUILD_CINOLIB_HEX "Build optional cinolib_hex adapter (needs CINOLIB_DIR headers)" OFF)
option(BUILD_ROBUSTHEX "Build robusthex pybind11 module (needs ROBUSTHEX_DIR source)" ON)
option(BUILD_FTETWILD  "Build vendored fTetWild pybind11 module (third_party/fTetWild)" ON)
option(BUILD_CFMESH    "Build vendored cfMesh pybind11 module (third_party/cfmesh)" ON)
option(BUILD_NATIVE_METRICS "Build native metric kernels for Python checker" ON)
option(BUILD_NATIVE_BL "Build native boundary-layer search kernels" ON)
option(BUILD_NATIVE_POLYMESH "Build native polyMesh topology kernel" ON)
option(BUILD_NATIVE_QUALITY_WITNESS "Build C++23 native quality witness" ON)
option(BUILD_NATIVE_POLY_QUALITY_RELOCATION "Build C++23 Native Poly post-BL quality relocation" ON)
option(BUILD_NATIVE_POLY_BL_LOCAL_FRONT_QOPT "Build C++23 Native Poly local BL front optimizer" ON)
option(BUILD_NATIVE_POLY_AUTHORITY_BOUND "Build private C++ actual-v2 Native Poly authority-bound consumer" ON)
option(BUILD_NATIVE_POLY_DUAL_RECEIPT "Build private C++ deterministic Poly dual-hull receipt" ON)
option(BUILD_NATIVE_TRI_AUTHORITY_BOUND "Build private C++ actual-v2 Native Tri authority-bound consumer" ON)
option(BUILD_NATIVE_STRICT_QUAD_AUTHORITY_BOUND "Build private C++ actual-v2 Strict Quad authority-bound consumer" ON)
option(BUILD_NATIVE_TRI_QUAD_AUTHORITY_BOUND "Build private C++ actual-v2 TRI+QUAD authority-bound consumer" ON)
option(BUILD_NATIVE_L2_EVIDENCE_AUDIT "Build private C++ content-addressed L2 evidence audit" ON)
option(BUILD_NATIVE_EVIDENCE_PACK_V2_WRITER "Build private C++ NativeEvidencePack v2 snapshot writer" ON)
option(BUILD_NATIVE_SNAP "Build native surface snap candidate kernel" ON)
option(BUILD_NATIVE_SURFACE_PADDING "Build native planar surface padding kernel" ON)
option(BUILD_NATIVE_HEX_QUALITY "Build native hex quality kernel" ON)
option(BUILD_NATIVE_TET_HEX_AUTHORITY_BOUND_CONSUMER "Build private C++ actual-v2 Tet/Hex boundary receipt consumer" ON)
option(BUILD_NATIVE_TET_SURFACE_BOUNDARY_RECEIPT_CONSUMER "Build private C++ actual surface-to-Tet boundary receipt consumer" ON)
option(BUILD_NATIVE_TET_PREDICATES "Build native exact tetrahedral predicate kernel" ON)
option(BUILD_NATIVE_TET_QOPT "Build native tetrahedral quality-optimizer kernel" ON)
option(BUILD_NATIVE_TET_RECEIPT_GRAPH
  "Build C++23 immutable Native Tet source/output receipt graph" ON)
option(BUILD_NATIVE_TET_POLYMESH_QUALITY
  "Build C++23 disk-authoritative OpenFOAM polyMesh quality oracle" ON)
option(BUILD_NATIVE_TET_METRIC_SEED "Build native metric-aware Tet seed kernel" ON)
option(BUILD_NATIVE_TET_BL_QOPT "Build native Tet wall-front quality optimizer kernel" ON)
option(BUILD_NATIVE_TRI_QUALITY_REPAIR "Build C++23 Native Tri constrained quality repair kernel" ON)
option(BUILD_NATIVE_SURFACE_BL_QUALITY "Build optional report-only native surface boundary-layer quality witness" OFF)
option(BUILD_NATIVE_SURFACE_BL_FOLDED_PLATE
  "Build private native folded-plate surface BL extension" OFF)
option(BUILD_NATIVE_SURFACE_BL_FRONT_SHARED
  "Build the C++23 shared-vertex surface wall-edge BL candidate planner" ON)
option(BUILD_NATIVE_SURFACE_BL_FRONT_SHARED_OPTIMIZER
  "Build the C++23 strict quality surface wall-edge optimizer" ON)
option(AUTOTESSELL_INSTALL_SURFACE_BL_FOLDED_PLATE
  "Install the separate verified folded-plate surface BL package" OFF)
option(BUILD_NATIVE_SURFACE_BL_STRIP_WRITER "Build private surface BL strip writer" ON)
option(BUILD_NATIVE_SURFACE_BL_HETEROGENEOUS_CERTIFICATE
  "Build private C++23 fail-closed heterogeneous surface BL certificate" ON)
option(BUILD_NATIVE_SURFACE_BL_ACTUAL_TRANSACTION Build_private_surface_BL_actual_authority_transaction_sealer ON)
option(BUILD_NATIVE_SURFACE_BL_INDEPENDENT_VERIFIER Build_private_surface_BL_independent_verifier ON)
option(BUILD_NATIVE_SURFACE_AUTHORITY_CORPUS Build_private_surface_authority_corpus_validator ON)
option(BUILD_NATIVE_SURFACE_STL_AUTHORITY_INGRESS "Build C++23 native STL source authority ingress" ON)
option(BUILD_NATIVE_SURFACE_BL_PARTITION_TRANSACTION "Build C++23 source-replacing surface partition transaction" ON)
option(BUILD_NATIVE_SURFACE_BL_FRONT_ACTUAL_V2
  "Build private C++23 actual BRep surface wall-edge ingress/producer/transaction modules" ON)
option(BUILD_NATIVE_HEX_CAD_AUTHORITY_CORPUS Build_private_native_hex_CAD_authority_validator ON)
option(BUILD_NATIVE_POLY_PROTECTED_CORPUS_RECEIPT Build_private_protected_native_poly_corpus_receipt ON)
option(BUILD_NATIVE_TRI_AUTHORITY_INGRESS_RECEIPT Build_private_native_tri_authority_ingress_receipt ON)
option(BUILD_NATIVE_TRI_CAD_STL_AUTHORITY_INGRESS
  "Build private C++23 Native Tri CAD/STL authority certificate ingress" ON)
option(BUILD_NATIVE_WALL_EDGE_METRIC_CORRIDOR
  "Build default-off shared wall-edge metric corridor certificate" ON)
option(BUILD_NATIVE_TRANSACTION_INTENT
  "Build default-off authoritative transaction-intent admission kernel" ON)
option(BUILD_NATIVE_TRANSACTION_EXECUTOR
  "Build default-off staged quality transaction executor" OFF)
option(BUILD_NATIVE_TRI_WALL_EDGE_BL_PREFLIGHT
  "Build private C++23 Native Tri wall-edge BL authority preflight" ON)
option(BUILD_NATIVE_TRI_PLANAR_TRIANGLE_BL_TEMPLATE
  "Build private C++23 authority-bound planar Native Tri BL template" ON)
option(BUILD_NATIVE_TRI_PLANAR_FACE_PAIR_BL_TEMPLATE
  "Build private C++23 authority-bound planar Native Tri face-pair BL template" ON)
option(BUILD_NATIVE_TRI_AUTHORITATIVE_CUBE_LATTICE_BL_REFINEMENT
  "Build private C++23 authority-bound conforming cube-lattice Native Tri BL refinement" ON)
option(BUILD_NATIVE_TRI_AUTHORITATIVE_RECTILINEAR_BOX_LATTICE_BL_REFINEMENT
  "Build private C++23 authority-bound rectilinear-box lattice Native Tri BL refinement" ON)
option(BUILD_NATIVE_TRI_AUTHORITY_BOUND_DIAGONAL_FRONT_CDT
  "Build private C++23 authority-bound diagonal-front constrained-Delaunay Native Tri BL refinement" ON)
option(BUILD_NATIVE_TRI_AUTHORITY_BOUND_SURFACE_BL_FRONT
  "Build private C++23 authority-bound non-box surface Native Tri BL front" ON)
option(BUILD_NATIVE_STRICT_QUAD_AUTHORITY_INGRESS_RECEIPT Build_private_strict_quad_authority_ingress_receipt ON)
option(BUILD_NATIVE_TRI_QUAD_AUTHORITY_INGRESS_RECEIPT Build_private_tri_quad_authority_ingress_receipt ON)
option(BUILD_NATIVE_TRI_QUAD_ACTUAL_MIXED_BL_TRANSACTION Build_private_tri_quad_actual_mixed_boundary_layer_transaction ON)
option(BUILD_NATIVE_TRI_QUAD_INDEPENDENT_QUALITY_READBACK Build_private_tri_quad_independent_quality_readback ON)
option(BUILD_NATIVE_TRI_QUAD_PRODUCER_AUDITOR_QUALITY_GATE Build_private_tri_quad_producer_auditor_quality_gate ON)
option(BUILD_NATIVE_ARTIFACT_FINGERPRINT "Build C++ staged artifact-tree fingerprint kernel" ON)
option(BUILD_NATIVE_ATOMIC_PUBLISH "Build C++ fail-closed stage/publish kernel" ON)
option(BUILD_NATIVE_BL_IDENTITY "Build C++ fail-closed BL identity witness" ON)
option(BUILD_NATIVE_GATE4_LINEAGE_WITNESS "Build C++23 staged Gate4 lineage witness" ON)
option(BUILD_NATIVE_TET_BL_TRANSACTION "Build report-only C++ native Tet staged BL transaction validator" ON)
option(BUILD_NATIVE_TET_ACTUAL_BREP_CONFORMAL_SHELL "Build private actual BRep regular-tetra pure-Tet BL shell producer" ON)
option(BUILD_NATIVE_SURFACE_PRODUCT_TRANSACTION "Build report-only C++ surface product transaction validator" ON)
option(BUILD_NATIVE_HEX_BL_TRANSACTION "Build report-only C++ native Hex inward-shell transaction validator" ON)
option(BUILD_NATIVE_HEX_ACTUAL_XDE_PRODUCER "Build restricted actual STEPCAF/XDE Native Hex producer" ON)
option(BUILD_NATIVE_HEX_OCCT_XDE_INGRESS
  "Build fail-closed Native Hex OCCT/XDE CAD ingress certificate" ON)
option(BUILD_NATIVE_HEX_BOUNDARY_RECEIPT "Build C++23 Native Hex post-BL B-Rep boundary receipt" ON)
option(BUILD_NATIVE_SURFACE_PRODUCT
  "Build report-only native surface product evaluator" OFF)
option(AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE
  "Install only the first-party native extension wheel profile" OFF)

if(AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE)
  # Keep binary wheels independent of optional external adapter sources.
  set(BUILD_CINOLIB_HEX OFF CACHE BOOL "" FORCE)
  set(BUILD_ROBUSTHEX OFF CACHE BOOL "" FORCE)
  set(BUILD_FTETWILD OFF CACHE BOOL "" FORCE)
  set(BUILD_CFMESH OFF CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_METRICS ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_BL ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_POLYMESH ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_SNAP ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_SURFACE_PADDING ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_HEX_QUALITY ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_TET_PREDICATES ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_TET_QOPT ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_ARTIFACT_FINGERPRINT ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_ATOMIC_PUBLISH ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_BL_IDENTITY ON CACHE BOOL "" FORCE)
  set(BUILD_NATIVE_GATE4_LINEAGE_WITNESS ON CACHE BOOL "" FORCE)
endif()

# ???? Paths to cloned repos (define first ??used by subdirectory builds) ??????????????
set(CINOLIB_DIR     "/tmp/hexmesh_build/cinolib"                    CACHE PATH "")
set(ROBUSTHEX_DIR   "/tmp/hexmesh_build/robust_hex_dominant_meshing" CACHE PATH "")
set(TETGEN_DIR      "${ROBUSTHEX_DIR}/ext/tetgen"                    CACHE PATH "")
set(PCG32_DIR       "${ROBUSTHEX_DIR}/ext/pcg32"                     CACHE PATH "")
set(RPLY_DIR        "${ROBUSTHEX_DIR}/ext/rply"                      CACHE PATH "")
set(FAKE_NANOGUI    "${CMAKE_CURRENT_SOURCE_DIR}/fake_nanogui"       CACHE PATH "")

# ???? pybind11 ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
set(PYBIND11_FINDPYTHON ON)
find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 3.0 CONFIG REQUIRED)

# ???? Eigen3 ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
if(BUILD_CINOLIB_HEX OR BUILD_ROBUSTHEX OR BUILD_FTETWILD)
  find_package(Eigen3 3.3 REQUIRED NO_MODULE)
endif()

set(_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS
  native_metrics
  native_quality_witness
  native_bl
  native_polymesh
  native_snap
  native_surface_padding
  native_hex_quality
  native_tet_receipt_graph
  native_tet_receipt_graph_1_to_n
  native_tet_predicates
  native_tet_qopt
  native_tet_polymesh_quality
  native_tet_metric_seed)
if(BUILD_NATIVE_POLY_QUALITY_RELOCATION)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_poly_quality_relocation)
endif()
if(BUILD_NATIVE_POLY_BL_LOCAL_FRONT_QOPT)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_poly_bl_local_front_qopt)
endif()
if(BUILD_NATIVE_TRI_QUALITY_REPAIR)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_tri_quality_repair)
endif()
if(BUILD_NATIVE_ARTIFACT_FINGERPRINT)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_artifact_fingerprint)
endif()
if(BUILD_NATIVE_HEX_BOUNDARY_RECEIPT)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_hex_boundary_receipt)
endif()
if(BUILD_NATIVE_ATOMIC_PUBLISH)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_atomic_publish)
endif()
if(BUILD_NATIVE_BL_IDENTITY)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_bl_identity)
endif()
if(BUILD_NATIVE_GATE4_LINEAGE_WITNESS)
  list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_gate4_lineage_witness)
endif()

function(autotessell_configure_first_party_native target_name)
  target_compile_features(${target_name} PRIVATE cxx_std_23)
  set_target_properties(${target_name} PROPERTIES CXX_EXTENSIONS OFF)
  if(MSVC)
    target_compile_options(${target_name} PRIVATE
      $<$<COMPILE_LANGUAGE:CXX>:/O2;/W4>
      $<$<AND:$<COMPILE_LANGUAGE:CXX>,$<BOOL:${AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE}>>:/WX>)
  else()
    target_compile_options(${target_name} PRIVATE
      $<$<COMPILE_LANGUAGE:CXX>:-O3;-Wall;-Wextra;-Wpedantic>
      $<$<AND:$<COMPILE_LANGUAGE:CXX>,$<BOOL:${AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE}>>:-Werror>)
  endif()
endfunction()

if(BUILD_NATIVE_SURFACE_BL_FOLDED_PLATE)
  pybind11_add_module(native_surface_bl_folded_plate
      surface_bl_front_shared/surface_bl_folded_plate_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_folded_plate)
  set_target_properties(native_surface_bl_folded_plate PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY
      "${CMAKE_CURRENT_BINARY_DIR}/surface_bl_package/native_extensions"
    RUNTIME_OUTPUT_DIRECTORY
      "${CMAKE_CURRENT_BINARY_DIR}/surface_bl_package/native_extensions")
  if(AUTOTESSELL_INSTALL_SURFACE_BL_FOLDED_PLATE)
    install(TARGETS native_surface_bl_folded_plate
      LIBRARY DESTINATION native_extensions
      RUNTIME DESTINATION native_extensions)
  endif()

  # The readback verifier is a separate private package module.  It shares
  # the package staging directory but is intentionally excluded from the
  # exact-15 first-party ABI inventory and remains publication-ineligible.
  pybind11_add_module(native_surface_bl_readback_verifier
      surface_bl_front_shared/surface_bl_readback_verifier_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_readback_verifier)
  set_target_properties(native_surface_bl_readback_verifier PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY
      "${CMAKE_CURRENT_BINARY_DIR}/surface_bl_package/native_extensions"
    RUNTIME_OUTPUT_DIRECTORY
      "${CMAKE_CURRENT_BINARY_DIR}/surface_bl_package/native_extensions")
  if(AUTOTESSELL_INSTALL_SURFACE_BL_FOLDED_PLATE)
    install(TARGETS native_surface_bl_readback_verifier
      LIBRARY DESTINATION native_extensions
      RUNTIME DESTINATION native_extensions)
  endif()
endif()

# ???? Compiler flag helpers ????????????????????????????????????????????????????????????????????????????????????????????????????????
# Use MSVC-compatible flags on Windows, GCC/Clang flags elsewhere
if(MSVC)
  set(_CINOLIB_FLAGS  /O2 /W0 /MP /bigobj)
  set(_ROBUSTHEX_FLAGS /O2 /W0 /MP /bigobj)
  # MSVC does not need -Wno-changes-meaning or -march=native
else()
  set(_CINOLIB_FLAGS  -O3 -w)
  if(NOT APPLE)
    list(APPEND _CINOLIB_FLAGS -march=native)
  endif()
  set(_ROBUSTHEX_FLAGS -O2 -w -Wno-changes-meaning)
endif()

# ???? cinolib_hex adapter (optional, external source) ??????????????????????????????????????????????????
# cinolib is not native-core source.  Keep Release builds independent of a
# developer-local checkout unless this adapter is explicitly requested.
if(BUILD_CINOLIB_HEX)
  if(NOT EXISTS "${CINOLIB_DIR}/include/cinolib/geometry/vec_mat.h")
    message(FATAL_ERROR
      "BUILD_CINOLIB_HEX=ON requires cinolib headers at "
      "CINOLIB_DIR/include/cinolib/geometry/vec_mat.h; "
      "set -DCINOLIB_DIR=<cinolib source root> or set -DBUILD_CINOLIB_HEX=OFF")
  endif()
  pybind11_add_module(cinolib_hex cinolib_hex_bind.cpp)
  target_include_directories(cinolib_hex PRIVATE "${CINOLIB_DIR}/include")
  target_compile_options(cinolib_hex PRIVATE ${_CINOLIB_FLAGS})
  target_link_libraries(cinolib_hex PRIVATE Eigen3::Eigen)
endif()

# ???? native metric kernels ????????????????????????????????????????????????????????????????????????????????????????????????????????
if(BUILD_NATIVE_METRICS)
  pybind11_add_module(native_metrics native_metrics_bind.cpp)
  autotessell_configure_first_party_native(native_metrics)
endif()

if(BUILD_NATIVE_QUALITY_WITNESS)
  pybind11_add_module(native_quality_witness native_quality_witness/native_quality_witness_bind.cpp
      native_quality_witness/native_quality_witness_v3.cpp)
  autotessell_configure_first_party_native(native_quality_witness)
endif()

# ???? native polyMesh topology kernel ??????????????????????????????????????????????????????????????????????????????
# Native boundary-layer search kernels.
if(BUILD_NATIVE_BL)
  pybind11_add_module(native_bl native_bl_bind.cpp)
  autotessell_configure_first_party_native(native_bl)
endif()

if(BUILD_NATIVE_POLYMESH)
  pybind11_add_module(native_polymesh native_polymesh_bind.cpp)
  autotessell_configure_first_party_native(native_polymesh)
endif()

if(BUILD_NATIVE_POLY_QUALITY_RELOCATION)
  pybind11_add_module(native_poly_quality_relocation native_poly_quality_relocation_bind.cpp)
  autotessell_configure_first_party_native(native_poly_quality_relocation)
endif()
if(BUILD_NATIVE_POLY_BL_LOCAL_FRONT_QOPT)
  pybind11_add_module(native_poly_bl_local_front_qopt native_poly_bl_local_front_qopt_bind.cpp)
  autotessell_configure_first_party_native(native_poly_bl_local_front_qopt)
endif()

if(BUILD_NATIVE_POLY_AUTHORITY_BOUND)
  pybind11_add_module(native_poly_authority_bound_consumer native_poly_authority_bound_consumer_bind.cpp)
  autotessell_configure_first_party_native(native_poly_authority_bound_consumer)
endif()

if(BUILD_NATIVE_POLY_DUAL_RECEIPT)
  pybind11_add_module(native_poly_dual_deterministic_receipt native_poly_dual_deterministic_receipt_bind.cpp)
  autotessell_configure_first_party_native(native_poly_dual_deterministic_receipt)
endif()

if(BUILD_NATIVE_TRI_AUTHORITY_BOUND)
  pybind11_add_module(native_tri_authority_bound_consumer native_tri_authority_bound_consumer_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authority_bound_consumer)
endif()

if(BUILD_NATIVE_STRICT_QUAD_AUTHORITY_BOUND)
  pybind11_add_module(native_strict_quad_authority_bound_consumer native_strict_quad_authority_bound_consumer_bind.cpp)
  autotessell_configure_first_party_native(native_strict_quad_authority_bound_consumer)
endif()

if(BUILD_NATIVE_TRI_QUAD_AUTHORITY_BOUND)
if(BUILD_NATIVE_TET_HEX_AUTHORITY_BOUND_CONSUMER)
  pybind11_add_module(native_tet_hex_authority_bound_consumer
      surface_bl_front_shared/native_tet_hex_authority_bound_consumer_bind.cpp)
  autotessell_configure_first_party_native(native_tet_hex_authority_bound_consumer)
endif()
  pybind11_add_module(native_tri_quad_authority_bound_consumer native_tri_quad_authority_bound_consumer_bind.cpp)
if(BUILD_NATIVE_TET_SURFACE_BOUNDARY_RECEIPT_CONSUMER)
  pybind11_add_module(native_tet_surface_boundary_receipt_consumer
      native_tet_surface_boundary_receipt_consumer_bind.cpp)
  autotessell_configure_first_party_native(native_tet_surface_boundary_receipt_consumer)
endif()
  autotessell_configure_first_party_native(native_tri_quad_authority_bound_consumer)
endif()

if(BUILD_NATIVE_TRI_QUALITY_REPAIR)
  pybind11_add_module(native_tri_quality_repair native_tri_quality_repair_bind.cpp)
  autotessell_configure_first_party_native(native_tri_quality_repair)
endif()

if(BUILD_NATIVE_L2_EVIDENCE_AUDIT)
  pybind11_add_module(native_l2_evidence_audit native_l2_evidence_audit_bind.cpp)
  autotessell_configure_first_party_native(native_l2_evidence_audit)
endif()
if(BUILD_NATIVE_EVIDENCE_PACK_V2_WRITER)
  pybind11_add_module(native_evidence_pack_v2_writer native_evidence_pack_v2_writer_bind.cpp)
  autotessell_configure_first_party_native(native_evidence_pack_v2_writer)
endif()

# ???? native surface snap candidate kernel ????????????????????????????????????????????????????????????????????
if(BUILD_NATIVE_SNAP)
  pybind11_add_module(native_snap native_snap_bind.cpp)
  autotessell_configure_first_party_native(native_snap)
endif()

# ???? native planar surface padding kernel ????????????????????????????????????????????????????????????????????
if(BUILD_NATIVE_SURFACE_PADDING)
  pybind11_add_module(native_surface_padding native_surface_padding_bind.cpp)
  autotessell_configure_first_party_native(native_surface_padding)
endif()

# ???? native hex quality kernel ????????????????????????????????????????????????????????????????????????????????????????????
if(BUILD_NATIVE_HEX_QUALITY)
  pybind11_add_module(native_hex_quality native_hex_quality_bind.cpp)
  autotessell_configure_first_party_native(native_hex_quality)
endif()

# ???? native exact tetrahedral predicates ??????????????????????????????????????????????????????????????????????
# The robust predicate implementation is the public-domain first-party copy
# already used by AutoTessell's Python predicate wrapper.  It is compiled into
# this module without modifying or depending on third_party/ source.
if(BUILD_NATIVE_TET_PREDICATES)
  # cpp_int is header-only.  Require an explicit development package so a
  # fresh source build fails at configure time instead of during compilation.
  find_package(Boost REQUIRED)
  set(_SHEWCHUK_PREDICATES
      "${CMAKE_CURRENT_SOURCE_DIR}/../core/utils/_shewchuk/predicates.c")
  if(NOT EXISTS "${_SHEWCHUK_PREDICATES}")
    message(FATAL_ERROR
      "BUILD_NATIVE_TET_PREDICATES=ON requires ${_SHEWCHUK_PREDICATES}")
  endif()
  pybind11_add_module(native_tet_predicates
      native_tet_predicates_bind.cpp
      "${_SHEWCHUK_PREDICATES}")
  target_link_libraries(native_tet_predicates PRIVATE Boost::headers)
  autotessell_configure_first_party_native(native_tet_predicates)
  if(MSVC)
    set_source_files_properties("${_SHEWCHUK_PREDICATES}"
        PROPERTIES COMPILE_OPTIONS "/O2;/fp:precise")
  else()
    set_source_files_properties("${_SHEWCHUK_PREDICATES}"
        PROPERTIES COMPILE_OPTIONS "-O3;-fno-fast-math")
  endif()
endif()

# ???? native tetrahedral quality optimizer ????????????????????????????????????????????????????????????????????
if(BUILD_NATIVE_TET_QOPT)
if(BUILD_NATIVE_TET_RECEIPT_GRAPH)
  pybind11_add_module(native_tet_receipt_graph
      native_tet_receipt_graph_bind.cpp)
  autotessell_configure_first_party_native(native_tet_receipt_graph)
  pybind11_add_module(native_tet_receipt_graph_1_to_n
      native_tet_receipt_graph_1_to_n_bind.cpp)
  autotessell_configure_first_party_native(native_tet_receipt_graph_1_to_n)
endif()
  pybind11_add_module(native_tet_qopt native_tet_qopt_bind.cpp)
  autotessell_configure_first_party_native(native_tet_qopt)
endif()
if(BUILD_NATIVE_TET_POLYMESH_QUALITY)
  pybind11_add_module(native_tet_polymesh_quality
      native_tet_polymesh_quality_bind_v2.cpp)
  autotessell_configure_first_party_native(native_tet_polymesh_quality)
endif()
if(BUILD_NATIVE_TET_METRIC_SEED)
  pybind11_add_module(native_tet_metric_seed native_tet_metric_seed_bind.cpp)
  autotessell_configure_first_party_native(native_tet_metric_seed)
endif()
if(BUILD_NATIVE_TET_BL_QOPT)
  pybind11_add_module(native_tet_bl_front_qopt native_tet_bl_front_qopt_bind.cpp)
  autotessell_configure_first_party_native(native_tet_bl_front_qopt)
  pybind11_add_module(native_tet_bl_writer native_tet_bl_writer_bind.cpp)
  autotessell_configure_first_party_native(native_tet_bl_writer)
  pybind11_add_module(native_tet_bl_admission native_tet_bl_admission_bind.cpp)
  autotessell_configure_first_party_native(native_tet_bl_admission)
  pybind11_add_module(native_tet_bl_authoritative_graph native_tet_bl_authoritative_graph_bind.cpp)
  autotessell_configure_first_party_native(native_tet_bl_authoritative_graph)
endif()

# ???? report-only native surface product evaluator ??????????????????????????????????????????????????????
# This target is deliberately default-OFF and is not part of the distributable
# first-party extension inventory.  It validates immutable topology arrays and
# reports a product class only; it does not route, create, repair, or write mesh
# data.
if(BUILD_NATIVE_SURFACE_PRODUCT)
  pybind11_add_module(native_surface_product native_surface_product_bind.cpp)
  autotessell_configure_first_party_native(native_surface_product)
endif()
if(BUILD_NATIVE_ATOMIC_PUBLISH)
  pybind11_add_module(native_atomic_publish
      native_atomic_publish_bind.cpp)
  autotessell_configure_first_party_native(native_atomic_publish)
endif()

if(BUILD_NATIVE_ARTIFACT_FINGERPRINT)
  pybind11_add_module(native_artifact_fingerprint
      native_artifact_fingerprint_bind.cpp)
  target_include_directories(native_artifact_fingerprint PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_artifact_fingerprint)
endif()
if(BUILD_NATIVE_GATE4_LINEAGE_WITNESS)
  pybind11_add_module(native_gate4_lineage_witness
      native_gate4_lineage_witness_bind.cpp)
  target_include_directories(native_gate4_lineage_witness PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_gate4_lineage_witness)
endif()
if(BUILD_NATIVE_BL_IDENTITY)
  pybind11_add_module(native_bl_identity native_bl_identity_bind.cpp)
  autotessell_configure_first_party_native(native_bl_identity)
endif()

if(BUILD_NATIVE_TET_BL_TRANSACTION)
  pybind11_add_module(native_tet_bl_transaction native_tet_bl_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_tet_bl_transaction)
endif()
if(BUILD_NATIVE_TET_ACTUAL_BREP_CONFORMAL_SHELL)
  pybind11_add_module(native_tet_actual_brep_conformal_shell native_tet_actual_brep_conformal_shell_bind.cpp)
  autotessell_configure_first_party_native(native_tet_actual_brep_conformal_shell)
endif()
if(BUILD_NATIVE_SURFACE_PRODUCT_TRANSACTION)
  pybind11_add_module(native_surface_product_transaction native_surface_product_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_surface_product_transaction)
endif()
if(BUILD_NATIVE_HEX_BL_TRANSACTION)
  pybind11_add_module(native_hex_bl_transaction native_hex_bl_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_hex_bl_transaction)
endif()
if(BUILD_NATIVE_HEX_ACTUAL_XDE_PRODUCER)
  pybind11_add_module(native_hex_actual_xde_brep_producer native_hex_actual_xde_brep_producer_bind.cpp)
  autotessell_configure_first_party_native(native_hex_actual_xde_brep_producer)
endif()
if(BUILD_NATIVE_HEX_OCCT_XDE_INGRESS)
  pybind11_add_module(native_hex_occt_xde_ingress
      native_hex_occt_xde_ingress_bind.cpp)
  target_include_directories(native_hex_occt_xde_ingress PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_hex_occt_xde_ingress)

  if(NOT DEFINED AUTOTESSELL_OCCT_SDK_ROOT)
    set(AUTOTESSELL_OCCT_SDK_ROOT "$ENV{AUTOTESSELL_OCCT_SDK_ROOT}"
        CACHE PATH "Optional OCCT SDK root for authoritative STEPCAF/XDE ingress")
  endif()
  set(AUTOTESSELL_OCCT_VERSION "" CACHE STRING
      "Expected OCCT version for the authoritative provisioning manifest")
  set(AUTOTESSELL_OCCT_ABI "" CACHE STRING
      "Expected OCCT ABI identity for the authoritative provisioning manifest")
  set(AUTOTESSELL_OCCT_COMPILER_ABI
      "${CMAKE_CXX_COMPILER_ID}-${CMAKE_CXX_COMPILER_VERSION}" CACHE STRING
      "Compiler ABI identity for the authoritative provisioning manifest")
  set(AUTOTESSELL_OCCT_BUILD_IDENTITY
      "${CMAKE_SYSTEM_NAME}-${CMAKE_CXX_COMPILER_ID}-${CMAKE_CXX_COMPILER_VERSION}" CACHE STRING
      "Native extension build identity for the authoritative provisioning manifest")
  set(_autotessell_occt_header "")
  set(_autotessell_occt_header_file "")
  set(_autotessell_occt_libs "")
  if(AUTOTESSELL_OCCT_SDK_ROOT)
    find_path(_autotessell_occt_header
      NAMES STEPCAFControl_Reader.hxx
      HINTS
        "${AUTOTESSELL_OCCT_SDK_ROOT}/include"
        "${AUTOTESSELL_OCCT_SDK_ROOT}/inc"
      PATH_SUFFIXES opencascade
      NO_DEFAULT_PATH)
    if(_autotessell_occt_header)
      find_file(_autotessell_occt_header_file
        NAMES STEPCAFControl_Reader.hxx
        HINTS "${_autotessell_occt_header}"
        NO_DEFAULT_PATH)
    endif()
    set(_autotessell_occt_library_names
      TKSTEPCAF TKXDE TKCAF TKLCAF TKSTEP TKSTEPBase TKXSBase
      TKDESTEP TKDE TKernel TKMath)
    set(_autotessell_occt_all_libs TRUE)
    foreach(_autotessell_occt_name IN LISTS _autotessell_occt_library_names)
      find_library(_autotessell_occt_${_autotessell_occt_name}
        NAMES ${_autotessell_occt_name}
        HINTS
          "${AUTOTESSELL_OCCT_SDK_ROOT}/lib"
          "${AUTOTESSELL_OCCT_SDK_ROOT}/lib64"
        NO_DEFAULT_PATH)
      if(NOT _autotessell_occt_${_autotessell_occt_name})
        set(_autotessell_occt_all_libs FALSE)
      else()
        list(APPEND _autotessell_occt_libs
          "${_autotessell_occt_${_autotessell_occt_name}}")
      endif()
    endforeach()
    if(_autotessell_occt_header AND _autotessell_occt_header_file
       AND _autotessell_occt_all_libs
       AND AUTOTESSELL_OCCT_VERSION
       AND AUTOTESSELL_OCCT_ABI
       AND AUTOTESSELL_OCCT_COMPILER_ABI
       AND AUTOTESSELL_OCCT_BUILD_IDENTITY)
      file(REAL_PATH "${AUTOTESSELL_OCCT_SDK_ROOT}" _autotessell_occt_root_real)
      file(RELATIVE_PATH _autotessell_occt_header_rel
        "${_autotessell_occt_root_real}" "${_autotessell_occt_header_file}")
      file(SHA256 "${_autotessell_occt_header_file}" _autotessell_occt_header_sha)
      set(_autotessell_occt_manifest_content
        "schema=autotessell/native-hex-occt-provisioning/v1\\n"
        "sdk_root=${_autotessell_occt_root_real}\\n"
        "occt_version=${AUTOTESSELL_OCCT_VERSION}\\n"
        "occt_abi=${AUTOTESSELL_OCCT_ABI}\\n"
        "compiler_abi=${AUTOTESSELL_OCCT_COMPILER_ABI}\\n"
        "build_identity=${AUTOTESSELL_OCCT_BUILD_IDENTITY}\\n")
      string(APPEND _autotessell_occt_manifest_content
        "header.STEPCAFControl_Reader.hxx=${_autotessell_occt_header_rel}|${_autotessell_occt_header_sha}\\n")
      foreach(_autotessell_occt_lib IN LISTS _autotessell_occt_libs)
        get_filename_component(_autotessell_occt_lib_name
          "${_autotessell_occt_lib}" NAME)
        string(REGEX REPLACE "^lib" "" _autotessell_occt_lib_name
          "${_autotessell_occt_lib_name}")
        string(REGEX REPLACE "\.(so|dylib|dll)(\..*)?$" ""
          _autotessell_occt_lib_name "${_autotessell_occt_lib_name}")
        string(REGEX REPLACE "\.(a|lib)$" ""
          _autotessell_occt_lib_name "${_autotessell_occt_lib_name}")
        file(RELATIVE_PATH _autotessell_occt_lib_rel
          "${_autotessell_occt_root_real}" "${_autotessell_occt_lib}")
        file(SHA256 "${_autotessell_occt_lib}" _autotessell_occt_lib_sha)
        string(APPEND _autotessell_occt_manifest_content
          "library.${_autotessell_occt_lib_name}=${_autotessell_occt_lib_rel}|${_autotessell_occt_lib_sha}\\n")
      endforeach()
      string(SHA256 _autotessell_occt_manifest_sha
        "${_autotessell_occt_manifest_content}")
      set(_autotessell_occt_manifest_path
        "${CMAKE_CURRENT_BINARY_DIR}/native_hex_occt_provisioning.manifest")
      file(WRITE "${_autotessell_occt_manifest_path}"
        "${_autotessell_occt_manifest_content}"
        "manifest_sha256=${_autotessell_occt_manifest_sha}\\n")
      target_include_directories(native_hex_occt_xde_ingress PRIVATE
        "${_autotessell_occt_header}/..")
      target_link_libraries(native_hex_occt_xde_ingress PRIVATE
        ${_autotessell_occt_libs})
      target_compile_definitions(native_hex_occt_xde_ingress PRIVATE
        AUTOTESSELL_HAVE_OCCT=1)
      message(STATUS
        "Native Hex OCCT/XDE ingress enabled with provisioning manifest ${_autotessell_occt_manifest_path}")
    else()
      message(STATUS
        "Native Hex OCCT/XDE ingress remains fail-closed: SDK, identity, or manifest fields missing")
    endif()
  else()
    message(STATUS
      "Native Hex OCCT/XDE ingress remains fail-closed: AUTOTESSELL_OCCT_SDK_ROOT is unset")
  endif()
endif()
if(BUILD_NATIVE_HEX_BOUNDARY_RECEIPT)
  pybind11_add_module(native_hex_boundary_receipt native_hex_boundary_receipt_bind.cpp)
  target_include_directories(native_hex_boundary_receipt PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_hex_boundary_receipt)
endif()



if(BUILD_NATIVE_SURFACE_BL_QUALITY)
  pybind11_add_module(native_surface_bl_quality
      surface_bl_quality/surface_bl_quality_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_quality)
endif()
if(BUILD_NATIVE_TRI_QUAD_AUTHORITY_INGRESS_RECEIPT)
  pybind11_add_module(native_tri_quad_authority_ingress_receipt
      native_tri_quad_authority_ingress_receipt_bind.cpp)
  autotessell_configure_first_party_native(native_tri_quad_authority_ingress_receipt)
endif()
if(BUILD_NATIVE_TRI_QUAD_ACTUAL_MIXED_BL_TRANSACTION)
  pybind11_add_module(native_tri_quad_actual_mixed_bl_transaction
      native_tri_quad_actual_mixed_bl_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_tri_quad_actual_mixed_bl_transaction)
endif()
if(BUILD_NATIVE_TRI_QUAD_INDEPENDENT_QUALITY_READBACK)
  pybind11_add_module(native_tri_quad_independent_quality_readback
      native_tri_quad_independent_quality_readback_bind.cpp)
  autotessell_configure_first_party_native(native_tri_quad_independent_quality_readback)
endif()
if(BUILD_NATIVE_TRI_QUAD_PRODUCER_AUDITOR_QUALITY_GATE)
  pybind11_add_module(native_tri_quad_producer_auditor_quality_gate
      native_tri_quad_producer_auditor_quality_gate_bind.cpp)
  autotessell_configure_first_party_native(native_tri_quad_producer_auditor_quality_gate)
endif()
if(BUILD_NATIVE_STRICT_QUAD_AUTHORITY_INGRESS_RECEIPT)
  pybind11_add_module(native_strict_quad_authority_ingress_receipt
      native_strict_quad_authority_ingress_receipt_bind.cpp)
  autotessell_configure_first_party_native(native_strict_quad_authority_ingress_receipt)
endif()
if(BUILD_NATIVE_TRI_AUTHORITY_INGRESS_RECEIPT)
  pybind11_add_module(native_tri_authority_ingress_receipt
      native_tri_authority_ingress_receipt_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authority_ingress_receipt)
endif()
if(BUILD_NATIVE_TRI_CAD_STL_AUTHORITY_INGRESS)
  pybind11_add_module(native_tri_cad_stl_authority_ingress
      native_tri_cad_stl_authority_ingress_bind.cpp)
  autotessell_configure_first_party_native(native_tri_cad_stl_authority_ingress)
endif()
if(BUILD_NATIVE_TRI_WALL_EDGE_BL_PREFLIGHT)
  pybind11_add_module(native_tri_wall_edge_bl_preflight
      native_tri_wall_edge_bl_preflight_bind.cpp)
  autotessell_configure_first_party_native(native_tri_wall_edge_bl_preflight)
endif()
if(BUILD_NATIVE_TRI_PLANAR_TRIANGLE_BL_TEMPLATE)
  pybind11_add_module(native_tri_planar_triangle_bl_template
      native_tri_planar_triangle_bl_template_bind.cpp)
  autotessell_configure_first_party_native(native_tri_planar_triangle_bl_template)
endif()
if(BUILD_NATIVE_TRI_PLANAR_FACE_PAIR_BL_TEMPLATE)
  pybind11_add_module(native_tri_planar_face_pair_bl_template
      native_tri_planar_face_pair_bl_template_bind.cpp)
  autotessell_configure_first_party_native(native_tri_planar_face_pair_bl_template)
endif()
if(BUILD_NATIVE_TRI_AUTHORITATIVE_CUBE_LATTICE_BL_REFINEMENT)
  pybind11_add_module(native_tri_authoritative_cube_lattice_bl_refinement
      native_tri_authoritative_cube_lattice_bl_refinement_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authoritative_cube_lattice_bl_refinement)
endif()
if(BUILD_NATIVE_TRI_AUTHORITATIVE_RECTILINEAR_BOX_LATTICE_BL_REFINEMENT)
  pybind11_add_module(native_tri_authoritative_rectilinear_box_lattice_bl_refinement
      native_tri_authoritative_rectilinear_box_lattice_bl_refinement_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authoritative_rectilinear_box_lattice_bl_refinement)
endif()
if(BUILD_NATIVE_TRI_AUTHORITY_BOUND_DIAGONAL_FRONT_CDT)
  pybind11_add_module(native_tri_authority_bound_diagonal_front_cdt
      native_tri_authority_bound_diagonal_front_cdt_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authority_bound_diagonal_front_cdt)
endif()
if(BUILD_NATIVE_TRI_AUTHORITY_BOUND_SURFACE_BL_FRONT)
  pybind11_add_module(native_tri_authority_bound_surface_bl_front
      native_tri_authority_bound_surface_bl_front_bind.cpp)
  autotessell_configure_first_party_native(native_tri_authority_bound_surface_bl_front)
endif()
if(BUILD_NATIVE_POLY_PROTECTED_CORPUS_RECEIPT)
  pybind11_add_module(native_poly_protected_corpus_receipt
      native_poly_protected_corpus_receipt_bind.cpp)
  autotessell_configure_first_party_native(native_poly_protected_corpus_receipt)
endif()
if(BUILD_NATIVE_HEX_CAD_AUTHORITY_CORPUS)
  pybind11_add_module(native_hex_cad_authority_corpus
      native_hex_cad_authority_corpus_bind.cpp)
  autotessell_configure_first_party_native(native_hex_cad_authority_corpus)
endif()
if(BUILD_NATIVE_SURFACE_AUTHORITY_CORPUS)
  pybind11_add_module(native_surface_authority_corpus
      native_surface_authority_corpus_bind.cpp)
  autotessell_configure_first_party_native(native_surface_authority_corpus)
endif()
if(BUILD_NATIVE_SURFACE_STL_AUTHORITY_INGRESS)
  pybind11_add_module(native_surface_stl_authority_ingress
      native_surface_stl_authority_ingress_bind.cpp)
  target_include_directories(native_surface_stl_authority_ingress PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_surface_stl_authority_ingress)
endif()
if(BUILD_NATIVE_SURFACE_BL_PARTITION_TRANSACTION)
  pybind11_add_module(native_surface_bl_partition_transaction
      native_surface_bl_partition_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_partition_transaction)
endif()
if(BUILD_NATIVE_SURFACE_BL_INDEPENDENT_VERIFIER)
  pybind11_add_module(native_surface_bl_independent_verifier
      surface_bl_independent_verifier/surface_bl_independent_verifier_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_independent_verifier)
endif()
if(BUILD_NATIVE_SURFACE_BL_ACTUAL_TRANSACTION)
  pybind11_add_module(native_surface_bl_actual_transaction
      native_surface_bl_actual_transaction_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_actual_transaction)
endif()
if(BUILD_NATIVE_SURFACE_BL_STRIP_WRITER)
  pybind11_add_module(native_surface_bl_strip_writer
      native_surface_bl_strip_writer_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_strip_writer)
endif()
if(BUILD_NATIVE_SURFACE_BL_HETEROGENEOUS_CERTIFICATE)
  pybind11_add_module(native_surface_bl_heterogeneous_zipper_certificate
      native_surface_bl_heterogeneous_zipper_certificate_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_heterogeneous_zipper_certificate)
endif()

# ???? robusthex module (optional) ????????????????????????????????????????????????????????????????????????????????????????????
# Only build if ROBUSTHEX_DIR contains the expected source tree.
if(BUILD_ROBUSTHEX AND EXISTS "${ROBUSTHEX_DIR}/src/meshio.cpp")

  # ???? Bundled TBB (old task API needed by bvh.cpp, removed in system TBB 2021)
  set(TBB_BUILD_STATIC          ON  CACHE BOOL "" FORCE)
  set(TBB_BUILD_SHARED          OFF CACHE BOOL "" FORCE)
  set(TBB_BUILD_TBBMALLOC       OFF CACHE BOOL "" FORCE)
  set(TBB_BUILD_TBBMALLOC_PROXY OFF CACHE BOOL "" FORCE)
  set(TBB_BUILD_TESTS           OFF CACHE BOOL "" FORCE)

  # Suppress GCC 13 -Wchanges-meaning error in old TBB code (Linux only)
  if(NOT MSVC)
    set(CMAKE_CXX_FLAGS_SAVE "${CMAKE_CXX_FLAGS}")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-changes-meaning")
  endif()
  add_subdirectory("${ROBUSTHEX_DIR}/ext/tbb" ext_build/tbb EXCLUDE_FROM_ALL)
  if(NOT MSVC)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS_SAVE}")
  endif()

  # ???? TetGen ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
  add_library(tetgen_lib STATIC
      "${TETGEN_DIR}/tetgen.cxx"
      "${TETGEN_DIR}/predicates.cxx"
  )
  target_compile_definitions(tetgen_lib PUBLIC TETLIBRARY)
  if(MSVC)
    target_compile_options(tetgen_lib PRIVATE /O2 /W0)
  else()
    target_compile_options(tetgen_lib PRIVATE -O2 -w)
  endif()

  set(ROBUSTHEX_SRCS
      "${ROBUSTHEX_DIR}/src/meshio.cpp"
      "${ROBUSTHEX_DIR}/src/batch.cpp"
      "${ROBUSTHEX_DIR}/src/bvh.cpp"
      "${ROBUSTHEX_DIR}/src/dedge.cpp"
      "${ROBUSTHEX_DIR}/src/hierarchy.cpp"
      "${ROBUSTHEX_DIR}/src/optimizer.cpp"
      "${ROBUSTHEX_DIR}/src/orient_triangle_mesh.cpp"
      "${ROBUSTHEX_DIR}/src/orientations.cpp"
      "${ROBUSTHEX_DIR}/src/positions.cpp"
      "${ROBUSTHEX_DIR}/src/extract.cpp"
      "${ROBUSTHEX_DIR}/src/extract3D.cpp"
      "${ROBUSTHEX_DIR}/src/subdivide.cpp"
      "${ROBUSTHEX_DIR}/src/global_types.cpp"
      "${RPLY_DIR}/rply.c"
  )

  pybind11_add_module(robusthex robusthex_bind.cpp ${ROBUSTHEX_SRCS})

  target_include_directories(robusthex PRIVATE
      "${ROBUSTHEX_DIR}/src"
      "${TETGEN_DIR}"
      "${PCG32_DIR}"
      "${RPLY_DIR}"
      "${FAKE_NANOGUI}"
      "${ROBUSTHEX_DIR}/ext/tbb/include"
  )

  target_compile_definitions(robusthex PRIVATE
      TETLIBRARY
      SINGLE_PRECISION
  )
  target_compile_options(robusthex PRIVATE ${_ROBUSTHEX_FLAGS})

  target_link_libraries(robusthex PRIVATE
      tetgen_lib
      tbb_static
      Eigen3::Eigen
  )

else()
  if(BUILD_ROBUSTHEX)
    message(STATUS
      "robusthex: ROBUSTHEX_DIR='${ROBUSTHEX_DIR}' not found or incomplete ??skipping.\n"
      "  Clone https://github.com/mlivesu/robust_hex_dominant_meshing and set -DROBUSTHEX_DIR=<path>")
  else()
    message(STATUS "robusthex: skipped (BUILD_ROBUSTHEX=OFF)")
  endif()
endif()

# ???? ftetwild module (vendored, MPL-2.0) ??????????????????????????????????????????????????????????????????????????
# third_party/fTetWild ??vendored ??fTetWild C++ ???뮞????슢諭?+ pybind11 wrap.
# ?紐? wildmeshing PyPI ???텕筌왖 ??뤵????볤탢??랁?揶쏆늿? algorithm ??in-tree 嚥??紐꾪뀱.
set(FTETWILD_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/fTetWild" CACHE PATH "")
if(BUILD_FTETWILD AND EXISTS "${FTETWILD_SRC_DIR}/CMakeLists.txt")
  message(STATUS "ftetwild: vendoring from '${FTETWILD_SRC_DIR}'")
  # fTetWild ????????main ??쎈뻬 ???뵬 + ???뮞???袁㏉?lib 筌???슢諭?
  set(FLOAT_TETWILD_TOPLEVEL_PROJECT OFF CACHE BOOL "" FORCE)
  set(FLOAT_TETWILD_ENABLE_TBB        ON  CACHE BOOL "" FORCE)
  set(FLOAT_TETWILD_USE_FLOAT         OFF CACHE BOOL "" FORCE)
  set(FLOAT_TETWILD_WITH_SANITIZERS   OFF CACHE BOOL "" FORCE)
  set(LIBIGL_USE_STATIC_LIBRARY       OFF CACHE BOOL "" FORCE)
  add_subdirectory("${FTETWILD_SRC_DIR}" ext_build/ftetwild EXCLUDE_FROM_ALL)

  pybind11_add_module(ftetwild ftetwild_bind.cpp)
  target_link_libraries(ftetwild PRIVATE FloatTetwild Eigen3::Eigen)
  target_compile_options(ftetwild PRIVATE -O2 -w)
else()
  if(BUILD_FTETWILD)
    message(STATUS "ftetwild: '${FTETWILD_SRC_DIR}' not found ??skipping.")
  endif()
endif()

# ???? cfmesh_native module (vendored, GPL-3) ????????????????????????????????????????????????????????????????????
set(CFMESH_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/cfmesh" CACHE PATH "")
if(BUILD_CFMESH AND EXISTS "${CFMESH_SRC_DIR}/CMakeLists.txt")
  message(STATUS "cfmesh_native: binding vendored cfMesh from '${CFMESH_SRC_DIR}'")
  find_package(Threads REQUIRED)
  pybind11_add_module(cfmesh_native cfmesh_bind.cpp)
  target_link_libraries(cfmesh_native PRIVATE Threads::Threads)
  target_compile_options(cfmesh_native PRIVATE -O2 -w)
else()
  if(BUILD_CFMESH)
    message(STATUS "cfmesh_native: '${CFMESH_SRC_DIR}' not found ??skipping.")
  endif()
endif()

option(AUTOTESSELL_BUILD_FIRST_PARTY_EVIDENCE
  "Generate fail-closed identity and ABI evidence for first-party native extensions" OFF)
set(AUTOTESSELL_SOURCE_IDENTITY "" CACHE STRING
  "Optional archive content identity; must equal the source-derived identity")
if(AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE)
  set(AUTOTESSELL_BUILD_FIRST_PARTY_EVIDENCE ON CACHE BOOL "" FORCE)
endif()

if(AUTOTESSELL_BUILD_FIRST_PARTY_EVIDENCE)
  foreach(target_name IN LISTS _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS)
    if(NOT TARGET ${target_name})
      message(FATAL_ERROR
        "First-party native evidence target '${target_name}' was not created")
    endif()
  endforeach()

  set(_AUTOTESSELL_SOURCE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
  set(_AUTOTESSELL_NATIVE_CONTRACT
      "${CMAKE_CURRENT_SOURCE_DIR}/native_build_contract.json")
  set(_AUTOTESSELL_NATIVE_MANIFEST
      "${CMAKE_CURRENT_BINARY_DIR}/autotessell_native_build_manifest.json")
  set(_AUTOTESSELL_IDENTITY_ARGS)
  if(AUTOTESSELL_SOURCE_IDENTITY)
    list(APPEND _AUTOTESSELL_IDENTITY_ARGS
      --source-identity "${AUTOTESSELL_SOURCE_IDENTITY}")
  endif()

  add_custom_target(native_build_evidence ALL
    COMMAND "${Python_EXECUTABLE}"
      "${_AUTOTESSELL_SOURCE_ROOT}/scripts/native_build_evidence.py" generate
      --contract "${_AUTOTESSELL_NATIVE_CONTRACT}"
      --source-root "${_AUTOTESSELL_SOURCE_ROOT}"
      --build-dir "${CMAKE_CURRENT_BINARY_DIR}"
      --output "${_AUTOTESSELL_NATIVE_MANIFEST}"
      --compiler-id "${CMAKE_CXX_COMPILER_ID}"
      --compiler-version "${CMAKE_CXX_COMPILER_VERSION}"
      --cxx-standard 23
      --os "${CMAKE_SYSTEM_NAME}"
      --build-type "${CMAKE_BUILD_TYPE}"
      --install-first-party-native "${AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE}"
      --build-cfmesh "${BUILD_CFMESH}"
      --build-cinolib-hex "${BUILD_CINOLIB_HEX}"
      --build-ftetwild "${BUILD_FTETWILD}"
      --build-robusthex "${BUILD_ROBUSTHEX}"
      ${_AUTOTESSELL_IDENTITY_ARGS}
    DEPENDS
      ${_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS}
      "${_AUTOTESSELL_NATIVE_CONTRACT}"
      "${_AUTOTESSELL_SOURCE_ROOT}/scripts/native_build_evidence.py"
    COMMENT "Generating first-party native build identity and ABI evidence"
    COMMAND_EXPAND_LISTS
    VERBATIM)
endif()

if(AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE)
  install(TARGETS ${_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS}
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .)
  install(FILES
    "${_AUTOTESSELL_NATIVE_MANIFEST}"
    DESTINATION .)
  install(FILES
    "${_AUTOTESSELL_NATIVE_CONTRACT}"
    DESTINATION .
    RENAME autotessell_native_build_contract.json)
endif()

if(BUILD_NATIVE_SURFACE_BL_FRONT_SHARED)
  # This planner is a candidate-only kernel. Keep it in the ordinary
  # developer build directory so the common loader can exercise the exact
  # artifact used by tests; its C++ runtime route remains explicitly
  # default-off until an authority-bound publishing gate is wired.
  pybind11_add_module(native_surface_bl_front_shared
      surface_bl_front_shared/surface_bl_front_shared_bind.cpp)
  autotessell_configure_first_party_native(native_surface_bl_front_shared)
endif()

if(BUILD_NATIVE_SURFACE_BL_FRONT_SHARED_OPTIMIZER)
  pybind11_add_module(native_surface_bl_front_shared_optimizer
      surface_bl_front_shared/surface_bl_front_shared_optimizer_bind.cpp)

if(BUILD_NATIVE_SURFACE_BL_FRONT_ACTUAL_V2)
  # Keep the nested developer package reachable from the repository build.
  # These modules are private/default-off at the product boundary; wiring them
  # here only makes the exact C++23 artifacts buildable and auditable.
  pybind11_add_module(native_brep_front_evidence_v2
      surface_bl_front_shared/brep_front_evidence_v2_bind.cpp)
  pybind11_add_module(native_surface_bl_front_actual_v2_ingress
      surface_bl_front_shared/surface_bl_front_actual_v2_ingress_bind.cpp)
  pybind11_add_module(native_surface_bl_front_actual_v2_transaction
      surface_bl_front_shared/surface_bl_front_actual_v2_transaction_bind.cpp)
  pybind11_add_module(native_surface_bl_front_actual_v2_producer
      surface_bl_front_shared/surface_bl_front_actual_v2_producer_bind.cpp)
  foreach(_target IN ITEMS
      native_brep_front_evidence_v2
      native_surface_bl_front_actual_v2_ingress
      native_surface_bl_front_actual_v2_transaction
      native_surface_bl_front_actual_v2_producer)
    autotessell_configure_first_party_native(${_target})
    set_target_properties(${_target} PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
      RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  endforeach()
endif()
  target_include_directories(native_surface_bl_front_shared_optimizer PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/surface_bl_front_shared")
  autotessell_configure_first_party_native(native_surface_bl_front_shared_optimizer)
endif()
if(BUILD_NATIVE_WALL_EDGE_METRIC_CORRIDOR)
  pybind11_add_module(native_wall_edge_metric_corridor
      native_wall_edge_metric_corridor.cpp)
  autotessell_configure_first_party_native(native_wall_edge_metric_corridor)
endif()
if(BUILD_NATIVE_TRANSACTION_INTENT)
  pybind11_add_module(native_transaction_intent
      native_transaction_intent/native_transaction_intent_bind.cpp
      native_transaction_intent/native_transaction_intent_v1.cpp)
  autotessell_configure_first_party_native(native_transaction_intent)
endif()
if(BUILD_NATIVE_TRANSACTION_EXECUTOR)
  pybind11_add_module(native_transaction_executor
      native_transaction_executor/native_transaction_executor_v1.cpp
      native_transaction_executor/native_transaction_executor_bind.cpp)
  autotessell_configure_first_party_native(native_transaction_executor)
endif()
