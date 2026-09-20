import json
from pathlib import Path

import pytest

from app.domain.errors import VantageError
from app.providers.llm import validate_interpretation

EVAL_FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "interpretation_eval_cases.json"
)
EVAL_CASES = json.loads(EVAL_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_eval_dataset_structure_and_completeness() -> None:
    assert len(EVAL_CASES) >= 20
    case_ids = [case["case_id"] for case in EVAL_CASES]
    assert len(case_ids) == len(set(case_ids))
    assert {case["category"] for case in EVAL_CASES} >= {
        "contradiction",
        "unsupported_evidence",
        "numeric",
        "advisory",
        "predictive",
        "target_price",
        "accepted_abstention",
        "accepted_cited",
    }
    for case in EVAL_CASES:
        assert isinstance(case["accepted"], bool)
        assert isinstance(case["payload"], dict)
        assert isinstance(case["allowed_evidence_ids"], list)


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda case: case["case_id"])
def test_eval_dataset_uses_runtime_safety_gate(case: dict) -> None:
    if case["accepted"]:
        result = validate_interpretation(
            case["payload"], set(case["allowed_evidence_ids"])
        )
        assert result.model_dump() == case["payload"]
    else:
        with pytest.raises(VantageError) as caught:
            validate_interpretation(case["payload"], set(case["allowed_evidence_ids"]))
        assert caught.value.code == "MODEL_OUTPUT_INVALID"
