"""L0 Chen p.2035 S/Z compatibility-ledger tests."""

import pytest

from core.generator.native_tet.chen_sz_choice_l0 import eligible_sz_types_l0


@pytest.mark.parametrize(
    ("neighbour_exists", "neighbour_decomposed", "neighbour_type"),
    ((False, False, None), (True, False, None)),
)  # type: ignore[untyped-decorator]
def test_no_decomposed_neighbour_leaves_both_types_eligible(
    neighbour_exists: bool, neighbour_decomposed: bool, neighbour_type: str | None
) -> None:
    result = eligible_sz_types_l0(
        neighbour_exists=neighbour_exists,
        neighbour_decomposed=neighbour_decomposed,
        neighbour_type=neighbour_type,  # type: ignore[arg-type]
    )

    assert result.accepted, result.reason
    assert result.eligible_types == {"S", "Z"}
    assert not result.forced_by_neighbour
    assert not result.production_mesh_changed


@pytest.mark.parametrize(("neighbour_type", "expected"), (("S", "Z"), ("Z", "S")))  # type: ignore[untyped-decorator]
def test_decomposed_neighbour_forces_the_opposite_type(neighbour_type: str, expected: str) -> None:
    result = eligible_sz_types_l0(
        neighbour_exists=True,
        neighbour_decomposed=True,
        neighbour_type=neighbour_type,  # type: ignore[arg-type]
    )

    assert result.accepted, result.reason
    assert result.eligible_types == {expected}
    assert result.forced_by_neighbour


def test_incoherent_neighbour_state_rejects_before_a_type_is_exposed() -> None:
    result = eligible_sz_types_l0(
        neighbour_exists=True,
        neighbour_decomposed=True,
        neighbour_type=None,
    )

    assert not result.accepted
    assert result.reason == "missing_decomposed_neighbour_type"
    assert not result.eligible_types
