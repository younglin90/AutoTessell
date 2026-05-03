// SPDX-License-Identifier: GPL-3.0-or-later
// Original stub for vendored cfMesh+OpenFOAM build.
//
// Flex parser is generated from STLAsciiParseFlex.L at build time by wmake.
// CMake build does not run flex; route to readAsciiManual instead.

#include "STLReader.H"

namespace Foam {
namespace fileFormats {

bool STLReader::readAsciiFlex(const fileName& filename)
{
    return readAsciiManual(filename);
}

}}
