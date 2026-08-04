# Measurements - native-all-production-gate-066

## Build and focused verification

- Built C++ targets: native_transaction_executor, native_transaction_intent, native_quality_witness, native_wall_edge_metric_corridor, native_artifact_fingerprint, native_atomic_publish, native_tet_bl_writer, and native_surface_bl_strip_writer.
- Combined 066/065/062/063/064 regression and actual-writer smoke command completed with **44 passed in 5.43 s**.
- New callback boundary: 3 C++ callback tests passed; Python transport adapter has 4 passed tests; actual C++ Tet/surface callback binding has 2 safe-refusal tests.
- Existing actual-writer smoke: 2 Tet writer tests and 1 surface artifact staging test passed after explicitly building native_artifact_fingerprint.

## Evidence and refusal measurements

- Callback commit sequence observed: staging -> candidate_validated -> published; writer callback and reread callback were each called once.
- Writer callback exception returned transaction_state=rolled_back, candidate_discarded=true, and rollback_reason=executor_writer_callback_exception.
- Actual surface C++ writer result lacked writer-issued output UID; AQTE returned executor_provenance_or_uid_lost before reread/publish.
- Actual Tet C++ writer result lacked the complete family quality witness; AQTE returned executor_candidate_receipt_missing before reread/publish.
- Existing surface staging initially failed because native_artifact_fingerprint was not built in the current build directory; building that declared target resolved the setup failure, and the smoke test passed.
- native_tet_bl_writer_bind.cpp emitted two pre-existing signedness warnings at source-face loops. They are recorded as an existing writer cleanup item, not hidden as an AQTE success.

No actual product-quality distribution, cell/face target accuracy, or release claim is made. The actual writer paths are still private/default-off and fail closed until they emit the complete AQTE artifact contract.
