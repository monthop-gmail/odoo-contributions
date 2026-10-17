"""Install B7c, then upgrade the SAME disposable database to this checkout."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from harness import ROOT, PROJECT, ODOO_ARGS
from upgrade_evidence import upgrade_checks, retained_checks

RETAINED_PREVIOUS='e481eeda8d8fdd3718d8b70c070efa4c7d9edecd'
PREVIOUS='631cd523d014595411b7726b09a6a5eae8175fd8'


def execute(retained=False):
    previous=RETAINED_PREVIOUS if retained else PREVIOUS
    prefix_label="retained-upgrade" if retained else "upgrade"
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    result={'status':'FAIL','previous_sha':previous,
        'final_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'scope':('Retained SYNTHETIC transactions only; NOT production migration' if retained else 'SYNTHETIC empty-business-DB addon update; NOT a business-data migration')}
    try:
        if subprocess.run(['git','cat-file','-e',previous+'^{commit}'],cwd=ROOT,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            # Public repo, no token/credential needed; checkout remains on sph/poc.
            subprocess.run(['git','fetch','--no-tags','--depth=1','origin',previous],
                cwd=ROOT,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        repo=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT,text=True).strip())
        prefix=str(ROOT.relative_to(repo)/'addons')+'/'
        archive=subprocess.check_output(['git','archive',previous,prefix.rstrip('/')],cwd=repo)
        with tempfile.TemporaryDirectory(prefix='.upgrade-',dir=evidence) as directory:
            work=Path(directory);addons=work/'previous-addons';addons.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
                for member in bundle:
                    if not member.isfile():continue
                    assert member.name.startswith(prefix)
                    relative=Path(member.name[len(prefix):]);assert not relative.is_absolute() and '..' not in relative.parts
                    target=addons/relative;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(bundle.extractfile(member).read())
            override=work/'mount.json'
            dc=['docker','compose','--project-name',PROJECT+'-'+prefix_label,'--file',str(ROOT/'compose.yaml'),
                '--file',str(ROOT/'compose.oneshot.yaml'),'--file',str(override)]
            def mount(source):
                override.write_text(json.dumps({'services':{'odoo':{'volumes':[str(source)+':/mnt/extra-addons:ro']}}}))
            def run(args,label,input=None):
                completed=subprocess.run(dc+args,cwd=ROOT,input=input,text=True,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
                (evidence/(prefix_label+'-'+label+'.log')).write_text(completed.stdout)
                completed.check_returncode()
                return completed.stdout
            def probe(phase):
                script='retained_probe.py' if retained else 'upgrade_probe.py'
                code="phase="+repr(phase)+"\nexec(compile(open('/opt/sph/scripts/"+script+"').read(),'"+script+"','exec'))\n"
                output=run(['run','--rm','--no-deps','odoo','shell']+ODOO_ARGS+
                    ['--no-http','--log-level=error'],'probe-'+phase,code)
                rows=[line for line in output.splitlines() if line.startswith('SPH_UPGRADE_PROBE ')]
                assert len(rows)==1
                return json.loads(rows[0].split(' ',1)[1])
            mount(addons)
            try:
                run(['down','--volumes','--remove-orphans'],'initial-down')
                run(['up','--detach','--wait','--wait-timeout','90','postgres'],'postgres')
                run(['run','--rm','--no-deps','odoo']+ODOO_ARGS+['--init=sph_core',
                    '--without-demo=all','--stop-after-init','--no-http'],'install-previous')
                result['before']=probe('before')
                mount(ROOT/'addons')
                run(['run','--rm','--no-deps','odoo']+ODOO_ARGS+['--update=sph_core',
                    '--without-demo=all','--stop-after-init','--no-http'],'update-current')
                result['after']=probe('after')
                result['assertions']=(retained_checks if retained else upgrade_checks)(result['before'],result['after'])
                if not all(result['assertions'].values()):raise ValueError('Measured upgrade check failed')
            finally:
                run(['down','--volumes','--remove-orphans'],'final-down')
                result['teardown']='PASS'
        result['status']='PASS'
    except Exception as error:
        result['error_type']=type(error).__name__
        raise
    finally:
        (evidence/('Retained-upgrade-results.json' if retained else 'Upgrade-results.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('SPH_UPGRADE_RESULT '+json.dumps(result))
    return result


if __name__=='__main__':execute()
