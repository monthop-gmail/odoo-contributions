"""Out-of-process live-harness hooks; readiness is not gate acceptance."""
import http.client
from pathlib import Path
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "evidence/live-suite.xml"


def g1_http():
    from g1_http import execute
    execute()


def run_suite(junit_path=JUNIT):
    suite = ET.Element("testsuite", name="SPH live-harness G1",
                       tests="2", failures="0", errors="0", skipped="1")
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="gate_acceptance", value="NOT RUN")
    ET.SubElement(properties, "property", name="scope", value="B4b real G1; G2 unimplemented")
    started = time.monotonic()
    readiness = ET.SubElement(suite, "testcase", name="g1_http",
                             classname="sph_live.placeholder")
    failed = False
    try:
        g1_http()
        print("g1_http: PASS (real isolation HTTP matrix)")
    except Exception as error:
        # Do not copy HTTP bodies, exception strings or session data into evidence.
        failed = True
        suite.set("failures", "1")
        ET.SubElement(readiness, "failure", type=type(error).__name__,
                      message="G1 live isolation matrix failed")
        print("g1_http: FAIL (loopback login GET did not succeed with HTTP 200)")
    readiness.set("time", f"{time.monotonic() - started:.6f}")
    race = ET.SubElement(suite, "testcase", name="g2_race",
                        classname="sph_live.placeholder", time="0")
    ET.SubElement(race, "skipped", message="UNRUNNABLE: not implemented")
    print("g2_race: SKIP (UNRUNNABLE: not implemented)")
    print("G1 HTTP matrix executed; G2/G3 NOT RUN")
    junit_path = Path(junit_path)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(suite)
    ET.ElementTree(suite).write(junit_path, encoding="utf-8", xml_declaration=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_suite())
