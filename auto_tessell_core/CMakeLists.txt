cmake_minimum_required(VERSION 3.15)
project(auto_tessell_core CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Build options ────────────────────────────────────────────────────────────
option(BUILD_ROBUSTHEX "Build robusthex pybind11 module (needs ROBUSTHEX_DIR source)" ON)
option(BUILD_FTETWILD  "Build vendored fTetWild pybind11 module (third_party/fTetWild)" ON)
option(BUILD_CFMESH    "Build vendored cfMesh pybind11 module (third_party/cfmesh)" ON)

# ── Paths to cloned repos (define first — used by subdirectory builds) ───────
set(CINOLIB_DIR     "/tmp/hexmesh_build/cinolib"                    CACHE PATH "")
set(ROBUSTHEX_DIR   "/tmp/hexmesh_build/robust_hex_dominant_meshing" CACHE PATH "")
set(TETGEN_DIR      "${ROBUSTHEX_DIR}/ext/tetgen"                    CACHE PATH "")
set(PCG32_DIR       "${ROBUSTHEX_DIR}/ext/pcg32"                     CACHE PATH "")
set(RPLY_DIR        "${ROBUSTHEX_DIR}/ext/rply"                      CACHE PATH "")
set(FAKE_NANOGUI    "${CMAKE_CURRENT_SOURCE_DIR}/fake_nanogui"       CACHE PATH "")

# ── pybind11 ────────────────────────────────────────────────────────────────
find_package(pybind11 CONFIG REQUIRED)

# ── Eigen3 ──────────────────────────────────────────────────────────────────
find_package(Eigen3 3.3 REQUIRED NO_MODULE)

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

# ── cinolib_hex module ───────────────────────────────────────────────────────
pybind11_add_module(cinolib_hex cinolib_hex_bind.cpp)
target_include_directories(cinolib_hex PRIVATE "${CINOLIB_DIR}/include")
target_compile_options(cinolib_hex PRIVATE ${_CINOLIB_FLAGS})
target_link_libraries(cinolib_hex PRIVATE Eigen3::Eigen)

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
