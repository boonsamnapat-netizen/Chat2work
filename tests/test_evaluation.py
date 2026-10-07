import json
from pathlib import Path

import pytest

from chat2work.evaluation.harness import evaluate, load, _score

DATA = Path(__file__).resolve().parents[1] / "data"
DATASETS = [DATA / "conversations.jsonl", DATA / "holdout.jsonl", DATA / "holdout2.jsonl"]
INDUSTRIES = {"air_conditioning", "cctv", "electrical", "repair", "contractor", "printing",
              "freelance_design", "agency", "solar", "interior", "noncommercial"}


def test_dataset_diversity_and_labelling():
    rows = [r for path in DATASETS for r in load(path)]
    assert len(load(DATASETS[0])) >= 30 and len({r["id"] for r in rows}) == len(rows)
    assert {r["industry"] for r in rows} == INDUSTRIES
    assert all(r["synthetic"] is True for r in rows)
    for r in rows:
        assert all(len(a) == 2 and a[1] in {"price", "total", "deposit", "budget", "unit_price", "previous_price", "discount", "balance", "payment"} for a in r["expected"]["amounts"])
    tags = {t for r in rows for t in r.get("tags", [])}
    for scenario in ("acceptance", "cancellation", "noncommercial", "missed_payment", "quotation_promise", "multiple_amounts"):
        assert scenario in tags
    assert any(r["expected"]["confirmed_sale"] for r in rows) and any(not r["expected"]["confirmed_sale"] for r in rows)


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_evaluation_gates_and_no_fabricated_usefulness(path):
    report = evaluate(path)
    assert report["metrics"]["commitments"]["f1"] >= .90
    assert report["metrics"]["amounts"]["f1"] >= .95
    assert report["metrics"]["dates"]["f1"] >= .90
    assert report["confirmed_sale_false_positive_rate"] < .03
    assert report["human_rated_action_usefulness"] is None


def test_score_penalizes_false_positive_and_false_negative():
    score = _score(2, 1, 1)
    assert score["precision"] == score["recall"] == score["f1"] == pytest.approx(2/3)
    assert _score(0, 0, 0)["f1"] is None


def test_empty_benchmark_not_reported_as_perfect(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    with pytest.raises(ValueError):
        evaluate(path)


def _evaluate_one(tmp_path, case):
    path = tmp_path / "one.jsonl"
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    return evaluate(path)["metrics"]


def test_amount_duplicates_are_scored(tmp_path):
    case = load(DATASETS[0])[0]  # gold: [["43000", "price"]]
    case["expected"]["amounts"].append(["43000", "price"])
    assert _evaluate_one(tmp_path, case)["amounts"]["fn"] == 1


def test_wrong_amount_role_is_scored(tmp_path):
    case = load(DATASETS[0])[0]
    case["expected"]["amounts"] = [["43000", "deposit"]]
    metrics = _evaluate_one(tmp_path, case)
    assert metrics["amounts"]["fn"] == metrics["amounts"]["fp"] == 0
    assert metrics["amount_roles"]["fn"] == metrics["amount_roles"]["fp"] == 1
