import json, subprocess, sys, tempfile, unittest
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
            p=subprocess.run([sys.executable,str(script),str(root)],capture_output=True)
            self.assertNotEqual(p.returncode,0)
            runs=list(root.iterdir()); self.assertEqual(len(runs),1)
            run=runs[0]; s=json.loads((run/'status.json').read_text())
            self.assertEqual(s['lifecycle'],'RUNNING')
            m=RunManager(root); m.interrupt(run.name)
            next_stage=m.recover(run.name)
            self.assertEqual(next_stage,'voice')
            self.assertEqual(m.status(run.name)['lifecycle'],'RUNNING')

if __name__=='__main__': unittest.main()
