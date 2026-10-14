"""Out-of-process live-harness hooks; readiness is not gate acceptance."""
import http.client
from pathlib import Path
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "evidence/live-suite.xml"


def g1_http():
    """Check only loopback login readiness; no session, data or credentials."""
    connection = http.client.HTTPConnection("127.0.0.1", 18069, timeout=10)
    try:
        connection.request("GET", "/web/login?db=sph_poc")
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"Expected HTTP 200, received {response.status}")
    finally:
        connection.close()


def run_suite(junit_path=JUNIT):
    suite = ET.Element("testsuite", name="SPH live-harness placeholders",
                       tests="2", failures="0", errors="0", skipped="1")
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="gate_acceptance", value="NOT RUN")
    ET.SubElement(properties, "property", name="scope", value="B3b infrastructure only")
    started = time.monotonic()
    readiness = ET.SubElement(suite, "testcase", name="g1_http",
                             classname="sph_live.placeholder")
    failed = False
    try:
        g1_http()
        print("g1_http: PASS (HTTP readiness only; G1 acceptance NOT RUN)")
    except Exception as error:
        # Do not copy HTTP bodies, exception strings or session data into evidence.
        failed = True
        suite.set("failures", "1")
        ET.SubElement(readiness, "failure", type=type(error).__name__,
                      message="Loopback login GET did not succeed with HTTP 200")
        print("g1_http: FAIL (loopback login GET did not succeed with HTTP 200)")
    readiness.set("time", f"{time.monotonic() - started:.6f}")
    race = ET.SubElement(suite, "testcase", name="g2_race",
                        classname="sph_live.placeholder", time="0")
    ET.SubElement(race, "skipped", message="UNRUNNABLE: not implemented")
    print("g2_race: SKIP (UNRUNNABLE: not implemented)")
    print("G1-G3 acceptance: NOT RUN; placeholders do not satisfy the gates")
    junit_path = Path(junit_path)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(suite)
    ET.ElementTree(suite).write(junit_path, encoding="utf-8", xml_declaration=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_suite())
