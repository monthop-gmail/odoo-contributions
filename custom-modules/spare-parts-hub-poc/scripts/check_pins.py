"""Fail closed on static pin drift, or on observed runtime drift with --runtime."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT, runtime=None):
    if not __debug__:
        raise RuntimeError("Pin validation requires Python without optimization")
    pins = json.loads((root / "version-pins.json").read_text())
    compose = json.loads((root / "compose.yaml").read_text())
    assert pins["platform"] == "linux/amd64", "unsupported platform"
    for name in ("odoo", "postgres"):
        pin = pins[name]
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", pin["digest"]), name
        assert compose["services"][name]["image"] == (
            f"{pin['repository']}:{pin['tag']}@{pin['digest']}"
        ), f"{name} image drift"
        assert compose["services"][name]["platform"] == pins["platform"]
        assert "build" not in compose["services"][name], "unreviewed image build"
    assert pins["odoo"]["tag"].startswith("19.0-"), "Odoo baseline drift"
    assert pins["odoo"]["deb_version"].startswith("19.0."), "Odoo build drift"
    assert re.fullmatch(r"[0-9a-f]{40}", pins["odoo"]["docker_build_ref"])
    assert re.fullmatch(r"[0-9a-f]{40}", pins["odoo"]["deb_sha1"])
    assert pins["postgres"]["tag"] == "16.15-bookworm", "PostgreSQL version drift"
    manifest = ast.literal_eval((root / "addons/sph_core/__manifest__.py").read_text())
    assert manifest["version"] == "19.0.0.1.0", "module version drift"
    assert manifest["license"] == "Other OSI approved licence"
    assert manifest["depends"] == ["stock", "purchase", "sale_management", "portal"]
    for name, expected in pins["lock_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, (
            f"{name} lock drift"
        )
    if runtime is not None:
        observed = json.loads(Path(runtime).read_text())
        assert observed["odoo_deb"] == pins["odoo"]["deb_version"], "Odoo package drift"
        assert observed["odoo_version"] == pins["odoo"]["runtime_version"], "Odoo release drift"
        assert observed["python"] == pins["python_version"], "Python runtime drift"
        expected = (root / "runtime-python.lock").read_text().splitlines()
        assert observed["packages"] == expected, "Python distribution inventory drift"
    print("SPH version pins PASS" + (" (runtime verified)" if runtime else " (static)"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", help="Observed runtime JSON from the pinned image")
    args = parser.parse_args()
    check(runtime=args.runtime)
