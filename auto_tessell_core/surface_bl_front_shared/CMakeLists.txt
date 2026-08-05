cmake_minimum_required(VERSION 3.20)
project(native_surface_bl_front_shared LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 3.0 CONFIG REQUIRED)
pybind11_add_module(native_brep_front_evidence brep_front_evidence_bind.cpp)
pybind11_add_module(native_brep_front_evidence_v2 brep_front_evidence_v2_bind.cpp)

pybind11_add_module(native_surface_bl_front_shared surface_bl_front_shared_bind.cpp)
target_compile_features(native_surface_bl_front_shared PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front_shared PRIVATE -O3 -Wall -Wextra -Wpedantic)
pybind11_add_module(native_surface_bl_front_shared_optimizer surface_bl_front_shared_optimizer_bind.cpp)
pybind11_add_module(native_surface_bl_strip_writer ../native_surface_bl_strip_writer_bind.cpp)
target_include_directories(native_surface_bl_strip_writer PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/..)
target_compile_features(native_surface_bl_strip_writer PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_strip_writer PRIVATE -O3 -Wall -Wextra -Wpedantic)
pybind11_add_module(native_surface_bl_heterogeneous_zipper_certificate
    ../native_surface_bl_heterogeneous_zipper_certificate_bind.cpp)
target_compile_features(native_surface_bl_heterogeneous_zipper_certificate PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_heterogeneous_zipper_certificate PRIVATE -O3 -Wall -Wextra -Wpedantic)
pybind11_add_module(native_surface_bl_folded_plate surface_bl_folded_plate_bind.cpp)
pybind11_add_module(native_surface_bl_readback_verifier surface_bl_readback_verifier_bind.cpp)
target_compile_features(native_surface_bl_readback_verifier PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_readback_verifier PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_features(native_surface_bl_folded_plate PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_folded_plate PRIVATE -O3 -Wall -Wextra -Wpedantic)
pybind11_add_module(native_surface_bl_front_authority_bridge surface_bl_front_authority_bridge_bind.cpp)
pybind11_add_module(native_surface_bl_front_actual_v2_ingress surface_bl_front_actual_v2_ingress_bind.cpp)
pybind11_add_module(native_surface_bl_front_actual_v2_transaction surface_bl_front_actual_v2_transaction_bind.cpp)
pybind11_add_module(native_surface_bl_front_actual_v2_producer surface_bl_front_actual_v2_producer_bind.cpp)
pybind11_add_module(native_tet_hex_authority_bound_consumer native_tet_hex_authority_bound_consumer_bind.cpp)
target_compile_features(native_tet_hex_authority_bound_consumer PRIVATE cxx_std_23)
target_compile_options(native_tet_hex_authority_bound_consumer PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_features(native_surface_bl_front_actual_v2_transaction PRIVATE cxx_std_23)
target_compile_features(native_surface_bl_front_actual_v2_producer PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front_actual_v2_producer PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_options(native_surface_bl_front_actual_v2_transaction PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_features(native_surface_bl_front_actual_v2_ingress PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front_actual_v2_ingress PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_features(native_surface_bl_front_authority_bridge PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front_authority_bridge PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_features(native_surface_bl_front_shared_optimizer PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front_shared_optimizer PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_options(native_brep_front_evidence_v2 PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_compile_options(native_brep_front_evidence PRIVATE -O3 -Wall -Wextra -Wpedantic)

set(AUTOTESSSELL_OCCT_SDK_ROOT "" CACHE PATH
    "Provenance-matched OCCT SDK root for the native B-Rep ingress shim")
set(AUTOTESSSELL_OCCT_NATIVE_READY OFF)
if(AUTOTESSSELL_OCCT_SDK_ROOT)
    find_path(AUTOTESSSELL_OCCT_INCLUDE_DIR
        NAMES BRep_Tool.hxx Standard_Version.hxx
        PATHS
            ${AUTOTESSSELL_OCCT_SDK_ROOT}/include/opencascade
            ${AUTOTESSSELL_OCCT_SDK_ROOT}/include
        NO_DEFAULT_PATH)
    set(_autotessell_occt_lib_names
        TKernel TKMath TKBRep TKGeomBase TKG2d TKTopAlgo TKXDE TKXCAF TKSTEP
        TKSTEP209 TKSTEPAttr TKSTEPBase)
    set(_autotessell_occt_libs)
    foreach(_lib_name IN LISTS _autotessell_occt_lib_names)
        find_library(_lib_path NAMES ${_lib_name}
            PATHS ${AUTOTESSSELL_OCCT_SDK_ROOT}/lib
                  ${AUTOTESSSELL_OCCT_SDK_ROOT}/lib64
            NO_DEFAULT_PATH)
        if(NOT _lib_path)
            set(_autotessell_occt_libs)
            break()
        endif()
        list(APPEND _autotessell_occt_libs ${_lib_path})
    endforeach()
    if(AUTOTESSSELL_OCCT_INCLUDE_DIR AND _autotessell_occt_libs)
        target_include_directories(native_brep_front_evidence_v2 PRIVATE
            ${AUTOTESSSELL_OCCT_INCLUDE_DIR})
        target_link_libraries(native_brep_front_evidence_v2 PRIVATE
            ${_autotessell_occt_libs})
        target_compile_definitions(native_brep_front_evidence_v2 PRIVATE
            AUTOTESSSELL_OCCT_NATIVE_ENABLED=1)
        set(AUTOTESSSELL_OCCT_NATIVE_READY ON)
    endif()
endif()
message(STATUS "AutoTessell OCCT native ingress ready: ${AUTOTESSSELL_OCCT_NATIVE_READY}")
