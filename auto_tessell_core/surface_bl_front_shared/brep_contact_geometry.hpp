#pragma once

#include <cmath>

namespace brep_contact {

struct Vec3 {
    double x;
    double y;
    double z;
};

inline Vec3 subtract(const Vec3& a, const Vec3& b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline double dot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline double norm(const Vec3& a) { return std::sqrt(dot(a, a)); }
inline bool finite(const Vec3& a) { return std::isfinite(a.x) && std::isfinite(a.y) && std::isfinite(a.z); }
inline double distance(const Vec3& a, const Vec3& b) { return norm(subtract(a, b)); }

}  // namespace brep_contact
