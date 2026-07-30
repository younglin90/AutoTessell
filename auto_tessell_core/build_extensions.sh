#!/usr/bin/env bash
# Build AutoTessell C++ extensions.
#
# Usage:
#   ./auto_tessell_core/build_extensions.sh
#   ./auto_tessell_core/build_extensions.sh --clean
#   ./auto_tessell_core/build_extensions.sh --clean --native-only
#
# Requirements:
#   - cmake >= 3.20
#   - g++ with C++23 support
#   - pybind11 (pip install pybind11)
#   - libeigen3-dev
#   - libtbb-dev
#   - Repos cloned to /tmp/hexmesh_build/:
#       - cinolib        (git clone https://github.com/mlivesu/cinolib)
#       - robust_hex_dominant_meshing (git clone ...)
#         with submodules: ext/tbb, ext/tetgen, ext/pcg32, ext/rply

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
PYTHON_BIN="${PYTHON:-python3}"
CLEAN=0
NATIVE_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --native-only) NATIVE_ONLY=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

PYBIND11_DIR="$($PYTHON_BIN -c 'import pybind11; print(pybind11.get_cmake_dir())')"

if [[ "$CLEAN" == 1 ]]; then
    echo "Cleaning build directory..."
    rm -rf "$BUILD_DIR"
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake_args=(
    "$SCRIPT_DIR"
    -DCMAKE_BUILD_TYPE=Release
    -Dpybind11_DIR="$PYBIND11_DIR"
    -DPython_EXECUTABLE="$($PYTHON_BIN -c 'import sys; print(sys.executable)')"
    -Wno-dev
)

if [[ "$NATIVE_ONLY" == 1 ]]; then
    cmake_args+=(
        -DBUILD_ROBUSTHEX=OFF
        -DBUILD_FTETWILD=OFF
        -DBUILD_CFMESH=OFF
    )
fi

cmake "${cmake_args[@]}"

# Core kernels have no external mesher dependency. Keep this list explicit so a
# successful build proves every Python hot-path wrapper remains buildable.
native_targets=(
    native_metrics
    native_polymesh
    native_snap
    native_surface_padding
    native_hex_quality
    native_tet_predicates
    native_tet_qopt
)
for target in "${native_targets[@]}"; do
    cmake --build . --target "$target" -j"$(nproc)"
    echo "$target built: $BUILD_DIR/$target*.so"
done

if [[ "$NATIVE_ONLY" == 1 ]]; then
    echo "Done. Native-only extensions built in $BUILD_DIR"
    exit 0
fi

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
