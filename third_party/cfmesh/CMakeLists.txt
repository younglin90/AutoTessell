# ─────────────────────────────────────────────────────────────────────────────
# cfMesh + minimal OpenFOAM core — vendored build for AutoTessell.
#
# Replaces OpenFOAM's wmake build with cmake. This file is original work
# authored for AutoTessell; the source code under openfoam_min/ and meshLibrary/
# is GPL-3.0 (see LICENSE.GPL3 + per-file headers).
#
# Build strategy:
#   1) Generate `lnInclude/` per lib (flat symlink farm of .H files) — wmake's
#      original mechanism for resolving #include "X.H" without subdir paths.
#   2) Build each lib in dependency order:
#        OpenFOAM → fileFormats → surfMesh → triSurface → meshTools →
#        finiteVolume → cfmesh_meshlib
#   3) Build 3 executables: cartesianMesh, tetMesh, pMesh.
#   4) AutoTessell pybind11 module links against cfmesh_meshlib + OpenFOAM
#      libs (see auto_tessell_core/cfmesh_bind.cpp — separate target).
# ─────────────────────────────────────────────────────────────────────────────
cmake_minimum_required(VERSION 3.20)
project(autotessell_cfmesh CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# OpenFOAM expects these globally.
add_compile_definitions(
    WM_LABEL_SIZE=32
    WM_DP                       # double precision
    NoRepository                # disables auto-instantiation of templates
    OPENFOAM=2406               # version stamp (Foundation v-dev ≈ 2406-compat)
)
# Quiet OpenFOAM's many deprecated/sign-compare warnings.
add_compile_options(-w -fPIC)

find_package(Threads REQUIRED)

set(CFMESH_ROOT ${CMAKE_CURRENT_SOURCE_DIR})
set(OF_SRC ${CFMESH_ROOT}/openfoam_min/src)
set(CFMESH_SRC ${CFMESH_ROOT}/meshLibrary)

# ─── lnInclude generator: collect all .H + .C files in a lib subtree ───────
# Reproduces wmake's `wmakeLnInclude` step. OpenFOAM template impl .C files
# are #include-d from their .H counterparts, so both must be findable in the
# flat lnInclude dir. The actual .C compilation list is computed separately
# via of_collect_sources, which excludes lnInclude/.
function(of_make_ln_include LIB_DIR OUT_DIR)
    file(GLOB_RECURSE _hdrs
         RELATIVE ${LIB_DIR}
         ${LIB_DIR}/*.H ${LIB_DIR}/*.h ${LIB_DIR}/*.hpp ${LIB_DIR}/*.hxx
         ${LIB_DIR}/*.C ${LIB_DIR}/*.cpp ${LIB_DIR}/*.cxx)
    file(MAKE_DIRECTORY ${OUT_DIR})
    foreach(_h IN LISTS _hdrs)
        # Skip already-in-lnInclude paths to avoid recursion.
        if(_h MATCHES "lnInclude/")
            continue()
        endif()
        get_filename_component(_b ${_h} NAME)
        if(NOT EXISTS "${OUT_DIR}/${_b}")
            file(CREATE_LINK "${LIB_DIR}/${_h}" "${OUT_DIR}/${_b}" SYMBOLIC)
        endif()
    endforeach()
endfunction()

# ─── 1) Generate lnInclude for every dependency lib ─────────────────────────
of_make_ln_include(${OF_SRC}/OpenFOAM           ${OF_SRC}/OpenFOAM/lnInclude)
of_make_ln_include(${OF_SRC}/OSspecific/POSIX   ${OF_SRC}/OSspecific/POSIX/lnInclude)
of_make_ln_include(${OF_SRC}/Pstream/dummy      ${OF_SRC}/Pstream/dummy/lnInclude)
of_make_ln_include(${OF_SRC}/fileFormats   ${OF_SRC}/fileFormats/lnInclude)
of_make_ln_include(${OF_SRC}/surfMesh      ${OF_SRC}/surfMesh/lnInclude)
of_make_ln_include(${OF_SRC}/triSurface    ${OF_SRC}/triSurface/lnInclude)
of_make_ln_include(${OF_SRC}/meshTools     ${OF_SRC}/meshTools/lnInclude)
of_make_ln_include(${OF_SRC}/finiteVolume  ${OF_SRC}/finiteVolume/lnInclude)
of_make_ln_include(${OF_SRC}/parallel      ${OF_SRC}/parallel/lnInclude)
of_make_ln_include(${OF_SRC}/sampling      ${OF_SRC}/sampling/lnInclude)
of_make_ln_include(${CFMESH_SRC}           ${CFMESH_SRC}/lnInclude)

# ─── 2) Helper: collect .C files recursively, excluding template-impl .C ────
# OpenFOAM convention (with NoRepository defined): .H header #include "X.C"
# the matching template .C → that .C must NOT be compiled separately, otherwise
# multiple-definition errors occur. We detect this by scanning .H for #include
# lines that reference a sibling .C basename and exclude those.
function(of_collect_sources OUT_VAR ROOT)
    file(GLOB_RECURSE _src ${ROOT}/*.C ${ROOT}/*.cpp ${ROOT}/*.cxx)
    list(FILTER _src EXCLUDE REGEX "/lnInclude/")
    list(FILTER _src EXCLUDE REGEX "/Test|/test/")
    list(FILTER _src EXCLUDE REGEX "/dummyThirdParty/")

    # Build a set of "template impl" .C basenames. Scan EVERY .H and .C file
    # for `#include "X.C"` lines — .C files include other .C files transitively.
    file(GLOB_RECURSE _scan_all ${ROOT}/*.H ${ROOT}/*.C)
    list(FILTER _scan_all EXCLUDE REGEX "/lnInclude/")
    set(_tmpl_impls "")
    foreach(_f IN LISTS _scan_all)
        # OpenFOAM uses both `#include` and `#   include` (with spaces).
        file(STRINGS ${_f} _lines REGEX "^[ \t]*#[ \t]*include[ \t]+\"[A-Za-z0-9_]+\\.C\"")
        foreach(_line IN LISTS _lines)
            string(REGEX MATCH "\"([A-Za-z0-9_]+\\.C)\"" _m "${_line}")
            if(CMAKE_MATCH_1)
                list(APPEND _tmpl_impls ${CMAKE_MATCH_1})
            endif()
        endforeach()
    endforeach()
    list(REMOVE_DUPLICATES _tmpl_impls)

    # Filter out .C files whose basename matches any detected template impl.
    set(_filtered "")
    foreach(_c IN LISTS _src)
        get_filename_component(_b ${_c} NAME)
        if(NOT _b IN_LIST _tmpl_impls)
            list(APPEND _filtered ${_c})
        endif()
    endforeach()
    set(${OUT_VAR} ${_filtered} PARENT_SCOPE)
endfunction()

# ─── 3) Build OpenFOAM core (OpenFOAM + OSspecific POSIX merged) ────────────
of_collect_sources(_openfoam_src    ${OF_SRC}/OpenFOAM)
of_collect_sources(_posix_src       ${OF_SRC}/OSspecific/POSIX)
of_collect_sources(_pstream_src     ${OF_SRC}/Pstream/dummy)
add_library(of_openfoam STATIC ${_openfoam_src} ${_posix_src} ${_pstream_src})
# OpenFOAM 의 circular dep (UPstream <-> Pstream) 해소: 모든 lib 에 Pstream.H 가
# include path 의 가장 앞에 위치하도록. -include 로 강제 prepend 하지는 않고
# include path 만 정렬.
target_include_directories(of_openfoam PUBLIC
    ${OF_SRC}/Pstream/dummy/lnInclude
    ${OF_SRC}/OpenFOAM/lnInclude
    ${OF_SRC}/OSspecific/POSIX/lnInclude
)
target_link_libraries(of_openfoam PUBLIC Threads::Threads dl)

# ─── 4) Build dependent libs ────────────────────────────────────────────────
of_collect_sources(_fileFormats_src ${OF_SRC}/fileFormats)
add_library(of_fileFormats STATIC ${_fileFormats_src})
target_include_directories(of_fileFormats PUBLIC ${OF_SRC}/fileFormats/lnInclude)
target_link_libraries(of_fileFormats PUBLIC of_openfoam)

of_collect_sources(_surfMesh_src ${OF_SRC}/surfMesh)
add_library(of_surfMesh STATIC ${_surfMesh_src})
target_include_directories(of_surfMesh PUBLIC ${OF_SRC}/surfMesh/lnInclude)
target_link_libraries(of_surfMesh PUBLIC of_fileFormats)

of_collect_sources(_triSurface_src ${OF_SRC}/triSurface)
add_library(of_triSurface STATIC ${_triSurface_src})
target_include_directories(of_triSurface PUBLIC ${OF_SRC}/triSurface/lnInclude)
target_link_libraries(of_triSurface PUBLIC of_surfMesh)

of_collect_sources(_meshTools_src ${OF_SRC}/meshTools)
add_library(of_meshTools STATIC ${_meshTools_src})
target_include_directories(of_meshTools PUBLIC ${OF_SRC}/meshTools/lnInclude)
target_link_libraries(of_meshTools PUBLIC of_triSurface)

of_collect_sources(_finiteVolume_src ${OF_SRC}/finiteVolume)
add_library(of_finiteVolume STATIC ${_finiteVolume_src})
target_include_directories(of_finiteVolume PUBLIC ${OF_SRC}/finiteVolume/lnInclude)
target_link_libraries(of_finiteVolume PUBLIC of_meshTools)

# ─── 5) Build cfMesh meshLibrary ────────────────────────────────────────────
of_collect_sources(_cfmesh_src ${CFMESH_SRC})
# Exclude OpenMP-only files if compiler doesn't have it.
add_library(cfmesh_meshlib STATIC ${_cfmesh_src})
target_include_directories(cfmesh_meshlib PUBLIC ${CFMESH_SRC}/lnInclude)
target_link_libraries(cfmesh_meshlib PUBLIC
    of_finiteVolume of_meshTools of_surfMesh of_fileFormats of_openfoam)

find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    target_link_libraries(cfmesh_meshlib PUBLIC OpenMP::OpenMP_CXX)
endif()

# ─── 6) Build executables ───────────────────────────────────────────────────
foreach(_exe IN ITEMS cartesianMesh tetMesh pMesh)
    set(_exe_src ${CFMESH_ROOT}/executables/${_exe}/${_exe}.C)
    if(EXISTS ${_exe_src})
        add_executable(${_exe} ${_exe_src})
        target_link_libraries(${_exe} PRIVATE cfmesh_meshlib)
    endif()
endforeach()
