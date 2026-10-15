"""Out-of-process real G1/G2/G3 evidence; G4 sign-off remains pending."""
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET
from g2_race import Unrunnable

ROOT=Path(__file__).resolve().parents[1]
JUNIT=ROOT/'evidence/live-suite.xml'


def g1_http():
    from g1_http import execute
    execute()


def g2_race():
    from g2_race import execute
    execute()


def g3_authority():
    from g3_authority import execute
    execute()



def flow_a():
    from flow_a import execute
    execute()


def flow_b():
    from flow_b import execute
    execute()


def run_suite(junit_path=JUNIT):
    suite=ET.Element('testsuite',name='SPH live G1/G2/G3',tests='5',failures='0',errors='0',skipped='0')
    properties=ET.SubElement(suite,'properties')
    ET.SubElement(properties,'property',name='scope',value='G1/G2/G3 and Flow A/B real live evidence; no pilot sign-off')
    failures=skips=0
    for name,runner in (('g1_http',g1_http),('g2_race',g2_race),('g3_authority',g3_authority),('flow_a',flow_a),('flow_b',flow_b)):
        case=ET.SubElement(suite,'testcase',name=name,classname='sph_live.'+name)
        started=time.monotonic()
        try:
            runner();print(name+': PASS (real live harness)')
        except Unrunnable:
            skips+=1
            ET.SubElement(case,'skipped',message='UNRUNNABLE: no witnessed contention')
            print(name+': SKIP (UNRUNNABLE: no witnessed contention)')
        except Exception as error:
            failures+=1
            frames=traceback.extract_tb(error.__traceback__)
            if frames: print(name+' failure location: '+Path(frames[-1].filename).name+':'+str(frames[-1].lineno))
            ET.SubElement(case,'failure',type=type(error).__name__,message='Live gate assertion failed')
            print(name+': FAIL')
        case.set('time',f'{time.monotonic()-started:.6f}')
    suite.set('failures',str(failures));suite.set('skipped',str(skips))
    ET.SubElement(properties,'property',name='gate_acceptance',
        value='G1-G3 PASS; G4 PENDING' if not failures and not skips else 'G1-G3 INCOMPLETE; G4 PENDING')
    path=Path(junit_path);path.parent.mkdir(exist_ok=True,parents=True)
    ET.indent(suite);ET.ElementTree(suite).write(path,encoding='utf-8',xml_declaration=True)
    # An unrunnable race never yields a green acceptance job.
    return 1 if failures or skips else 0


if __name__=='__main__': raise SystemExit(run_suite())
