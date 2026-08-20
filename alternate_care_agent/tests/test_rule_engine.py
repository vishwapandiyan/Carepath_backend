"""
Run with: python -m pytest tests/test_rule_engine.py -v
(or just: python tests/test_rule_engine.py  -- it will run standalone too)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.schemas import PatientFeatures
from engine.care_classifier import CareClassifier


def load_cases():
    path = Path(__file__).parent / "sample_patients.json"
    return json.loads(path.read_text())


def run():
    classifier = CareClassifier()
    cases = load_cases()
    failures = []

    for case in cases:
        patient = PatientFeatures(**case["patient"])
        decision = classifier.classify(patient)
        ok = decision.rule_id == case["expected_rule_id"]
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}")
        print(f"       -> got {decision.rule_id} ({decision.destination}"
              f"{'/' + decision.specialty if decision.specialty else ''})")
        if not ok:
            failures.append(case["name"])

    print(f"\n{len(cases) - len(failures)}/{len(cases)} passed")
    if failures:
        print("Failed:", failures)
        sys.exit(1)


if __name__ == "__main__":
    run()


def test_all_sample_patients():
    """pytest entrypoint"""
    classifier = CareClassifier()
    for case in load_cases():
        patient = PatientFeatures(**case["patient"])
        decision = classifier.classify(patient)
        assert decision.rule_id == case["expected_rule_id"], (
            f"{case['name']}: expected {case['expected_rule_id']}, got {decision.rule_id}"
        )
