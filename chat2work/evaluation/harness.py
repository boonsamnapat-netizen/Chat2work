"""Micro precision/recall/F1 of exact events; booleans scored separately.

Gold ``amounts`` are ``[amount, role]`` pairs. ``amounts`` scores values only;
``amount_roles`` additionally requires the role (total/deposit/budget/...) to match.
"""
from collections import Counter
import json
from pathlib import Path
from ..engine import analyze

METRICS = ("commitments", "amounts", "amount_roles", "dates", "commercial_intent", "decision_pending", "confirmed_sale")


def _score(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def load(path: str | Path) -> list[dict]:
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        raise ValueError("Benchmark dataset must not be empty")
    return cases


def evaluate(path: str | Path) -> dict:
    cases = load(path)
    counts = {k: Counter() for k in METRICS}
    failures = []
    negatives = false_sales = opportunities_correct = 0
    for case in cases:
        analysis = analyze(case["conversation"])
        expected = dict(case["expected"])
        expected["amount_roles"] = [tuple(a) for a in expected["amounts"]]
        expected["amounts"] = [a[0] for a in expected["amounts"]]
        money = [s.value for s in analysis.signals if s.type == "monetary_amount"]
        actual = {
            "commitments": {(s.type, s.actor, s.value) for s in analysis.signals if s.type in {"business_commitment", "customer_commitment"}},
            "amounts": [v["amount"] for v in money],
            "amount_roles": [(v["amount"], v["role"]) for v in money],
            "dates": [s.value["raw"] for s in analysis.signals if s.type in {"deadline", "schedule"}],
            "commercial_intent": analysis.commercial_intent,
            "decision_pending": analysis.decision_pending,
            "confirmed_sale": analysis.confirmed_sale,
        }
        mismatch = {}
        for metric, predicted in actual.items():
            gold = expected[metric]
            if metric == "commitments":
                gold = {tuple(c) for c in gold}
            if isinstance(predicted, bool):
                tp, fp, fn = int(predicted and gold), int(predicted and not gold), int(not predicted and gold)
                correct = predicted == gold
            else:
                pred_counts, gold_counts = Counter(predicted), Counter(gold)
                tp = sum((pred_counts & gold_counts).values())
                fp, fn = sum((pred_counts - gold_counts).values()), sum((gold_counts - pred_counts).values())
                correct = pred_counts == gold_counts
            counts[metric].update(tp=tp, fp=fp, fn=fn, correct=int(correct))
            if not correct:
                mismatch[metric] = dict(expected=sorted(gold) if isinstance(gold, (set, list)) else gold,
                                        actual=sorted(predicted) if isinstance(predicted, (set, list)) else predicted)
        amount_correct = analysis.potential_revenue.amount == expected["potential_revenue"]
        opportunities_correct += amount_correct
        if not amount_correct:
            mismatch["potential_revenue"] = dict(expected=expected["potential_revenue"], actual=analysis.potential_revenue.amount)
        if not expected["confirmed_sale"]:
            negatives += 1
            false_sales += analysis.confirmed_sale
        if mismatch:
            failures.append(dict(id=case["id"], mismatches=mismatch))
    metrics = {k: dict(_score(v["tp"], v["fp"], v["fn"]), exact_case_accuracy=v["correct"] / len(cases)) for k, v in counts.items()}
    return dict(dataset=Path(path).name, split=cases[0].get("split", "dev"), cases=len(cases),
                industries=sorted({c["industry"] for c in cases}),
                metrics=metrics, confirmed_sale_false_positive_rate=false_sales / negatives if negatives else None,
                negative_sale_cases=negatives, false_confirmed_sales=false_sales,
                opportunity_amount_accuracy=opportunities_correct / len(cases),
                human_rated_action_usefulness=None, failures=failures,
                limitations="Hand-authored synthetic Thai conversations; no real-world accuracy or human usefulness established.")
