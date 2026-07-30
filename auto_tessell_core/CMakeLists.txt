cmake_minimum_required(VERSION 3.20)
project(auto_tessell_core CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Build options ────────────────────────────────────────────────────────────
option(BUILD_CINOLIB_HEX "Build optional cinolib_hex adapter (needs CINOLIB_DIR headers)" OFF)
option(BUILD_ROBUSTHEX "Build robusthex pybind11 module (needs ROBUSTHEX_DIR source)" ON)
option(BUILD_FTETWILD  "Build vendored fTetWild pybind11 module (third_party/fTetWild)" ON)
option(BUILD_CFMESH    "Build vendored cfMesh pybind11 module (third_party/cfmesh)" ON)
option(BUILD_NATIVE_METRICS "Build native metric kernels for Python checker" ON)
option(BUILD_NATIVE_BL "Build native boundary-layer search kernels" ON)
option(BUILD_NATIVE_POLYMESH "Build native polyMesh topology kernel" ON)
option(BUILD_NATIVE_SNAP "Build native surface snap candidate kernel" ON)
option(BUILD_NATIVE_SURFACE_PADDING "Build native planar surface padding kernel" ON)
option(BUILD_NATIVE_HEX_QUALITY "Build native hex quality kernel" ON)
option(BUILD_NATIVE_TET_PREDICATES "Build native exact tetrahedral predicate kernel" ON)
option(BUILD_NATIVE_TET_QOPT "Build native tetrahedral quality-optimizer kernel" ON)
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
endif()

# ── Paths to cloned repos (define first — used by subdirectory builds) ───────
set(CINOLIB_DIR     "/tmp/hexmesh_build/cinolib"                    CACHE PATH "")
set(ROBUSTHEX_DIR   "/tmp/hexmesh_build/robust_hex_dominant_meshing" CACHE PATH "")
set(TETGEN_DIR      "${ROBUSTHEX_DIR}/ext/tetgen"                    CACHE PATH "")
set(PCG32_DIR       "${ROBUSTHEX_DIR}/ext/pcg32"                     CACHE PATH "")
set(RPLY_DIR        "${ROBUSTHEX_DIR}/ext/rply"                      CACHE PATH "")
set(FAKE_NANOGUI    "${CMAKE_CURRENT_SOURCE_DIR}/fake_nanogui"       CACHE PATH "")

# ── pybind11 ────────────────────────────────────────────────────────────────
set(PYBIND11_FINDPYTHON ON)
find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 3.0 CONFIG REQUIRED)

# ── Eigen3 ──────────────────────────────────────────────────────────────────
if(BUILD_CINOLIB_HEX OR BUILD_ROBUSTHEX OR BUILD_FTETWILD)
  find_package(Eigen3 3.3 REQUIRED NO_MODULE)
endif()

set(_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS
  native_metrics
  native_bl
  native_polymesh
  native_snap
  native_surface_padding
  native_hex_quality
  native_tet_predicates
  native_tet_qopt)

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

# ── Compiler flag helpers ────────────────────────────────────────────────────
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

# ── cinolib_hex adapter (optional, external source) ─────────────────────────
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

# ── native metric kernels ────────────────────────────────────────────────────
if(BUILD_NATIVE_METRICS)
  pybind11_add_module(native_metrics native_metrics_bind.cpp)
  autotessell_configure_first_party_native(native_metrics)
endif()

# ── native polyMesh topology kernel ───────────────────────────────────────
# Native boundary-layer search kernels.
if(BUILD_NATIVE_BL)
  pybind11_add_module(native_bl native_bl_bind.cpp)
  autotessell_configure_first_party_native(native_bl)
endif()

if(BUILD_NATIVE_POLYMESH)
  pybind11_add_module(native_polymesh native_polymesh_bind.cpp)
  autotessell_configure_first_party_native(native_polymesh)
endif()

# ── native surface snap candidate kernel ──────────────────────────────────
if(BUILD_NATIVE_SNAP)
  pybind11_add_module(native_snap native_snap_bind.cpp)
  autotessell_configure_first_party_native(native_snap)
endif()

# ── native planar surface padding kernel ──────────────────────────────────
if(BUILD_NATIVE_SURFACE_PADDING)
  pybind11_add_module(native_surface_padding native_surface_padding_bind.cpp)
  autotessell_configure_first_party_native(native_surface_padding)
endif()

# ── native hex quality kernel ──────────────────────────────────────────────
if(BUILD_NATIVE_HEX_QUALITY)
  pybind11_add_module(native_hex_quality native_hex_quality_bind.cpp)
  autotessell_configure_first_party_native(native_hex_quality)
endif()

# ── native exact tetrahedral predicates ───────────────────────────────────
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

# ── native tetrahedral quality optimizer ──────────────────────────────────
if(BUILD_NATIVE_TET_QOPT)
  pybind11_add_module(native_tet_qopt native_tet_qopt_bind.cpp)
  autotessell_configure_first_party_native(native_tet_qopt)
endif()

# ── robusthex module (optional) ──────────────────────────────────────────────
# Only build if ROBUSTHEX_DIR contains the expected source tree.
if(BUILD_ROBUSTHEX AND EXISTS "${ROBUSTHEX_DIR}/src/meshio.cpp")

  # ── Bundled TBB (old task API needed by bvh.cpp, removed in system TBB 2021)
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

  # ── TetGen ─────────────────────────────────────────────────────────────────
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
      "robusthex: ROBUSTHEX_DIR='${ROBUSTHEX_DIR}' not found or incomplete — skipping.\n"
      "  Clone https://github.com/mlivesu/robust_hex_dominant_meshing and set -DROBUSTHEX_DIR=<path>")
  else()
    message(STATUS "robusthex: skipped (BUILD_ROBUSTHEX=OFF)")
  endif()
endif()

# ── ftetwild module (vendored, MPL-2.0) ─────────────────────────────────────
# third_party/fTetWild 에 vendored 된 fTetWild C++ 소스를 빌드 + pybind11 wrap.
# 외부 wildmeshing PyPI 패키지 의존을 제거하고 같은 algorithm 을 in-tree 로 호출.
set(FTETWILD_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/fTetWild" CACHE PATH "")
if(BUILD_FTETWILD AND EXISTS "${FTETWILD_SRC_DIR}/CMakeLists.txt")
  message(STATUS "ftetwild: vendoring from '${FTETWILD_SRC_DIR}'")
  # fTetWild 의 옵션 — main 실행 파일 + 테스트 끄고 lib 만 빌드.
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
    message(STATUS "ftetwild: '${FTETWILD_SRC_DIR}' not found — skipping.")
  endif()
endif()

# ── cfmesh_native module (vendored, GPL-3) ──────────────────────────────────
set(CFMESH_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/cfmesh" CACHE PATH "")
if(BUILD_CFMESH AND EXISTS "${CFMESH_SRC_DIR}/CMakeLists.txt")
  message(STATUS "cfmesh_native: binding vendored cfMesh from '${CFMESH_SRC_DIR}'")
  find_package(Threads REQUIRED)
  pybind11_add_module(cfmesh_native cfmesh_bind.cpp)
  target_link_libraries(cfmesh_native PRIVATE Threads::Threads)
  target_compile_options(cfmesh_native PRIVATE -O2 -w)
else()
  if(BUILD_CFMESH)
    message(STATUS "cfmesh_native: '${CFMESH_SRC_DIR}' not found — skipping.")
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
