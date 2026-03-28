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

    def test_too_large(self):
        with pytest.raises(STLValidationError, match="too large"):
            validate_stl(_make_binary_stl(10), max_size=100)

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


# ---- Binary STL with "solid" header (common exporter bug) ----

class TestBinarySTLWithSolidHeader:
    """Some exporters put "solid <name>" in the 80-byte binary header.
    The validator must not reject these as malformed ASCII files."""

    def _make_solid_header_binary_stl(self, num_triangles: int) -> bytes:
        """Binary STL whose header starts with 'solid' (as some buggy exporters produce)."""
        header_text = b"solid exported_by_buggy_exporter"
        header = header_text + b"\x00" * (80 - len(header_text))
        count = struct.pack("<I", num_triangles)
        triangle = struct.pack("<12f", *([0.0] * 12)) + b"\x00\x00"
        return header + count + (triangle * num_triangles)

    def test_valid_binary_with_solid_header_accepted(self):
        """Binary STL starting with 'solid' must not be rejected."""
        validate_stl(self._make_solid_header_binary_stl(5))

    def test_solid_header_binary_zero_triangles_rejected(self):
        """Valid structure, zero triangles → still rejected."""
        with pytest.raises(STLValidationError, match="zero triangles"):
            validate_stl(self._make_solid_header_binary_stl(0))

    def test_solid_header_binary_truncated_rejected(self):
        """Truncated binary with solid header → size mismatch."""
        content = self._make_solid_header_binary_stl(10)[:-20]
        with pytest.raises(STLValidationError, match="size mismatch"):
            validate_stl(content)


# ---- Binary STL with extra trailing bytes ----

class TestSizeLimit:
    """Tests for the max_size enforcement."""

    def test_exactly_at_max_size_accepted(self):
        """A file whose size equals max_size exactly must be accepted (> not >=)."""
        content = _make_binary_stl(5)
        validate_stl(content, max_size=len(content))  # must not raise

    def test_one_byte_over_max_size_rejected(self):
        """One byte over the limit must be rejected."""
        content = _make_binary_stl(5)
        with pytest.raises(STLValidationError, match="too large"):
            validate_stl(content, max_size=len(content) - 1)

    def test_too_large_error_mentions_max(self):
        """Error message must name the limit (helps user understand the constraint)."""
        content = _make_binary_stl(5)
        with pytest.raises(STLValidationError, match="max"):
            validate_stl(content, max_size=10)


class TestBinarySTLOversized:
    """Binary STL files that are *larger* than the declared triangle count require."""

    def test_extra_trailing_bytes_rejected(self):
        """Binary STL with extra bytes after the declared triangles → size mismatch."""
        content = _make_binary_stl(5) + b"\x00" * 50  # 50 extra bytes appended
        with pytest.raises(STLValidationError, match="size mismatch"):
            validate_stl(content)

    def test_one_extra_byte_rejected(self):
        """Even a single extra byte at the end must be caught."""
        content = _make_binary_stl(3) + b"\xff"
        with pytest.raises(STLValidationError, match="size mismatch"):
            validate_stl(content)

    def test_exact_size_accepted(self):
        """The correct-size file must still be accepted (regression guard)."""
        content = _make_binary_stl(4)
        validate_stl(content)  # must not raise
