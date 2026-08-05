cmake_minimum_required(VERSION 3.20)
project(native_surface_bl_front LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 3.0 CONFIG REQUIRED)

pybind11_add_module(native_surface_bl_front surface_bl_front_bind.cpp)
target_compile_features(native_surface_bl_front PRIVATE cxx_std_23)
target_compile_options(native_surface_bl_front PRIVATE -O3 -Wall -Wextra -Wpedantic)
