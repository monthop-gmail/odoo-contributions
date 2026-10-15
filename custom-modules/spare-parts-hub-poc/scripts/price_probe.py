"""Run probe against the live disposable harness; no sessions in evidence."""
import json
import subprocess
from harness import DC, ODOO_ARGS, ROOT


def execute(require_denied=False):
    code=f'require_denied={require_denied!r}\n'+"""import json, traceback
try:
    exec(compile(open('/opt/sph/scripts/price_probe_worker.py').read(),'price_probe_worker.py','exec'))
except Exception as error:
    print('SPH_PRICE_FAILURE '+json.dumps({'type':type(error).__name__,'frames':[(f.filename.rsplit('/',1)[-1],f.lineno) for f in traceback.extract_tb(error.__traceback__)]}))
    raise
"""
    result=subprocess.run(DC+['exec','-T','odoo','odoo','shell']+ODOO_ARGS+
        ['--no-http','--log-level=error'],input=code,text=True,capture_output=True,timeout=90)
    lines=result.stdout.splitlines()
    final=[line for line in lines if line.startswith('SPH_PRICE_PROBE ')]
    if result.returncode or not final:
        for line in lines:
            if line.startswith('SPH_PRICE_FAILURE '):print(line)
        raise RuntimeError('Live price probe failed')
    data=json.loads(final[-1].split(' ',1)[1])
    directory=ROOT/'evidence';directory.mkdir(exist_ok=True)
    (directory/'B5a-price-probe.json').write_text(json.dumps(data,indent=2)+'\n')
    print('B5a live price probe: '+json.dumps(data))
