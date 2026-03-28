"""Unit tests for CORS origin list parsing (main.py)."""


def _parse_cors_origins(cors_origins: str) -> list[str]:
    """Replicate the one-liner used in main.py."""
    return [o for o in (o.strip() for o in cors_origins.split(",")) if o]


def test_single_origin():
    assert _parse_cors_origins("http://localhost:3000") == ["http://localhost:3000"]


def test_multiple_origins():
    result = _parse_cors_origins("http://localhost:3000,https://app.tessell.io")
    assert result == ["http://localhost:3000", "https://app.tessell.io"]


def test_trailing_comma_no_empty_entry():
    """Trailing comma must not produce an empty string in the list."""
    result = _parse_cors_origins("http://localhost:3000,")
    assert "" not in result
    assert result == ["http://localhost:3000"]


def test_leading_comma_no_empty_entry():
    result = _parse_cors_origins(",http://localhost:3000")
    assert "" not in result
    assert result == ["http://localhost:3000"]


def test_whitespace_around_comma_stripped():
    result = _parse_cors_origins("http://localhost:3000 , https://app.tessell.io")
    assert result == ["http://localhost:3000", "https://app.tessell.io"]


def test_empty_string_produces_empty_list():
    """Empty cors_origins must not add an empty-string allow-origin."""
    assert _parse_cors_origins("") == []


def test_only_commas_produces_empty_list():
    assert _parse_cors_origins(",,,") == []
