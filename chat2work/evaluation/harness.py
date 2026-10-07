"""Micro precision/recall/F1 of exact events; booleans scored separately.

Gold ``amounts`` are ``[amount, role]`` pairs. ``amounts`` scores values only;
``amount_roles`` additionally requires the role (total/deposit/budget/...) to match.
"""
from collections import Counter
import json
from pathlib import Path
from ..engine import analyze

# Deal states where the engine abstains from a sale decision and asks a person.
REVIEW_STATES = {"possible_acceptance", "acceptance_needs_review", "changed_needs_review", "cancellation_needs_review"}
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
    negatives = false_sales = opportunities_correct = reviewed = abstained = 0
    for case in cases:
        analysis = analyze(case["conversation"])
        reviewed += analysis.review_required
        abstained += analysis.deal_status in REVIEW_STATES
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
                sale_recall=metrics["confirmed_sale"]["recall"],
                review_rate=reviewed / len(cases), sale_abstention_rate=abstained / len(cases),
                human_rated_action_usefulness=None, failures=failures,
                limitations="Hand-authored synthetic Thai conversations; no real-world accuracy or human usefulness established.")


def evaluate_actions(path: str | Path) -> dict:
    """Score proposed actions and still-open obligations, not just extracted labels.

    A scenario passes when the sale decision matches, every required action is proposed, no
    forbidden action is proposed, and the set of open obligations (commitments still tracked)
    matches exactly."""
    cases = load(path)
    passed, failures = 0, []
    required_total = required_hit = forbidden_total = forbidden_hit = obligations_ok = 0
    sale_tp = sale_fp = sale_fn = negatives = reviewed = abstained = 0
    for case in cases:
        a = analyze(case["conversation"])
        expected = case["expected"]
        proposed = {x.type for x in a.recommended_actions}
        by_id = {s.id: s for s in a.signals}
        open_now = sorted(by_id[i].value for x in a.recommended_actions if x.type == "track_commitment" for i in x.signal_ids)
        missing_required = sorted(set(expected["required_actions"]) - proposed)
        present_forbidden = sorted(set(expected["forbidden_actions"]) & proposed)
        obligations_match = open_now == sorted(expected["open_obligations"])
        sale_ok = a.confirmed_sale == expected["confirmed_sale"]
        required_total += len(expected["required_actions"])
        required_hit += len(expected["required_actions"]) - len(missing_required)
        forbidden_total += len(expected["forbidden_actions"])
        forbidden_hit += len(present_forbidden)
        obligations_ok += obligations_match
        sale_tp += a.confirmed_sale and expected["confirmed_sale"]
        sale_fp += a.confirmed_sale and not expected["confirmed_sale"]
        sale_fn += not a.confirmed_sale and expected["confirmed_sale"]
        negatives += not expected["confirmed_sale"]
        reviewed += a.review_required
        abstained += a.deal_status in REVIEW_STATES
        if sale_ok and not missing_required and not present_forbidden and obligations_match:
            passed += 1
        else:
            failures.append(dict(id=case["id"], sale=dict(expected=expected["confirmed_sale"], actual=a.confirmed_sale),
                                 missing_required=missing_required, present_forbidden=present_forbidden,
                                 open_obligations=dict(expected=sorted(expected["open_obligations"]), actual=open_now)))
    n = len(cases)
    return dict(dataset=Path(path).name, split=cases[0].get("split", "action_scenarios"), cases=n,
                action_case_accuracy=passed / n,
                required_action_recall=required_hit / required_total if required_total else None,
                forbidden_action_rate=forbidden_hit / forbidden_total if forbidden_total else None,
                open_obligation_accuracy=obligations_ok / n,
                sale_recall=sale_tp / (sale_tp + sale_fn) if sale_tp + sale_fn else None,
                confirmed_sale_false_positive_rate=sale_fp / negatives if negatives else None,
                false_confirmed_sales=sale_fp, negative_sale_cases=negatives,
                review_rate=reviewed / n, sale_abstention_rate=abstained / n,
                human_rated_action_usefulness=None, failures=failures,
                limitations="Hand-written synthetic scenarios; action correctness against the author's labels, not human usefulness.")
