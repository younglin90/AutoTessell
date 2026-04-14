cmake_minimum_required(VERSION 3.15)
project(auto_tessell_core CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Paths to cloned repos (define first — used by subdirectory builds) ───────
set(CINOLIB_DIR     "/tmp/hexmesh_build/cinolib"                    CACHE PATH "")
set(ROBUSTHEX_DIR   "/tmp/hexmesh_build/robust_hex_dominant_meshing" CACHE PATH "")
set(TETGEN_DIR      "${ROBUSTHEX_DIR}/ext/tetgen"                    CACHE PATH "")
set(PCG32_DIR       "${ROBUSTHEX_DIR}/ext/pcg32"                     CACHE PATH "")
set(RPLY_DIR        "${ROBUSTHEX_DIR}/ext/rply"                      CACHE PATH "")
set(FAKE_NANOGUI    "${CMAKE_CURRENT_SOURCE_DIR}/fake_nanogui"       CACHE PATH "")

# ── pybind11 ────────────────────────────────────────────────────────────────
find_package(pybind11 CONFIG REQUIRED)

# ── Eigen3 (system) ─────────────────────────────────────────────────────────
find_package(Eigen3 3.3 REQUIRED NO_MODULE)

# ── Bundled TBB (old task API needed by bvh.cpp, removed in system TBB 2021) ─
set(TBB_BUILD_STATIC          ON  CACHE BOOL "" FORCE)
set(TBB_BUILD_SHARED          OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_TBBMALLOC       OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_TBBMALLOC_PROXY OFF CACHE BOOL "" FORCE)
set(TBB_BUILD_TESTS           OFF CACHE BOOL "" FORCE)
# GCC 13 treats -Wchanges-meaning as error in C++17 — suppress for old TBB code
set(CMAKE_CXX_FLAGS_SAVE "${CMAKE_CXX_FLAGS}")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-changes-meaning")
add_subdirectory("${ROBUSTHEX_DIR}/ext/tbb" ext_build/tbb EXCLUDE_FROM_ALL)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS_SAVE}")

# ── TetGen ───────────────────────────────────────────────────────────────────
add_library(tetgen_lib STATIC
    "${TETGEN_DIR}/tetgen.cxx"
    "${TETGEN_DIR}/predicates.cxx"
)
target_compile_definitions(tetgen_lib PUBLIC TETLIBRARY)
target_compile_options(tetgen_lib PRIVATE -O2 -w)

# ── cinolib_hex module ───────────────────────────────────────────────────────
pybind11_add_module(cinolib_hex cinolib_hex_bind.cpp)
target_include_directories(cinolib_hex PRIVATE "${CINOLIB_DIR}/include")
target_compile_options(cinolib_hex PRIVATE -O3 -march=native -w)
target_link_libraries(cinolib_hex PRIVATE Eigen3::Eigen)

# ── robusthex module ─────────────────────────────────────────────────────────
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
    "${ROBUSTHEX_DIR}/ext/tbb/include"  # bundled TBB headers (old API)
)

target_compile_definitions(robusthex PRIVATE
    TETLIBRARY
    SINGLE_PRECISION
)
target_compile_options(robusthex PRIVATE -O2 -w -Wno-changes-meaning)

target_link_libraries(robusthex PRIVATE
    tetgen_lib
    tbb_static      # bundled TBB with old task API
    Eigen3::Eigen
)
