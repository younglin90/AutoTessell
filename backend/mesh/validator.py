"""STL file validation — size, magic bytes, and basic structure check."""

import struct


_DEFAULT_MAX_SIZE = 100 * 1024 * 1024  # 100 MB — upload.py가 config 값을 주입하지 않을 때 방어용


class STLValidationError(ValueError):
    pass


def validate_stl(content: bytes, max_size: int = _DEFAULT_MAX_SIZE) -> None:
    """
    Raise STLValidationError if content is not a valid STL file.

    max_size: 바이트 단위 최대 허용 크기 (기본 100 MB).
              config.max_stl_size_bytes 값을 외부에서 주입하는 것을 권장.
    """
    if len(content) > max_size:
        limit_mb = max_size // (1024 * 1024)
        got_mb = len(content) // (1024 * 1024)
        raise STLValidationError(f"STL file too large (max {limit_mb} MB, got {got_mb} MB)")

    # ASCII check must come before the 84-byte size guard:
    # valid ASCII STL files can be shorter than the binary minimum.
    # If ASCII parsing fails, fall through to binary — some exporters
    # (incorrectly) start binary STL headers with "solid".
    if _is_ascii_stl(content):
        try:
            _validate_ascii_stl(content)
            return
        except STLValidationError:
            # Only fall through to binary validation if the file is large enough
            # to possibly be a binary STL — some exporters incorrectly start
            # binary headers with "solid <name>".  Short files are genuinely
            # malformed ASCII, so re-raise the original ASCII error.
            if len(content) < 84:
                raise

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
