"""Observe packages in the pinned image; no network, installation or secrets."""
import importlib.metadata
import json
import platform
import subprocess

import odoo.release


def inventory():
    packages = sorted({
        (dist.metadata.get("Name").lower().replace("_", "-"), dist.version)
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    })
    return {
        "python": platform.python_version(),
        "odoo_version": odoo.release.version,
        "odoo_deb": subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", "odoo"], text=True
        ),
        "packages": [f"{name}=={version}" for name, version in packages],
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
