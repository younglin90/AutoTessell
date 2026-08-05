// SPDX-License-Identifier: GPL-3.0-or-later
// Author: AutoTessell project (this stub file is original work).
//
// Stub for Foam::expressions::fieldExpr::parser.
// Upstream OpenFOAM generates the Lemon parser from fieldExprLemonParser.lyy-m4
// at build time via wmake's m4+lemon pipeline. The CMake-driven vendor build
// does not run that pipeline. cfMesh executables never invoke field
// expressions at runtime, so empty stubs that allow linking are sufficient.

#include "fieldExprParser.H"
#include "Ostream.H"

namespace Foam
{
namespace expressions
{
namespace fieldExpr
{

word parser::tokenName(int /*tokenId*/)
{
    return word("token");
}

void parser::printTokenNames(Ostream& /*os*/) {}
void parser::printRules(Ostream& /*os*/) {}

void parser::start(parseDriver& /*driver_*/) {}
void parser::stop() {}

void parser::parse(int /*tokenId*/) {}
void parser::parse(int /*tokenId*/, scanToken /*tok*/) {}

} // namespace fieldExpr
} // namespace expressions
} // namespace Foam
