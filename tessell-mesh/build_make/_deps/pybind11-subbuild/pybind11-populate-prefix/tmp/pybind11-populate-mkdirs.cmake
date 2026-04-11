# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-src"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-build"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/tmp"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/src/pybind11-populate-stamp"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/src"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/src/pybind11-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/src/pybind11-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/pybind11-subbuild/pybind11-populate-prefix/src/pybind11-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
