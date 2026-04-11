# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-build"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/tmp"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/src/geogram-populate-stamp"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/src"
  "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/src/geogram-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/src/geogram-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-subbuild/geogram-populate-prefix/src/geogram-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
