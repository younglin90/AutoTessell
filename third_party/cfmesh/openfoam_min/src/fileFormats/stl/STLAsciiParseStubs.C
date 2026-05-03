// SPDX-License-Identifier: GPL-3.0-or-later
// Author: AutoTessell project (this stub file is original work).
//
// Stub for STLReader::readAsciiFlex and readAsciiRagel.
// Upstream OpenFOAM generates these from .L/.rl sources via flex/ragel at
// build time. CMake-driven vendor build does not run flex/ragel; we route
// both to the always-present manual parser (readAsciiManual) instead.

#include "STLReader.H"

namespace Foam
{
namespace fileFormats
{

bool STLReader::readAsciiFlex(const fileName& filename)
{
    return readAsciiManual(filename);
}

bool STLReader::readAsciiRagel(const fileName& filename)
{
    return readAsciiManual(filename);
}

} // namespace fileFormats
} // namespace Foam
