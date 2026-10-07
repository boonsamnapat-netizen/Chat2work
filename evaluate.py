"""Run the synthetic benchmark from any working directory; optionally enforce target gates."""
import argparse
import json
from pathlib import Path
from chat2work.evaluation.harness import evaluate

DATA = Path(__file__).parent / "data"
GATES = {"commitments": .90, "amounts": .95, "dates": .90}
MAX_FALSE_SALE_RATE = .03


def failed_gates(report: dict) -> list[str]:
    failed = [f"{name} F1 < {target}" for name, target in GATES.items() if (report["metrics"][name]["f1"] or 0) < target]
    fpr = report["confirmed_sale_false_positive_rate"]
    if fpr is None or fpr >= MAX_FALSE_SALE_RATE:
        failed.append(f"false confirmed-sale rate >= {MAX_FALSE_SALE_RATE}")
    return failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, action="append",
                        help="JSONL dataset (repeatable); default: every data/*.jsonl split")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="exit 1 when a synthetic technical gate is unmet on any dataset")
    args = parser.parse_args()
    datasets = args.dataset or [DATA / "conversations.jsonl", DATA / "holdout.jsonl", DATA / "holdout2.jsonl"]
    reports = [evaluate(path) for path in datasets if path.exists()]
    for report in reports:
        report["failed_gates"] = failed_gates(report)
    content = json.dumps(reports, ensure_ascii=False, indent=2)
    print(content)
    if args.output:
        args.output.write_text(content + "\n", encoding="utf-8")
    if args.check and any(r["failed_gates"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
