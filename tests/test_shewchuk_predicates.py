"""Tests for the bundled Shewchuk C predicates.

Covers:
- Basic orient3d / insphere correctness.
- Degenerate cases: coplanar, cospherical.
- Near-degenerate cases where float64 is unreliable.
- Sign parity with Fraction-based exact predicates.

All tests skip gracefully if the .so could not be compiled on this platform
(e.g., no C compiler), preserving the "silent fallback" contract.
"""
from __future__ import annotations

import math
import pytest
from fractions import Fraction

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _frac_orient3d(a, b, c, d) -> int:
    """Exact orient3d via Fraction."""
    from core.utils.predicates_exact import orient3d as _exact
    return _exact(a, b, c, d)


def _frac_insphere(a, b, c, d, e) -> int:
    """Exact insphere via Fraction."""
    from core.utils.predicates_exact import insphere as _exact
    return _exact(a, b, c, d, e)


@pytest.fixture(scope="module")
def shewchuk():
    """Return the _shewchuk module.  Skip if C predicates unavailable."""
    try:
        import core.utils._shewchuk as sw
    except ImportError:
        pytest.skip("_shewchuk module not importable")
    if not sw.is_available():
        pytest.skip("Shewchuk .so not compiled / loaded on this platform")
    return sw


# ---------------------------------------------------------------------------
# orient3d tests
# ---------------------------------------------------------------------------

class TestOrient3d:
    """orient3d — 13 cases."""

    def test_positive_orientation(self, shewchuk):
        """Standard positive tet: d above plane abc."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.0, 0.0, 1.0)
        assert shewchuk.orient3d(a, b, c, d) == 1

    def test_negative_orientation(self, shewchuk):
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.0, 0.0, -1.0)
        assert shewchuk.orient3d(a, b, c, d) == -1

    def test_coplanar_zero(self, shewchuk):
        """Exactly coplanar — z=0 plane."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (1.0, 1.0, 0.0)
        assert shewchuk.orient3d(a, b, c, d) == 0

    def test_near_coplanar_positive(self, shewchuk):
        """d is epsilon above the plane — should be +1, not 0."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        # z = 1e-15 is below float64 noise threshold but exact answer is +1
        d = (0.5, 0.5, 1e-15)
        result = shewchuk.orient3d(a, b, c, d)
        frac_result = _frac_orient3d(a, b, c, d)
        assert result == frac_result

    def test_near_coplanar_negative(self, shewchuk):
        """d is epsilon below the plane."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.5, 0.5, -1e-15)
        result = shewchuk.orient3d(a, b, c, d)
        frac_result = _frac_orient3d(a, b, c, d)
        assert result == frac_result

    def test_tiny_positive(self, shewchuk):
        """Very thin tet — z=1e-18."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.5, 0.5, 1e-18)
        result = shewchuk.orient3d(a, b, c, d)
        frac_result = _frac_orient3d(a, b, c, d)
        assert result == frac_result

    def test_large_coords(self, shewchuk):
        """Large coordinates — no overflow."""
        a = (1e8, 0.0, 0.0)
        b = (1e8 + 1.0, 0.0, 0.0)
        c = (1e8, 1.0, 0.0)
        d = (1e8, 0.0, 1.0)
        assert shewchuk.orient3d(a, b, c, d) == 1

    def test_sign_parity_random_1(self, shewchuk):
        a = (0.1, 0.2, 0.3)
        b = (1.1, 0.5, 0.1)
        c = (0.3, 1.2, 0.4)
        d = (0.6, 0.7, 0.9)
        assert shewchuk.orient3d(a, b, c, d) == _frac_orient3d(a, b, c, d)

    def test_sign_parity_random_2(self, shewchuk):
        a = (-1.0, -2.0, 3.0)
        b = (4.0, -1.0, 2.0)
        c = (1.0, 3.0, -1.0)
        d = (0.0, 0.0, 0.0)
        assert shewchuk.orient3d(a, b, c, d) == _frac_orient3d(a, b, c, d)

    def test_permuted_vertices_sign_flip(self, shewchuk):
        """Swapping b↔c should flip sign."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.0, 0.0, 1.0)
        s1 = shewchuk.orient3d(a, b, c, d)
        s2 = shewchuk.orient3d(a, c, b, d)
        assert s1 == -s2

    def test_repeated_vertex(self, shewchuk):
        """Degenerate: two identical vertices — must agree with Fraction exact."""
        a = (1.0, 2.0, 3.0)
        b = (1.0, 2.0, 3.0)  # same as a
        c = (0.0, 1.0, 0.0)
        d = (0.0, 0.0, 1.0)
        # Both exact and Shewchuk should return 0 (degenerate),
        # but floating-point determinant computation may not be exactly zero.
        # We only require sign parity with the Fraction result.
        frac_result = _frac_orient3d(a, b, c, d)
        result = shewchuk.orient3d(a, b, c, d)
        assert result == frac_result

    def test_float128_borderline(self, shewchuk):
        """Case where stage1 bound is close — adaptive must resolve."""
        eps = 2.0 ** -52  # machine epsilon
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.33333333333333331, 0.33333333333333331, eps)
        result = shewchuk.orient3d(a, b, c, d)
        frac_result = _frac_orient3d(a, b, c, d)
        assert result == frac_result


# ---------------------------------------------------------------------------
# insphere tests
# ---------------------------------------------------------------------------

