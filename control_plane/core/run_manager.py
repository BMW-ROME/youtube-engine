"""Durable single-writer run state for Control Plane v0.1.

recover() returns a validated next-stage hint, not a resumed media pipeline.
The YouTube adapter still delegates to the complete production pipeline.
"""

from __future__ import annotations
import hashlib, json, os, re, secrets, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .state_machine import STAGES, require_transition, next_stage

def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

class RunManager:
    def __init__(self, root: str | Path):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)

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

    def checkpoint(self, run_id: str, stage: str, artifacts: list[str]):
        d=self._dir(run_id); s=self.status(run_id)
        if s["lifecycle"] != "RUNNING" or stage not in STAGES:
            raise ValueError("checkpoint requires a RUNNING run and a known stage")
        if not isinstance(artifacts, list) or not artifacts or not all(isinstance(x, str) for x in artifacts):
            raise ValueError("checkpoint requires artifact paths")
        if len(set(artifacts)) != len(artifacts):
            raise ValueError("checkpoint requires distinct artifact paths")
        previous=self.latest_checkpoint(run_id)
        if previous and STAGES.index(stage) <= STAGES.index(previous["stage"]):
            raise ValueError("checkpoint stages must advance; preserve completed evidence")
        digests={rel:self._digest(self._contained_file(d, rel)) for rel in artifacts}
        cid=f"{stage}-{s['attempt']}"
        cp={"schema_version":"1.0","checkpoint_id":cid,"run_id":run_id,"stage":stage,"attempt":s["attempt"],"created_at":utcnow(),"verified":True,"resume_from":next_stage(stage),"artifacts":artifacts,"artifact_sha256":digests}
        path=self._contained_path(d, f"checkpoints/{cid}.json"); self._write_json(path,cp)
        self.event(run_id,"checkpoint_created",stage,{"checkpoint_id":cid,"artifacts":artifacts})
        s.update(stage=stage,last_checkpoint=str(path.relative_to(d)),resumable=cp["resume_from"] is not None,updated_at=utcnow()); self._write_status(d,s)

    def interrupt(self, run_id: str):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"INTERRUPTED")
        s.update(lifecycle="INTERRUPTED",execution="INTERRUPTED",updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"run_interrupted",s["stage"],{})

    def recover(self, run_id: str):
        d=self._dir(run_id); s=self.status(run_id)
        if s["lifecycle"] != "RECOVERY_REQUIRED":
            require_transition(s["lifecycle"],"RECOVERY_REQUIRED")
        s.update(lifecycle="RECOVERY_REQUIRED",execution="INTERRUPTED",updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"recovery_started",s["stage"],{})
        try:
            cp=self.latest_checkpoint(run_id)
            self._validate_checkpoint(d,s,cp)
        except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
            s.update(resumable=False,error_class="CheckpointValidationError",error_message=str(exc),updated_at=utcnow())
            self._write_status(d,s)
            raise RuntimeError(f"checkpoint validation failed: {exc}") from exc
        require_transition("RECOVERY_REQUIRED","RUNNING")
        s.update(lifecycle="RUNNING",execution="RUNNING",attempt=s["attempt"]+1,stage=cp["resume_from"] or cp["stage"],resumable=cp["resume_from"] is not None,error_class=None,error_message=None,updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"recovery_completed",s["stage"],{"resume_from":cp["resume_from"]})
        return cp["resume_from"]

    def succeed(self, run_id: str, outputs=None):
        d=self._dir(run_id); s=self.status(run_id); require_transition(s["lifecycle"],"SUCCEEDED")
        completed=[]
        for line in (d/"events.jsonl").read_text(encoding="utf-8").splitlines():
            event=json.loads(line)
            if event["event"] == "checkpoint_created" and event["stage"] not in completed:
                completed.append(event["stage"])
        self._write_json(d/"results.json",{"schema_version":"1.0","run_id":run_id,"success":True,"completed_stages":completed,"failed_stages":[],"outputs":outputs or {}})
        s.update(lifecycle="SUCCEEDED",execution="COMPLETE",resumable=False,updated_at=utcnow()); self._write_status(d,s)
        self.event(run_id,"run_succeeded",s["stage"],{})

    def event(self,run_id,event,stage,data):
        p=self._dir(run_id)/"events.jsonl"
        with p.open(encoding="utf-8") as f: seq=sum(1 for _ in f)+1
        rec={"schema_version":"1.0","event_id":secrets.token_hex(8),"run_id":run_id,"sequence":seq,"timestamp":utcnow(),"event":event,"stage":stage,"attempt":self.status(run_id)["attempt"],"data":data}
        with p.open("a",encoding="utf-8") as f:
            f.write(json.dumps(rec,separators=(",",":"))+"\n")
            f.flush(); os.fsync(f.fileno())

    def latest_checkpoint(self,run_id):
        d=self._dir(run_id); rel=self.status(run_id)["last_checkpoint"]
        if rel is None: return None
        if not isinstance(rel,str) or Path(rel).parent != Path("checkpoints"):
            raise ValueError("invalid checkpoint pointer")
        return json.loads(self._contained_file(d,rel).read_text(encoding="utf-8"))

    def _validate_checkpoint(self,d,s,cp):
        if not isinstance(cp,dict) or cp.get("verified") is not True:
            raise ValueError("no verified checkpoint")
        stage=cp.get("stage"); attempt=cp.get("attempt")
        if cp.get("schema_version") != "1.0" or cp.get("run_id") != d.name or s["run_id"] != d.name:
            raise ValueError("checkpoint identity mismatch")
        if stage not in STAGES or type(attempt) is not int or not 1 <= attempt <= s["attempt"]:
            raise ValueError("invalid checkpoint stage or attempt")
        cid=f"{stage}-{attempt}"
        if cp.get("checkpoint_id") != cid or s["last_checkpoint"] != f"checkpoints/{cid}.json":
            raise ValueError("checkpoint pointer mismatch")
        if cp.get("resume_from") != next_stage(stage):
            raise ValueError("invalid checkpoint successor")
        artifacts=cp.get("artifacts"); digests=cp.get("artifact_sha256")
        if not isinstance(artifacts,list) or not artifacts or not all(isinstance(x,str) for x in artifacts):
            raise ValueError("invalid checkpoint artifacts")
        if not isinstance(digests,dict) or set(digests) != set(artifacts):
            raise ValueError("missing integrity evidence; legacy checkpoints must be reverified")
        for rel in artifacts:
            expected=digests[rel]
            if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected):
                raise ValueError("invalid artifact digest")
            if self._digest(self._contained_file(d,rel)) != expected:
                raise ValueError(f"checkpoint artifact changed: {rel}")

    def _dir(self,run_id):
        if not isinstance(run_id,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{8}",run_id):
            raise ValueError("invalid run id")
        d=self._contained_path(self.root,run_id)
        if not d.is_dir(): raise FileNotFoundError(run_id)
        return d

    @staticmethod
    def _contained_path(base,rel):
        if not isinstance(rel,str) or not rel or "\\" in rel:
            raise ValueError("invalid relative path")
        relative=Path(rel)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe path reference")
        path=(base/relative).resolve()
        if not path.is_relative_to(base.resolve()) or path == base.resolve():
            raise ValueError("path escapes run directory")
        return path

    @classmethod
    def _contained_file(cls,base,rel):
        path=cls._contained_path(base,rel)
        if not path.is_file(): raise RuntimeError(f"missing checkpoint artifact file: {rel}")
        return path

    @staticmethod
    def _digest(path):
        digest=hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""): digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json(path,value):
        fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                f.write(json.dumps(value,indent=2)+"\n"); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,path)
        finally: Path(tmp).unlink(missing_ok=True)

    @classmethod
    def _write_status(cls,d,s):
        cls._write_json(d/"status.json",s)
