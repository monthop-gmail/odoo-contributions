"""Validate all Odoo summaries and the binding list of executed test names."""
import re


def validate_test_log(log, expected):
    summaries = re.findall(r"\b(\d+) failed, (\d+) error", log)
    if not summaries:
        raise ValueError("No Odoo test summary")
    if any(int(failed) or int(errors) for failed, errors in summaries):
        raise ValueError("Nonzero Odoo test summary")
    if re.search(r"\bERROR\b|(?m:^\s*FAIL:)", log):
        raise ValueError("Odoo ERROR/FAIL test log")
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Invalid binding expected-test list")
    executed = set(re.findall(r"\bStarting\s+(\w+\.\w+)\s+\.{3}", log))
    missing = set(expected) - executed
    if missing:
        raise ValueError("Binding tests not executed: " + ", ".join(sorted(missing)))