class TestInsphere:
    """insphere — 11 cases."""

    def _pos_tet(self):
        """Return a positively-oriented tet for circumsphere tests."""
        return (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )

    def test_inside(self, shewchuk):
        """Centroid of tet is inside circumsphere."""
        a, b, c, d = self._pos_tet()
        e = (0.25, 0.25, 0.25)  # centroid — clearly inside
        assert shewchuk.insphere(a, b, c, d, e) == 1

    def test_outside(self, shewchuk):
        """Far point is outside circumsphere."""
        a, b, c, d = self._pos_tet()
        e = (10.0, 10.0, 10.0)
        assert shewchuk.insphere(a, b, c, d, e) == -1

    def test_on_sphere_vertex(self, shewchuk):
        """One of the defining vertices is exactly on the sphere (0)."""
        a, b, c, d = self._pos_tet()
        # a itself is on the circumsphere → result should be 0
        assert shewchuk.insphere(a, b, c, d, a) == 0

    def test_sign_parity_inside(self, shewchuk):
        a = (0.0, 0.0, 0.0)
        b = (2.0, 0.0, 0.0)
        c = (0.0, 2.0, 0.0)
        d = (0.0, 0.0, 2.0)
        e = (0.5, 0.5, 0.5)
        assert shewchuk.insphere(a, b, c, d, e) == _frac_insphere(a, b, c, d, e)

    def test_sign_parity_outside(self, shewchuk):
        a = (0.0, 0.0, 0.0)
        b = (2.0, 0.0, 0.0)
        c = (0.0, 2.0, 0.0)
        d = (0.0, 0.0, 2.0)
        e = (3.0, 3.0, 3.0)
        assert shewchuk.insphere(a, b, c, d, e) == _frac_insphere(a, b, c, d, e)

    def test_near_cospherical(self, shewchuk):
        """Point nearly on the sphere — must agree with Fraction."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.0, 0.0, 1.0)
        # circumradius^2 for this tet's circumsphere:
        # center ≈ (0.5, 0.5, 0.5), circumradius = sqrt(0.75)
        # point slightly inside
        r = math.sqrt(0.75) - 1e-14
        e = (0.5 + r / math.sqrt(3), 0.5, 0.5)
        result = shewchuk.insphere(a, b, c, d, e)
        frac_result = _frac_insphere(a, b, c, d, e)
        assert result == frac_result

    def test_unit_sphere_tet(self, shewchuk):
        """Tet inscribed in unit sphere — must agree with Fraction exact.

        Note: the geometric tet may have negative orientation, so the insphere
        result depends on orientation convention.  We only check sign parity
        with the Fraction-based exact predicate.
        """
        sq2 = math.sqrt(2.0 / 3.0)
        a = (0.0, 0.0, 1.0)
        b = (2 * sq2 * math.cos(0.0), 2 * sq2 * math.sin(0.0), -1.0 / 3.0)
        c = (2 * sq2 * math.cos(2 * math.pi / 3), 2 * sq2 * math.sin(2 * math.pi / 3), -1.0 / 3.0)
        d = (2 * sq2 * math.cos(4 * math.pi / 3), 2 * sq2 * math.sin(4 * math.pi / 3), -1.0 / 3.0)
        e = (0.0, 0.0, 0.0)  # origin
        frac_result = _frac_insphere(a, b, c, d, e)
        assert shewchuk.insphere(a, b, c, d, e) == frac_result

    def test_sign_parity_random(self, shewchuk):
        a = (0.1, 0.2, 0.3)
        b = (1.1, 0.0, 0.0)
        c = (0.0, 1.1, 0.0)
        d = (0.0, 0.0, 1.1)
        e = (0.4, 0.4, 0.4)
        assert shewchuk.insphere(a, b, c, d, e) == _frac_insphere(a, b, c, d, e)

    def test_degenerate_flat_tet(self, shewchuk):
        """Flat (coplanar) tet — insphere should return 0 for any query."""
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (1.0, 1.0, 0.0)  # coplanar!
        e = (0.5, 0.5, 0.0)
        # Fraction result
        frac_result = _frac_insphere(a, b, c, d, e)
        assert shewchuk.insphere(a, b, c, d, e) == frac_result

    def test_large_coords_insphere(self, shewchuk):
        """Large coords — should not overflow."""
        s = 1e6
        a = (0.0, 0.0, 0.0)
        b = (s, 0.0, 0.0)
        c = (0.0, s, 0.0)
        d = (0.0, 0.0, s)
        e = (s * 0.25, s * 0.25, s * 0.25)
        assert shewchuk.insphere(a, b, c, d, e) == 1


# ---------------------------------------------------------------------------
# Integration test: predicates_staged uses Shewchuk C (not Fraction) for Stage 3
# ---------------------------------------------------------------------------

class TestStagedIntegration:
    """Verify predicates_staged picks up the bundled C library."""

    def test_has_shewchuk(self, shewchuk):
        """predicates_staged.has_shewchuk_predicates() should be True."""
        from core.utils.predicates_staged import has_shewchuk_predicates
        assert has_shewchuk_predicates() is True

    def test_staged_thin_tet_positive(self, shewchuk):
        """Thin tet that stage1 can't resolve — staged returns Shewchuk result."""
        from core.utils.predicates_staged import orient3d_staged
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.5, 0.5, 1e-18)
        assert orient3d_staged(a, b, c, d) == 1

    def test_staged_thin_tet_negative(self, shewchuk):
        from core.utils.predicates_staged import orient3d_staged
        a = (0.0, 0.0, 0.0)
        b = (1.0, 0.0, 0.0)
        c = (0.0, 1.0, 0.0)
        d = (0.5, 0.5, -1e-18)
        assert orient3d_staged(a, b, c, d) == -1
