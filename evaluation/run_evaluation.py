"""Evaluate the explanation guardrails against the reference dataset.

Default (offline) mode replays scripted model outputs, so it measures the
citation, groundedness, unsupported/unsafe and failure-handling guardrails
without credentials or cost. It does NOT measure live model quality.

  python evaluation/run_evaluation.py          # offline guardrail evaluation
  python evaluation/run_evaluation.py --live   # also asks the configured model
                                               # the supported questions (billed)
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from explanations import (  # noqa: E402
    ExplanationError, ModelConfig, config_from_env, explain,
)
from fieldtech_assistant import build_guidance, load_sources  # noqa: E402

CASES = Path(__file__).with_name("explanation_cases.json")
OFFLINE_CONFIG = ModelConfig("https://offline.invalid", "offline", "offline")


def scripted_model(case):
    def model(_config, _messages):
        if case.get("model_error") == "timeout":
            raise ExplanationError("The model request timed out.")
        if case.get("model_error", "").startswith("http_"):
            raise ExplanationError(f"The model service returned HTTP {case['model_error'][5:]}.")
        output = case["model_output"]
        return output if isinstance(output, str) else json.dumps(output)
    return model


def run_case(case, sources, config, model):
    guidance = build_guidance(case["question"], sources)
    calls = []

    def tracked(cfg, messages):
        calls.append(1)
        return model(cfg, messages)

    try:
        explain(case["question"], guidance, config, tracked)
        outcome = "accepted"
    except ExplanationError:
        outcome = "error" if calls and case.get("model_error") else ("rejected" if calls else "not_called")
    return outcome


def main(argv):
    sources = load_sources()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    failures = []
    for case in cases:
        outcome = run_case(case, sources, OFFLINE_CONFIG, scripted_model(case))
        status = "PASS" if outcome == case["expect"] else "FAIL"
        print(f"{status} {case['id']}: expected {case['expect']}, got {outcome}")
        if status == "FAIL":
            failures.append(case["id"])
    by_category = {}
    for case in cases:
        by_category.setdefault(case["category"], 0)
        by_category[case["category"]] += 1
    print(f"Offline guardrail cases: {len(cases) - len(failures)}/{len(cases)} passed {by_category}")

    if "--live" in argv:
        config = config_from_env()
        supported = [c for c in cases if c["category"] == "supported" and c["id"] == "grounded-f07"]
        accepted = 0
        for case in supported:
            guidance = build_guidance(case["question"], sources)
            try:
                result = explain(case["question"], guidance, config)
                accepted += 1
                print(f"LIVE accepted: {result.text} {result.citations}")
            except ExplanationError as exc:
                print(f"LIVE rejected/failed: {exc}")
        print(f"Live accepted {accepted}/{len(supported)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
