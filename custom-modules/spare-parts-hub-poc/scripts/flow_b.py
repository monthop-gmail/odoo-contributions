"""One command: clean disposable harness -> synthetic Flow B -> evidence -> down."""
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from harness import DC, ODOO_ARGS, ROOT


def execute():
    code="""import json,traceback
try:
    exec(compile(open('/opt/sph/scripts/flow_b_worker.py').read(),'flow_b_worker.py','exec'))
except Exception as error:
    print('SPH_FLOW_B_FAILURE '+json.dumps({'type':type(error).__name__,'frames':[(f.filename.rsplit('/',1)[-1],f.lineno) for f in traceback.extract_tb(error.__traceback__)]}))
    raise
"""
    run=subprocess.run(DC+['exec','-T','odoo','odoo','shell']+ODOO_ARGS+
        ['--no-http','--log-level=error'],input=code,text=True,capture_output=True,timeout=120)
    lines=run.stdout.splitlines()
    results=[line for line in lines if line.startswith('SPH_FLOW_B_RESULT ')]
    if run.returncode or not results:
        for line in lines:
            if line.startswith('SPH_FLOW_B_FAILURE '):print(line)
        raise RuntimeError('Flow B live assertions failed')
    result=json.loads(results[-1].split(' ',1)[1])
    result['commit']=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    result['pins']=json.loads((ROOT/'version-pins.json').read_text())
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    (evidence/'Flow-B-results.json').write_text(json.dumps(result,indent=2)+'\n')
    suite=ET.Element('testsuite',name='Synthetic Flow B',tests='1',failures='0',errors='0')
    ET.SubElement(suite,'testcase',classname='sph_flow_b',name='shortage_bot_draft_human_confirm')
    ET.ElementTree(suite).write(evidence/'Flow-B-assertions.xml',encoding='utf-8',xml_declaration=True)
    print('SPH_FLOW_B_RESULT '+json.dumps({k:v for k,v in result.items() if k!='pins'}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--running',action='store_true',help='Use an already-running disposable harness (CI).')
    args=parser.parse_args()
    if args.running:
        execute();return
    print('WARNING: wipes this checkout disposable harness volumes. NEVER point at a non-disposable DB.',file=sys.stderr,flush=True)
    harness=[sys.executable,str(ROOT/'scripts/harness.py')]
    subprocess.run(harness+['down'],check=True)
    try:
        subprocess.run(harness+['up'],check=True)
        execute()
    finally:
        subprocess.run(harness+['down'],check=True)


if __name__=='__main__':main()
