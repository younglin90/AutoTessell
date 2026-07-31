import asyncio
from scripts.autoresearch_validation_runner import main

def test_manifest_statuses():
    result=asyncio.run(main({"concurrency":2,"jobs":[
        {"name":"ok","command":["/bin/true"],"timeout_seconds":1},
        {"name":"bad","command":["/bin/false"],"timeout_seconds":1},
        {"name":"invalid"},
    ]}))
    assert result["status"] == "UNVERIFIED"
    assert [x["status"] for x in result["results"]] == ["PASS","ERROR","UNVERIFIED"]
