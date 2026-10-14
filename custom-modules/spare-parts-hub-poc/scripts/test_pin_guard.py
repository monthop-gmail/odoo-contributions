"""Negative controls exercise drift detection without Docker or third-party deps."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from check_pins import ROOT, check


class TestPinGuard(unittest.TestCase):
    def test_drift_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sph"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("evidence", "__pycache__"))
            with contextlib.redirect_stdout(io.StringIO()):
                check(root)
            compose_path = root / "compose.yaml"
            original = compose_path.read_text()
            compose = json.loads(original)
            compose["services"]["odoo"]["image"] = "odoo:19.0"
            compose_path.write_text(json.dumps(compose))
            with self.assertRaisesRegex(AssertionError, "image drift"):
                check(root)
            compose_path.write_text(original)
            (root / "requirements.lock").write_text("unreviewed-package==1.0\n")
            with self.assertRaisesRegex(AssertionError, "lock drift"):
                check(root)


if __name__ == "__main__":
    unittest.main()
