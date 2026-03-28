"""STL file validation — size, magic bytes, and basic structure check."""

import struct


MAX_STL_SIZE = 100 * 1024 * 1024  # 100 MB


class STLValidationError(ValueError):
    pass


def validate_stl(content: bytes) -> None:
    """Raise STLValidationError if content is not a valid STL file."""
    if len(content) > MAX_STL_SIZE:
        raise STLValidationError(f"STL file too large (max 100 MB, got {len(content) // 1024 // 1024} MB)")

    # ASCII check must come before the 84-byte size guard:
    # valid ASCII STL files can be shorter than the binary minimum.
    if _is_ascii_stl(content):
        _validate_ascii_stl(content)
        return

    if len(content) < 84:
        raise STLValidationError("File too small to be a valid STL")

    _validate_binary_stl(content)


def _is_ascii_stl(content: bytes) -> bool:
    try:
        start = content[:256].decode("ascii", errors="strict").strip().lower()
        return start.startswith("solid")
    except (UnicodeDecodeError, ValueError):
        return False


def _validate_ascii_stl(content: bytes) -> None:
    text = content.decode("ascii", errors="replace")
    if "facet normal" not in text:
        raise STLValidationError("ASCII STL has no facets")
    if "endsolid" not in text:
        raise STLValidationError("ASCII STL missing 'endsolid' — file may be truncated")


def _validate_binary_stl(content: bytes) -> None:
    # Binary STL: 80 byte header + 4 byte triangle count + 50 bytes * N
    if len(content) < 84:
        raise STLValidationError("Binary STL too short")
    num_triangles = struct.unpack_from("<I", content, 80)[0]
    expected_size = 84 + 50 * num_triangles
    if len(content) != expected_size:
        raise STLValidationError(
            f"Binary STL size mismatch: header says {num_triangles} triangles "
            f"(expected {expected_size} bytes), got {len(content)} bytes"
        )
    if num_triangles == 0:
        raise STLValidationError("STL has zero triangles")
