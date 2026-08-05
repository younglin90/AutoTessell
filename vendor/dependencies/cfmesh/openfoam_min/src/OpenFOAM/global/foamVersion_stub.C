// SPDX-License-Identifier: GPL-3.0-or-later
// Author: AutoTessell project (this stub file is original work).
//
// foamVersion runtime stub for in-tree vendored cfMesh + OpenFOAM build.
// OpenFOAM's wmake normally generates these symbols at build time from the
// version-control state. CMake-driven vendor build replaces that with this
// minimal stub — sufficient for cfMesh exes which only print/log the values.

#include "foamVersion.H"

#include <string>
#include <iostream>

namespace Foam
{
namespace foamVersion
{

const int api = 2406;
const std::string patch = "0";
const std::string build = "vendored";
const std::string buildArch = "linux64Gcc";
const std::string version = "v2406-vendored";

unsigned labelByteSize(const std::string& /*str*/)
{
    return sizeof(int);
}

unsigned scalarByteSize(const std::string& /*str*/)
{
    return sizeof(double);
}

bool patched()
{
    return false;
}

void printBuildInfo(std::ostream& os, bool /*full*/)
{
    os << "Build  : " << version << " (vendored)\n"
       << "Arch   : " << buildArch << "\n"
       << "API    : " << api << std::endl;
}

} // namespace foamVersion
} // namespace Foam
