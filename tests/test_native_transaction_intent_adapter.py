from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.evaluator.native_transaction_intent import (  # noqa: E402
    authorize_native_transaction,
    validate_transaction_intent_receipt,
)
from test_native_transaction_intent_v1_cpp23 import (  # noqa: E402
    _authority,
    _corridor,
    _manifest,
    _quality,
    _request,
)


def test_python_adapter_passes_lossless_request_to_native_and_only_checks_shape() -> None:
    receipt = authorize_native_transaction(_authority(), _request(1), _manifest(), _quality(1), _corridor(1))
    assert receipt["accepted"] is True, receipt
    assert validate_transaction_intent_receipt(receipt) == {"accepted": True, "reasons": []}


def test_python_adapter_does_not_promote_refused_receipt() -> None:
    receipt = authorize_native_transaction(_authority(), _request(1), _manifest(), _quality(1), None)
    assert receipt["accepted"] is False
    assert validate_transaction_intent_receipt(receipt)["accepted"] is False
