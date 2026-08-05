#pragma once

#include <algorithm>
#include <array>
#include <cmath>

namespace autotessell_surface_bl_quality {

using Point = std::array<double, 3>;

inline Point sub(const Point& a, const Point& b) noexcept {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

inline double dot(const Point& a, const Point& b) noexcept {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

inline double length(const Point& value) noexcept {
    return std::sqrt(dot(value, value));
}

inline double aspect(const Point& a, const Point& b, const Point& c) noexcept {
    const double ab = length(sub(b, a));
    const double bc = length(sub(c, b));
    const double ca = length(sub(a, c));
    return std::max({ab, bc, ca}) / std::max(1.0e-14, std::min({ab, bc, ca}));
}

inline double skewness(const Point& a, const Point& b, const Point& c) noexcept {
    const double q = aspect(a, b, c);
    return (q - 1.0) / q;
}

inline double non_orthogonality(const Point& a, const Point& b, const Point& c) noexcept {
    const Point ab = sub(b, a), ac = sub(c, a);
    const Point ba = sub(a, b), bc = sub(c, b);
    const Point ca = sub(a, c), cb = sub(b, c);
    const auto angle = [](const Point& x, const Point& y) {
        return std::acos(std::clamp(dot(x, y) / (length(x) * length(y)), -1.0, 1.0)) * 180.0 / std::acos(-1.0);
    };
    return std::max({std::abs(angle(ab, ac) - 60.0), std::abs(angle(ba, bc) - 60.0), std::abs(angle(ca, cb) - 60.0)});
}

struct TriangleScore {
    double skewness = 0.0;
    double aspect_ratio = 0.0;
    double non_orthogonality = 0.0;
};

inline TriangleScore score(const Point& a, const Point& b, const Point& c) noexcept {
    return {skewness(a, b, c), aspect(a, b, c), non_orthogonality(a, b, c)};
}

}  // namespace autotessell_surface_bl_quality
