"""Read-only proof that the full live suite starts in a fresh synthetic DB."""
import json
import subprocess
from harness import DC, ODOO_ARGS, ROOT


def capture():
    code="""import json
assert env.cr.dbname=='sph_poc'
data={'database':'sph_poc','companies':env['res.company'].search_count([]),
    'sales':env['sale.order'].search_count([]),'purchases':env['purchase.order'].search_count([]),
    'reservations':env['sph.reservation'].search_count([])}
assert data['companies']==1 and data['sales']==data['purchases']==data['reservations']==0
print('SPH_FRESH_START '+json.dumps(data),flush=True)
"""
    result=subprocess.run(DC+['exec','-T','odoo','odoo','shell']+ODOO_ARGS+
        ['--no-http','--log-level=error'],input=code,text=True,capture_output=True,check=True,timeout=60)
    lines=[line for line in result.stdout.splitlines() if line.startswith('SPH_FRESH_START ')]
    assert len(lines)==1
    data=json.loads(lines[0].split(' ',1)[1])
    data['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (ROOT/'evidence/Fresh-live-start.json').write_text(json.dumps(data,indent=2)+'\n')
    return data
