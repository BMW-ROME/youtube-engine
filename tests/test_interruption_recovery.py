import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from control_plane.core.run_manager import RunManager

class InterruptionRecoveryTests(unittest.TestCase):
    def test_process_interruption_leaves_recoverable_run(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); script=root/"child.py"
            script.write_text("""from control_plane.core.run_manager import RunManager
import os, signal, sys
m=RunManager(sys.argv[1]); r=m.create('e2e_validation', {'topic':'recovery-test'})
m.start(r)
d=m.root/r/'artifacts'/'script.txt'; d.write_text('durable artifact')
m.checkpoint(r,'script',[str(d.relative_to(m.root/r))])
os.kill(os.getpid(), signal.SIGTERM)
""")
            env=os.environ.copy()
            repo_root=str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"]=repo_root + os.pathsep + env.get("PYTHONPATH","")
            p=subprocess.run(
                [sys.executable,str(script),str(root)],
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(
                p.returncode,
                0,
                msg=f"child unexpectedly succeeded; stdout={p.stdout!r} stderr={p.stderr!r}",
            )
            runs=[path for path in root.iterdir() if path.is_dir()]
            self.assertEqual(
                len(runs),
                1,
                msg=f"expected one durable run directory; entries={list(root.iterdir())!r}; stderr={p.stderr!r}",
            )
            run=runs[0]; s=json.loads((run/'status.json').read_text())
            self.assertEqual(s['lifecycle'],'RUNNING')
            m=RunManager(root); m.interrupt(run.name)
            next_stage=m.recover(run.name)
            self.assertEqual(next_stage,'voice')
            self.assertEqual(m.status(run.name)['lifecycle'],'RUNNING')

if __name__=='__main__': unittest.main()
