"""Run the synthetic benchmark from any working directory; optionally enforce target gates."""
import argparse
import json
from pathlib import Path
from chat2work.evaluation.harness import evaluate

DATA = Path(__file__).parent / "data"
GATES = {"commitments": .90, "amounts": .95, "dates": .90}
MAX_FALSE_SALE_RATE = .03
REQUIRED_DATASETS = ("conversations.jsonl", "holdout.jsonl", "holdout2.jsonl", "holdout3.jsonl", "holdout4.jsonl")


def failed_gates(report: dict) -> list[str]:
    failed = [f"{name} F1 < {target}" for name, target in GATES.items() if (report["metrics"][name]["f1"] or 0) < target]
    fpr = report["confirmed_sale_false_positive_rate"]
    if fpr is None or fpr >= MAX_FALSE_SALE_RATE:
        failed.append(f"false confirmed-sale rate >= {MAX_FALSE_SALE_RATE}")
    return failed


def select_datasets(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[Path]:
    """Every explicitly selected or required default dataset must exist; never skip one silently."""
    explicit = bool(args.dataset)
    paths = args.dataset or [args.data_dir / name for name in REQUIRED_DATASETS]
    resolved = [p.resolve() for p in paths]
    duplicates = sorted({str(p) for p in resolved if resolved.count(p) > 1})
    if duplicates:
        parser.error("duplicate dataset selected: " + ", ".join(duplicates))
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        kind = "dataset" if explicit else "required default dataset"
        parser.error(f"{kind} not found: " + ", ".join(missing))
    if not paths:
        parser.error("no datasets selected")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, action="append",
                        help="JSONL dataset (repeatable); default: the required splits in --data-dir")
    parser.add_argument("--data-dir", type=Path, default=DATA,
                        help="directory holding the required default splits: " + ", ".join(REQUIRED_DATASETS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="exit 1 when a synthetic technical gate is unmet on any dataset")
    args = parser.parse_args()
    reports = []
    for path in select_datasets(parser, args):
        try:
            reports.append(evaluate(path))
        except (ValueError, json.JSONDecodeError, KeyError) as error:
            parser.error(f"cannot evaluate {path}: {error}")
    if not reports:
        parser.error("no datasets were evaluated")
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
