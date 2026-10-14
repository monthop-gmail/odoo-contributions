"""Self-contained, passwordless, synthetic-only local/CI Docker harness."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

from test_results import validate_test_log

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "sph-poc-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
DC = ["docker", "compose", "--project-name", PROJECT, "--file", str(ROOT / "compose.yaml")]
ONESHOT_DC = DC + ["--file", str(ROOT / "compose.oneshot.yaml")]
EVIDENCE = ROOT / "evidence"
ODOO_ARGS = [
    "--db_host=postgres", "--db_user=odoo", "--db_password=",
    "--database=sph_poc", "--db-filter=^sph_poc$", "--no-database-list",
    "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons",
    "--data-dir=/var/lib/odoo", "--workers=0", "--max-cron-threads=0",
]


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def down():
    run(DC + ["down", "--volumes", "--remove-orphans"])


def capture_inventory():
    EVIDENCE.mkdir(exist_ok=True)
    result = run(DC + ["run", "--rm", "--no-deps", "--entrypoint", "python3",
                       "odoo", "/opt/sph/scripts/runtime_inventory.py"],
                 stdout=subprocess.PIPE, text=True)
    # Validate JSON before saving; this output contains version metadata only.
    data = json.loads(result.stdout)
    (EVIDENCE / "runtime.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(data, sort_keys=True), flush=True)


def install(test=False):
    args = ODOO_ARGS + ["--init=sph_core", "--without-demo=all", "--stop-after-init", "--no-http"]
    if test:
        args += ["--test-enable", "--test-tags=/sph_core", "--log-level=test"]
    result = subprocess.run(ONESHOT_DC + ["run", "--rm", "--no-deps", "odoo"] + args,
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / ("odoo-tests.log" if test else "odoo-install.log")).write_text(result.stdout)
    print(result.stdout, end="", flush=True)
    result.check_returncode()
    if test:
        expected = json.loads((ROOT / "expected-tests.json").read_text())
        validate_test_log(result.stdout, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down", "test", "inventory"])
    args = parser.parse_args()
    if args.action == "down":
        down()
        return
    run([sys.executable, str(ROOT / "scripts/check_pins.py")])
    run(["docker", "compose", "version"])
    run(DC + ["pull"])
    if args.action == "inventory":
        capture_inventory()
        return
    if args.action == "test":
        # Only this checkout's dedicated compose project is destroyed.
        down()
    try:
        run(DC + ["up", "--detach", "--wait", "--wait-timeout", "90", "postgres"])
        capture_inventory()
        run([sys.executable, str(ROOT / "scripts/check_pins.py"),
             "--runtime", str(EVIDENCE / "runtime.json")])
        pg = run(DC + ["exec", "-T", "postgres", "postgres", "--version"],
                 stdout=subprocess.PIPE, text=True).stdout.strip()
        pins = json.loads((ROOT / "version-pins.json").read_text())
        assert pg == pins["postgres"]["runtime_version"], "PostgreSQL runtime drift"
        (EVIDENCE / "postgres-version.txt").write_text(pg + "\n")
        install(test=args.action == "test")
        if args.action == "up":
            run(DC + ["up", "--detach", "--wait", "--wait-timeout", "120", "odoo"])
            url = "http://127.0.0.1:18069/web/login?db=sph_poc"
            try:
                with urllib.request.urlopen(url, timeout=10) as response:
                    assert response.status == 200, "Loopback UI did not respond"
            except Exception:
                run(DC + ["ps"])
                run(DC + ["logs", "--tail", "50", "odoo"])
                raise
            (EVIDENCE / "ui-startup.json").write_text(
                json.dumps({"loopback_http_status": 200, "container_health": "healthy"}) + "\n"
            )
            print("Synthetic harness: http://127.0.0.1:18069 ; down removes its database.")
    finally:
        if args.action == "test":
            down()


if __name__ == "__main__":
    main()
