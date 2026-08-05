#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <tessell/mesh2d.hpp>
#include <cmath>

using namespace tessell;

// ──────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────

static std::vector<Vec2> unit_square() {
    return {{0,0},{1,0},{1,1},{0,1}};
}

static std::vector<Vec2> triangle_poly() {
    return {{0,0},{1,0},{0.5,1}};
}

// Check that all triangle vertices reference valid vertex indices
static bool triangles_valid(const Mesh2D& m) {
    int nv = (int)m.vertices.size();
    for (auto& t : m.triangles) {
        if (t[0] < 0 || t[0] >= nv) return false;
        if (t[1] < 0 || t[1] >= nv) return false;
        if (t[2] < 0 || t[2] >= nv) return false;
    }
    return true;
}

// Signed area of 2-D triangle (positive = CCW)
static double signed_area(const Vec2& a, const Vec2& b, const Vec2& c) {
    return 0.5 * ((b[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(b[1]-a[1]));
}

static double total_area(const Mesh2D& m) {
    double area = 0;
    for (auto& t : m.triangles) {
        area += std::abs(signed_area(m.vertices[t[0]],
                                      m.vertices[t[1]],
                                      m.vertices[t[2]]));
    }
    return area;
}

// ──────────────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────────────

TEST_CASE("2D triangulation: unit square has correct total area") {
    auto mesh = triangulate_2d(unit_square());
    CHECK(mesh.triangles.size() > 0);
    CHECK(triangles_valid(mesh));
    // Total triangle area should equal 1.0 (unit square)
    CHECK(total_area(mesh) == doctest::Approx(1.0).epsilon(1e-6));
}

TEST_CASE("2D triangulation: triangle polygon") {
    auto mesh = triangulate_2d(triangle_poly());
    CHECK(mesh.triangles.size() > 0);
    CHECK(triangles_valid(mesh));
    // Area = 0.5 * base * height = 0.5 * 1 * 1 = 0.5
    CHECK(total_area(mesh) == doctest::Approx(0.5).epsilon(1e-6));
}

TEST_CASE("2D triangulation: square with square hole") {
    // Outer square 0–4
    std::vector<Vec2> outer = {{0,0},{4,0},{4,4},{0,4}};
    // Inner hole 1–3
    std::vector<Vec2> hole  = {{1,1},{3,1},{3,3},{1,3}};
    auto mesh = triangulate_2d(outer, {hole});
    CHECK(mesh.triangles.size() > 0);
    CHECK(triangles_valid(mesh));
    // Area = 16 - 4 = 12
    CHECK(total_area(mesh) == doctest::Approx(12.0).epsilon(1e-5));
}

TEST_CASE("2D triangulation: boundary produces at least 2 triangles for square") {
    auto mesh = triangulate_2d(unit_square());
    // A square needs at least 2 triangles
    CHECK(mesh.triangles.size() >= 2);
}

TEST_CASE("2D triangulation: throws on degenerate input") {
    CHECK_THROWS_AS(
        triangulate_2d({{0,0},{1,0}}),  // only 2 vertices
        std::invalid_argument
    );
}

TEST_CASE("2D triangulation: large polygon") {
    // Regular 16-gon
    std::vector<Vec2> poly;
    const int N = 16;
    for (int i = 0; i < N; ++i) {
        double a = 2.0 * M_PI * i / N;
        poly.push_back({std::cos(a), std::sin(a)});
    }
    auto mesh = triangulate_2d(poly);
    CHECK(mesh.triangles.size() > 0);
    CHECK(triangles_valid(mesh));
    // Area of unit circle ≈ π; regular 16-gon ≈ 3.061
    CHECK(total_area(mesh) > 3.0);
    CHECK(total_area(mesh) < M_PI);
}
