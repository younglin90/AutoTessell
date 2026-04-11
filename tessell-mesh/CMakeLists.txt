cmake_minimum_required(VERSION 3.20)
project(tessell_mesh VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ──────────────────────────────────────────────────────────────
# Optional: build only the C++ library (no Python)
# ──────────────────────────────────────────────────────────────
option(TESSELL_BUILD_PYTHON "Build Python pybind11 extension" ON)
option(TESSELL_BUILD_TESTS  "Build C++ unit tests"            OFF)
option(TESSELL_VERBOSE_MESH "Enable geogram verbose output"   OFF)

include(FetchContent)
set(FETCHCONTENT_QUIET OFF)

# ──────────────────────────────────────────────────────────────
# Dependency: pybind11
# ──────────────────────────────────────────────────────────────
if(TESSELL_BUILD_PYTHON)
    FetchContent_Declare(pybind11
        GIT_REPOSITORY https://github.com/pybind/pybind11.git
        GIT_TAG        v2.13.1
        GIT_SHALLOW    TRUE
    )
    FetchContent_MakeAvailable(pybind11)
endif()

# ──────────────────────────────────────────────────────────────
# Dependency: geogram (BSD-3-Clause)
# ──────────────────────────────────────────────────────────────
FetchContent_Declare(geogram
    GIT_REPOSITORY https://github.com/BrunoLevy/geogram.git
    GIT_TAG        v1.9.5
    GIT_SHALLOW    TRUE
)
FetchContent_GetProperties(geogram)
if(NOT geogram_POPULATED)
    FetchContent_Populate(geogram)
    # Disable graphics and tests to speed up build
    set(GEOGRAM_WITH_GRAPHICS     OFF CACHE BOOL "" FORCE)
    set(GEOGRAM_WITH_LEGACY_NUMERICS OFF CACHE BOOL "" FORCE)
    set(GEOGRAM_LIB_ONLY          ON  CACHE BOOL "" FORCE)
    add_subdirectory(${geogram_SOURCE_DIR} ${geogram_BINARY_DIR} EXCLUDE_FROM_ALL)
endif()

# ──────────────────────────────────────────────────────────────
# Dependency: CDT — Constrained Delaunay Triangulation (MPL-2.0)
# Header-only, zero external dependencies
# ──────────────────────────────────────────────────────────────
FetchContent_Declare(CDT
    GIT_REPOSITORY https://github.com/artem-ogre/CDT.git
    GIT_TAG        1.4.4
    GIT_SHALLOW    TRUE
)
FetchContent_GetProperties(CDT)
if(NOT cdt_POPULATED)
    FetchContent_Populate(CDT)
    # CDT ships its CMakeLists.txt under CDT/
    set(CDT_USE_AS_COMPILED_LIBRARY OFF CACHE BOOL "" FORCE)
    add_subdirectory(${cdt_SOURCE_DIR}/CDT ${cdt_BINARY_DIR} EXCLUDE_FROM_ALL)
endif()

# ──────────────────────────────────────────────────────────────
# Core C++ library: tessell_mesh_core
# ──────────────────────────────────────────────────────────────
add_library(tessell_mesh_core STATIC
    src/mesh2d.cpp
    src/mesh3d.cpp
    src/of_writer.cpp
)

target_include_directories(tessell_mesh_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

target_link_libraries(tessell_mesh_core
    PUBLIC
        geogram          # geogram target exposed by geogram's CMakeLists
        CDT::CDT
)

if(TESSELL_VERBOSE_MESH)
    target_compile_definitions(tessell_mesh_core PUBLIC TESSELL_VERBOSE)
endif()

# ──────────────────────────────────────────────────────────────
# Python extension: tessell_mesh (pybind11 module)
# ──────────────────────────────────────────────────────────────
if(TESSELL_BUILD_PYTHON)
    pybind11_add_module(tessell_mesh src/bindings.cpp)

    target_link_libraries(tessell_mesh PRIVATE tessell_mesh_core)

    # Place the .so next to the Python source
    set_target_properties(tessell_mesh PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../backend/mesh"
    )
endif()

# ──────────────────────────────────────────────────────────────
# Optional C++ tests
# ──────────────────────────────────────────────────────────────
if(TESSELL_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
