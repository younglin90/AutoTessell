"""C35-0 native OCCT ABI preflight must fail closed without a shim."""

from __future__ import annotations

import sys

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

from native_brep_front_evidence_v2 import (  # noqa: E402
    occt_native_pcurve_preflight_v2,
)


def test_occt_native_pcurve_preflight_is_explicitly_unavailable_without_abi() -> None:
    result = occt_native_pcurve_preflight_v2()
    assert result["available"] is False
    assert result["status"] == "occt_native_ingress_unavailable"
    assert result["indexed_curve_on_surface"] is False
    assert result["is_stored_authoritative"] is False
    assert result["reason"] in {"occt_headers_unavailable", "occt_linkage_not_configured", "indexed_shim_not_built"}
