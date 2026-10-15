"""Launch the committed-DB HTTP race outside Odoo's test process."""
import json
import os
import subprocess
from harness import DC, ODOO_ARGS, ROOT


class Unrunnable(RuntimeError):
    pass


def execute():
    count=int(os.environ.get('SPH_RACE_ROUNDS','4'))
    code=f"round_count={count}\n" + """import traceback, json
try:
    exec(compile(open('/opt/sph/scripts/g2_worker.py').read(), 'g2_worker.py', 'exec'))
except Exception as error:
    print('SPH_G2_FAILURE '+json.dumps({'type':type(error).__name__, 'frames':[(frame.filename.rsplit('/',1)[-1],frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]}))
    raise
"""
    result=subprocess.run(DC+['exec','-T','odoo','odoo','shell']+ODOO_ARGS+
        ['--no-http','--log-level=error'],input=code,text=True,capture_output=True,timeout=180)
    lines=result.stdout.splitlines()
    witnesses=[line for line in lines if line.startswith('SPH_G2_LOCK_WITNESS ')]
    for line in witnesses: print(line)
    final=[line for line in lines if line.startswith('SPH_G2_RESULT ')]
    if result.returncode or not final:
        if 'UNRUNNABLE: no witnessed contention' in result.stderr:
            raise Unrunnable('No witnessed lock contention')
        import re
        for line in lines:
            if line.startswith('SPH_G2_FAILURE '): print(line)
        locations=re.findall(r'g2_worker.py[^\n]*line (\d+)',result.stderr+result.stdout)
        print('G2 worker failure location: '+(locations[-1] if locations else 'bootstrap'))
        raise RuntimeError('G2 standalone race failed')
    stats=json.loads(final[-1].split(' ',1)[1])
    if not stats['lock_wait_rounds']:
        raise Unrunnable('No witnessed lock contention')
    logs_result=subprocess.run(DC+['logs','--no-color','odoo'],text=True,capture_output=True,check=True)
    logs=logs_result.stdout+logs_result.stderr
    lock_lines=[line for line in logs.splitlines() if 'SPH_LOCK_WAIT:' in line]
    if not lock_lines:
        raise Unrunnable('No server-side lock witness')
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    # Preserve sanitized server-side transaction-conflict/retry lines, not SQL dumps.
    retry_lines=[line for line in logs.splitlines() if any(marker in line.lower()
        for marker in ('serialization_failure','could not serialize access','serialization failure','retrying transaction'))]
    (evidence/'G2-retry-serialization.log').write_text(
        '\n'.join(retry_lines)+'\n' if retry_lines else 'No serialization/retry lines observed; lock contention witnessed separately.\n')
    stats['retry_serialization_log_lines']=len(retry_lines)
    (evidence/'G2-lock-waits.log').write_text('\n'.join(lock_lines)+'\n')
    (evidence/'G2-request-results.json').write_text(json.dumps(stats,indent=2)+'\n')
    pins=json.loads((ROOT/'version-pins.json').read_text())
    sha=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    (evidence/'manifest.json').write_text(json.dumps({'scope':'SYNTHETIC ASSUMPTION: G2 committed live HTTP race',
        'commit':sha,'round_count':count,'isolation':stats['isolation'],'odoo':pins['odoo'],
        'postgres':pins['postgres'],'race':stats},indent=2)+'\n')
    print('g2_race stats: '+json.dumps({key:stats[key] for key in ('round_count','double_allocations','lock_wait_rounds')}))
