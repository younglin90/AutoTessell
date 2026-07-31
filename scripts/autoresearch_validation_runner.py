"""Bounded parallel manifest validation with durable JSON evidence."""
from __future__ import annotations

import argparse, asyncio, hashlib, json, os, signal, time
from pathlib import Path

def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

async def run(item: dict[str, object]) -> dict[str, object]:
    command = item.get("command")
    timeout = item.get("timeout_seconds")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command) or not isinstance(timeout, (int,float)) or timeout <= 0:
        return {"name": item.get("name"), "status":"UNVERIFIED", "error":"invalid manifest item"}
    started=time.time(); proc=None
    try:
        proc=await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
        out,err=await asyncio.wait_for(proc.communicate(), timeout)
        status="PASS" if proc.returncode==0 else "ERROR"
        return {"name":item.get("name"),"command":command,"started":started,"finished":time.time(),"elapsed_seconds":time.time()-started,"exit_code":proc.returncode,"status":status,"stdout_sha256":digest(out),"stderr_sha256":digest(err)}
    except asyncio.TimeoutError:
        if proc: os.killpg(proc.pid, signal.SIGTERM); await proc.wait()
        return {"name":item.get("name"),"started":started,"finished":time.time(),"elapsed_seconds":time.time()-started,"status":"TIMEOUT"}
    except Exception as exc:
        return {"name":item.get("name"),"started":started,"finished":time.time(),"elapsed_seconds":time.time()-started,"status":"ERROR","error":str(exc)}

async def main(manifest: dict[str, object]) -> dict[str, object]:
    jobs=manifest.get("jobs")
    if not isinstance(jobs,list): return {"status":"UNVERIFIED","error":"jobs must be list","results":[]}
    sem=asyncio.Semaphore(int(manifest.get("concurrency",2)))
    async def guarded(job):
        async with sem: return await run(job if isinstance(job,dict) else {})
    results=await asyncio.gather(*(guarded(job) for job in jobs))
    return {"status":"PASS" if results and all(x["status"]=="PASS" for x in results) else "UNVERIFIED","results":results}

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("manifest",type=Path); p.add_argument("--evidence",type=Path,required=True); a=p.parse_args()
    try: manifest=json.loads(a.manifest.read_text(encoding="utf-8"))
    except Exception as e: manifest={"jobs":None,"error":str(e)}
    result=asyncio.run(main(manifest)); a.evidence.write_text(json.dumps(result,sort_keys=True),encoding="utf-8"); raise SystemExit(0 if result["status"]=="PASS" else 1)
