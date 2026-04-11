# Install script for directory: /home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src/src/lib/geogram

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-build/src/lib/geogram/third_party/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit" OR NOT CMAKE_INSTALL_COMPONENT)
  foreach(file
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1.9.5"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1"
      )
    if(EXISTS "${file}" AND
       NOT IS_SYMLINK "${file}")
      file(RPATH_CHECK
           FILE "${file}"
           RPATH "/usr/local/lib")
    endif()
  endforeach()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES
    "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so.1.9.5"
    "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so.1"
    )
  foreach(file
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1.9.5"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1"
      )
    if(EXISTS "${file}" AND
       NOT IS_SYMLINK "${file}")
      file(RPATH_CHANGE
           FILE "${file}"
           OLD_RPATH "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src/build_make/lib:"
           NEW_RPATH "/usr/local/lib")
      if(CMAKE_INSTALL_DO_STRIP)
        execute_process(COMMAND "/usr/bin/strip" "${file}")
      endif()
    endif()
  endforeach()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit-full" OR NOT CMAKE_INSTALL_COMPONENT)
  foreach(file
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1.9.5"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1"
      )
    if(EXISTS "${file}" AND
       NOT IS_SYMLINK "${file}")
      file(RPATH_CHECK
           FILE "${file}"
           RPATH "/usr/local/lib")
    endif()
  endforeach()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES
    "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so.1.9.5"
    "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so.1"
    )
  foreach(file
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1.9.5"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libgeogram.so.1"
      )
    if(EXISTS "${file}" AND
       NOT IS_SYMLINK "${file}")
      file(RPATH_CHANGE
           FILE "${file}"
           OLD_RPATH "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src/build_make/lib:"
           NEW_RPATH "/usr/local/lib")
      if(CMAKE_INSTALL_DO_STRIP)
        execute_process(COMMAND "/usr/bin/strip" "${file}")
      endif()
    endif()
  endforeach()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit-full" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/lib/libgeogram.so")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/geogram1/geogram" TYPE DIRECTORY FILES "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src/src/lib/geogram/api" FILES_MATCHING REGEX "/[^/]*\\.h$")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "devkit-full" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/geogram1/geogram" TYPE DIRECTORY FILES "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-src/src/lib/geogram/." FILES_MATCHING REGEX "/[^/]*\\.h$" REGEX "/license/" EXCLUDE)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/home/younglin90/work/claude_code/AutoTessell/tessell-mesh/build_make/_deps/geogram-build/geogram1.pc")
endif()

