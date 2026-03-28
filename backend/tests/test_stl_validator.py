"""Unit tests for STL validator."""

import struct
import pytest

from mesh.validator import STLValidationError, validate_stl


def _make_binary_stl(num_triangles: int) -> bytes:
    """Build a minimal valid binary STL."""
    header = b"\x00" * 80
    count = struct.pack("<I", num_triangles)
    # Each triangle: 12 floats (normal + 3 vertices) + 2 byte attribute
    triangle = struct.pack("<12f", *([0.0] * 12)) + b"\x00\x00"
    return header + count + (triangle * num_triangles)


def _make_ascii_stl(num_facets: int = 1) -> bytes:
    facets = ""
    for _ in range(num_facets):
        facets += (
            "  facet normal 0 0 1\n"
            "    outer loop\n"
            "      vertex 0 0 0\n"
            "      vertex 1 0 0\n"
            "      vertex 0 1 0\n"
            "    endloop\n"
            "  endfacet\n"
        )
    text = f"solid test\n{facets}endsolid test\n"
    return text.encode("ascii")


# ---- Binary STL ----

class TestBinarySTL:
    def test_valid(self):
        validate_stl(_make_binary_stl(10))  # should not raise

    def test_zero_triangles(self):
        with pytest.raises(STLValidationError, match="zero triangles"):
            validate_stl(_make_binary_stl(0))

    def test_truncated(self):
        content = _make_binary_stl(10)[:-20]  # cut off last 20 bytes
        with pytest.raises(STLValidationError, match="size mismatch"):
            validate_stl(content)

    def test_too_large(self, monkeypatch):
        import mesh.validator as v
        monkeypatch.setattr(v, "MAX_STL_SIZE", 100)
        with pytest.raises(STLValidationError, match="too large"):
            validate_stl(_make_binary_stl(10))

    def test_too_short(self):
        with pytest.raises(STLValidationError):
            validate_stl(b"\x00" * 10)


# ---- ASCII STL ----

class TestASCIISTL:
    def test_valid(self):
        validate_stl(_make_ascii_stl(3))  # should not raise

    def test_no_facets(self):
        content = b"solid test\nendsolid test\n"
        with pytest.raises(STLValidationError, match="no facets"):
            validate_stl(content)

    def test_missing_endsolid(self):
        content = b"solid test\n  facet normal 0 0 1\n    outer loop\n"
        with pytest.raises(STLValidationError, match="endsolid"):
            validate_stl(content)
