#!/usr/bin/env bash
# Build AutoTessell C++ extensions (cinolib_hex, robusthex)
#
# Usage:
#   ./auto_tessell_core/build_extensions.sh
#   ./auto_tessell_core/build_extensions.sh --clean
#
# Requirements:
#   - cmake >= 3.15
#   - g++ with C++17 support
#   - pybind11 (pip install pybind11)
#   - libeigen3-dev
#   - libtbb-dev
#   - Repos cloned to /tmp/hexmesh_build/:
#       - cinolib        (git clone https://github.com/mlivesu/cinolib)
#       - robust_hex_dominant_meshing (git clone ...)
#         with submodules: ext/tbb, ext/tetgen, ext/pcg32, ext/rply

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

PYBIND11_DIR="$(python3 -c 'import pybind11; print(pybind11.get_cmake_dir())')"

if [[ "$1" == "--clean" ]]; then
    echo "Cleaning build directory..."
    rm -rf "$BUILD_DIR"
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake "$SCRIPT_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -Dpybind11_DIR="$PYBIND11_DIR" \
    -Wno-dev

# Build both targets
cmake --build . --target cinolib_hex -j"$(nproc)"
echo ""
echo "cinolib_hex built: $BUILD_DIR/cinolib_hex*.so"

# robusthex requires cloned submodules — attempt but don't fail
if cmake --build . --target robusthex -j"$(nproc)" 2>/dev/null; then
    echo "robusthex built: $BUILD_DIR/robusthex*.so"
else
    echo "WARNING: robusthex build failed (optional — cinolib_hex is the primary extension)"
fi

echo ""
echo "Done. Add $BUILD_DIR to PYTHONPATH or set AUTOTESSELL_EXT_BUILD_DIR=$BUILD_DIR"
