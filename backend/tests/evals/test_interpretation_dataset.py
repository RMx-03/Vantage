import json
from pathlib import Path
import pytest
from app.domain.research import AIInterpretation

EVAL_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "interpretation_eval_cases.json"


@pytest.fixture
def eval_cases() -> list[dict]:
    assert EVAL_FIXTURE_PATH.exists(), f"Evaluation fixture missing: {EVAL_FIXTURE_PATH}"
    cases = json.loads(EVAL_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 20, f"Evaluation dataset must contain at least 20 cases, found {len(cases)}"
    return cases


def test_eval_dataset_structure_and_completeness(eval_cases: list[dict]) -> None:
    case_ids = [c["case_id"] for c in eval_cases]
    assert len(case_ids) == len(set(case_ids)), "All case_ids in eval dataset must be unique"
    for case in eval_cases:
        assert "case_id" in case
        assert "metrics" in case
        assert "evidence" in case
        assert "expected_labels" in case
        assert "must_reference_only" in case
        assert "must_not_contain" in case
        assert "allow_abstention" in case
        assert "mock_response" in case


def test_eval_dataset_schema_and_safety_gate(eval_cases: list[dict]) -> None:
    for case in eval_cases:
        mock_resp = case["mock_response"]

        # 1. 100% schema validity
        interpretation = AIInterpretation.model_validate(mock_resp)

        # 2. Label alignment
        assert interpretation.sentiment_label in case["expected_labels"], (
            f"Case {case['case_id']}: label {interpretation.sentiment_label} not in expected {case['expected_labels']}"
        )

        # 3. 100% evidence-ID precision
        allowed_ids = set(case["must_reference_only"])
        for eid in interpretation.evidence_ids:
            assert eid in allowed_ids, (
                f"Case {case['case_id']}: referenced evidence {eid} not in allowed {allowed_ids}"
            )

        # 4. 100% forbidden-language absence
        forbidden = case["must_not_contain"]
        text_corpus = f"{interpretation.summary} {' '.join(interpretation.warnings)} {interpretation.abstention_reason or ''}".lower()
        for forbidden_word in forbidden:
            assert forbidden_word.lower() not in text_corpus, (
                f"Case {case['case_id']}: contains forbidden phrase '{forbidden_word}'"
            )

        # 5. Correct abstention allowance
        if interpretation.abstained:
            assert case["allow_abstention"] is True, (
                f"Case {case['case_id']}: abstained but allow_abstention is False"
            )
            assert interpretation.abstention_reason is not None and len(interpretation.abstention_reason) > 0, (
                f"Case {case['case_id']}: abstained without providing abstention_reason"
            )
            assert interpretation.sentiment_score is None, (
                f"Case {case['case_id']}: abstained output must not have a numeric sentiment score"
            )
        else:
            assert interpretation.sentiment_score is not None or interpretation.sentiment_label == "unavailable"
