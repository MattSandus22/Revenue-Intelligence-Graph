"""Live-model eval for the sentiment task (docs/09 §F offline metrics).

Runs the golden set through the real LLM client and reports accuracy on
overall sentiment (exact + off-by-one-band) and topic recall. Requires
Anthropic credentials — run manually or in a scheduled eval job, not in the
per-commit CI gate (that gate is the adversarial validator suite).

Usage:  python -m rig.evals.model_eval
"""

import json
import sys
from pathlib import Path

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "evals" / "sentiment_golden.jsonl"

BANDS = ["very_negative", "negative", "neutral", "positive", "very_positive"]


def load_golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN_PATH.read_text().splitlines() if line.strip()]


def run(client=None) -> dict:
    from ..llm.gateway import AnthropicLLMClient
    from ..llm.sentiment import SENTIMENT_SCHEMA, SYSTEM

    client = client or AnthropicLLMClient()
    cases = load_golden()
    exact = adjacent = 0
    topic_hits = topic_total = 0
    failures = []

    for case in cases:
        result = client.complete(system=SYSTEM, user=case["text"], schema=SENTIMENT_SCHEMA)
        got = result.output.get("overall", "neutral")
        expected = case["expected_overall"]
        if got == expected:
            exact += 1
        if abs(BANDS.index(got) - BANDS.index(expected)) <= 1:
            adjacent += 1
        else:
            failures.append({"id": case["id"], "expected": expected, "got": got})
        expected_topics = set(case["expected_topics"])
        got_topics = {a["topic"] for a in result.output.get("aspects", [])}
        topic_total += len(expected_topics)
        topic_hits += len(expected_topics & got_topics)

    n = len(cases)
    return {
        "cases": n,
        "overall_exact_accuracy": round(exact / n, 3),
        "overall_adjacent_accuracy": round(adjacent / n, 3),
        "topic_recall": round(topic_hits / topic_total, 3) if topic_total else None,
        "failures": failures,
        # release bar (docs/09 F): adjacent accuracy >= 0.9, topic recall >= 0.8
        "passes_release_bar": (adjacent / n) >= 0.9
                              and (topic_total == 0 or topic_hits / topic_total >= 0.8),
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passes_release_bar"] else 1)
