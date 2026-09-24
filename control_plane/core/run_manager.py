"""Durable run state for Control Plane v0.1."""
from __future__ import annotations
import json, os, secrets
from datetime import datetime, timezone
from pathlib import Path
from .state_machine import require_transition, next_stage

def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

class RunManager:
    def __init__(self, root: str | Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)

    def create(self, operation: str, inputs: dict, project="helping-others-with-my-voice", controller_version="0.1.0") -> str:
        run_id=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")+"-"+secrets.token_hex(4)
        d=self.root/run_id; (d/"artifacts").mkdir(parents=True); (d/"checkpoints").mkdir()
        (d/"manifest.json").write_text(json.dumps({"schema_version":"1.0","run_id":run_id,"project":project,"operation":operation,"created_at":utcnow(),"controller_version":controller_version,"inputs":inputs},indent=2)+"\n")
        self._write_status(d,{"schema_version":"1.0","run_id":run_id,"lifecycle":"CREATED","stage":None,"execution":"NOT_STARTED","analysis":"NOT_STARTED","last_checkpoint":None,"resumable":False,"attempt":1,"video_id":inputs.get("video_id"),"error_class":None,"error_message":None,"updated_at":utcnow()})
        (d/"events.jsonl").write_text("")
        (d/"stdout.log").write_text(""); (d/"stderr.log").write_text("")
        return run_id

    def start(self, run_id: str):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"RUNNING")
        s.update(lifecycle="RUNNING",execution="RUNNING",updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"run_started",None,{"pid":os.getpid()})

    def status(self, run_id): return json.loads((self._dir(run_id)/"status.json").read_text())

    def checkpoint(self, run_id: str, stage: str, artifacts: list[str], resume_from: str | None = None):
        d=self._dir(run_id); s=self.status(run_id)
        cid=f"{stage}-{s['attempt']}"
        cp={"schema_version":"1.0","checkpoint_id":cid,"run_id":run_id,"stage":stage,"attempt":s["attempt"],"created_at":utcnow(),"verified":True,"resume_from":resume_from if resume_from is not None else next_stage(stage),"artifacts":artifacts}
        path=d/"checkpoints"/f"{cid}.json"; path.write_text(json.dumps(cp,indent=2)+"\n")
        self.event(run_id,"checkpoint_created",stage,{"checkpoint_id":cid,"artifacts":artifacts})
        s.update(stage=stage,last_checkpoint=str(path.relative_to(d)),resumable=True,updated_at=utcnow()); self._write_status(d,s)

    def interrupt(self, run_id: str):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"INTERRUPTED")
        s.update(lifecycle="INTERRUPTED",execution="INTERRUPTED",updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"run_interrupted",s["stage"],{})

    def recover(self, run_id: str):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"RECOVERY_REQUIRED")
        s.update(lifecycle="RECOVERY_REQUIRED",updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"recovery_started",s["stage"],{})
        cp=self.latest_checkpoint(run_id)
        if not cp or not cp.get("verified"): raise RuntimeError("no verified checkpoint")
        for rel in cp["artifacts"]:
            if not (d/rel).exists(): raise RuntimeError(f"missing checkpoint artifact: {rel}")
        require_transition("RECOVERY_REQUIRED","RUNNING")
        s.update(lifecycle="RUNNING",execution="RUNNING",attempt=s["attempt"]+1,stage=cp["resume_from"],updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"recovery_completed",s["stage"],{"resume_from":cp["resume_from"]})
        return cp["resume_from"]

    def succeed(self, run_id: str, outputs=None):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"SUCCEEDED")
        s.update(lifecycle="SUCCEEDED",execution="COMPLETE",resumable=False,updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"run_succeeded",s["stage"],{})
        (d/"results.json").write_text(json.dumps({"schema_version":"1.0","run_id":run_id,"success":True,"completed_stages":[],"failed_stages":[],"outputs":outputs or {}},indent=2)+"\n")

    def event(self,run_id,event,stage,data):
        p=self._dir(run_id)/"events.jsonl"; seq=sum(1 for _ in p.open())+1
        rec={"schema_version":"1.0","event_id":secrets.token_hex(8),"run_id":run_id,"sequence":seq,"timestamp":utcnow(),"event":event,"stage":stage,"attempt":self.status(run_id)["attempt"],"data":data}
        with p.open("a") as f: f.write(json.dumps(rec,separators=(",",":"))+"\n")

    def latest_checkpoint(self,run_id):
        d=self._dir(run_id); cps=sorted((d/"checkpoints").glob("*.json"),key=lambda p:p.stat().st_mtime)
        return json.loads(cps[-1].read_text()) if cps else None

    def _dir(self,run_id):
        d=self.root/run_id
        if not d.exists(): raise FileNotFoundError(run_id)
        return d
    @staticmethod
    def _write_status(d,s):
        tmp=d/"status.json.tmp"; tmp.write_text(json.dumps(s,indent=2)+"\n"); os.replace(tmp,d/"status.json")
