"""Run real G3 HTTP transactions and persist only sanitized evidence."""
import json
import subprocess
import xml.etree.ElementTree as ET
from harness import DC, ODOO_ARGS, ROOT


def execute():
    from price_probe import execute as probe
    probe()
    code="""import json, traceback
try:
    exec(compile(open('/opt/sph/scripts/g3_worker.py').read(),'g3_worker.py','exec'))
except Exception as error:
    print('SPH_G3_FAILURE '+json.dumps({'type':type(error).__name__,'frames':[(f.filename.rsplit('/',1)[-1],f.lineno) for f in traceback.extract_tb(error.__traceback__)]}))
    raise
"""
    result=subprocess.run(DC+['exec','-T','odoo','odoo','shell']+ODOO_ARGS+
        ['--no-http','--log-level=error'],input=code,text=True,capture_output=True,timeout=120)
    lines=result.stdout.splitlines()
    final=[line for line in lines if line.startswith('SPH_G3_RESULT ')]
    if result.returncode or not final:
        for line in lines:
            if line.startswith(('SPH_G3_FAILURE ','SPH_G3_CHECK ')):print(line)
        raise RuntimeError('G3 live assertions failed')
    data=json.loads(final[-1].split(' ',1)[1])
    directory=ROOT/'evidence';directory.mkdir(exist_ok=True)
    (directory/'G3-authority-results.json').write_text(json.dumps(data,indent=2)+'\n')
    suite=ET.Element('testsuite',name='G3 committed HTTP authority',tests=str(len(data['matrix'])),failures='0',errors='0')
    for row in data['matrix']:
        ET.SubElement(suite,'testcase',classname='sph_g3.'+row['role'],name=row['action']+'.'+row['outcome'])
    ET.ElementTree(suite).write(directory/'G3-assertions.xml',encoding='utf-8',xml_declaration=True)
    print('g3_authority stats: '+json.dumps({key:data[key] for key in ('deny_rows_observed','allow_rows_observed','maker_checker_distinct')}))
