#!/usr/bin/env bash
# Build tessell-mesh C++ extension and install .so into backend/mesh/
# Usage: ./build.sh [--debug] [--no-tests]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
BUILD_TYPE="Release"
BUILD_TESTS="OFF"

for arg in "$@"; do
    case $arg in
        --debug)   BUILD_TYPE="Debug" ;;
        --tests)   BUILD_TESTS="ON" ;;
    esac
done

echo "=== tessell-mesh build ($BUILD_TYPE) ==="
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake "$SCRIPT_DIR" \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DTESSELL_BUILD_PYTHON=ON \
    -DTESSELL_BUILD_TESTS="$BUILD_TESTS" \
    -G "Ninja" \
    "$@"

cmake --build . --parallel "$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)"

echo ""
echo "=== Build complete ==="
echo "Extension: $(ls "$SCRIPT_DIR/../backend/mesh/tessell_mesh*.so" 2>/dev/null || echo '(not found)')"
