"""Farm doctor: ranking quality plus the safety rules the proposal demands."""

from __future__ import annotations

from app.config import settings
from app.engine import diseases

BXW_ANSWERS = {
    "speed": "days",
    "pattern": "one",
    "fruit": "premature",
    "bud": "black",
    "inside": "brown",
    "leaves": "yellow",
}
SIGATOKA_ANSWERS = {
    "speed": "weeks",
    "leaves": "spots",
    "conditions": "wet",
    "pattern": "many",
    "fruit": "small",
}
BUunchy_TOP = {
    "speed": "weeks",
    "leaves": "narrow",
    "pests": "aphids",
    "pattern": "one",
    "fruit": "none",
}


def test_classic_bxw_ranks_bxw_first():
    result = diseases.assess(BXW_ANSWERS)
    assert result.top is not None
    assert result.top.key == "bxw"


def test_sigatoka_ranks_above_wilt_when_only_leaf_spots_are_reported():
    result = diseases.assess(SIGATOKA_ANSWERS)
    assert result.top.key == "black_sigatoka"


def test_bunchy_top_signs_rank_bunchy_top():
    result = diseases.assess(BUunchy_TOP)
    assert result.top.key == "bunchy_top"


def test_confidence_is_capped_below_certainty():
    for answers in (
        BXW_ANSWERS,
        SIGATOKA_ANSWERS,
        {q["id"]: q["options"][0]["id"] for q in diseases.questions()},
    ):
        result = diseases.assess(answers)
        assert result.confidence <= diseases.CONFIDENCE_CAP
        assert result.confidence < 1.0


def test_notifiable_conditions_always_refer_to_a_person():
    # Even a one-sided, confident-looking answer about BXW must be escalated.
    result = diseases.assess(BXW_ANSWERS)
    assert result.referred is True
    assert "notified" in result.referral_reason.lower() or "officer" in result.referral_reason.lower()


def test_ambiguous_answers_are_referred_not_answered():
    result = diseases.assess({"inside": "not_cut", "roots": "not_seen", "pests": "unsure"})
    assert result.referred is True
    assert result.candidates == [] or result.confidence < settings.disease_referral_confidence


def test_contradictory_evidence_lowers_the_alternative():
    only_bud = diseases.assess({"bud": "normal", "inside": "clean", "leaves": "spots"})
    with_spots = diseases.assess(SIGATOKA_ANSWERS)
    assert with_spots.top.key == "black_sigatoka"
    assert (only_bud.top.score if only_bud.top else 0) <= with_spots.top.score + 0.35


def test_headline_is_worded_as_possible_not_definite():
    result = diseases.assess(BXW_ANSWERS)
    text = diseases.safe_headline(result).lower()
    assert "possible" in text
    assert "you have" not in text
    assert "diagnosis" not in text or "not" in text


def test_followup_question_is_unanswered_and_discriminative():
    result = diseases.assess(SIGATOKA_ANSWERS)
    nxt = result.next_question
    assert nxt is not None
    assert nxt["id"] not in SIGATOKA_ANSWERS
    # For a leaf-spot picture the bud/ooze question is what separates Sigatoka from wilt.
    assert nxt["id"] in {"bud", "inside", "pattern", "speed"}


def test_no_more_questions_when_all_answered():
    all_answers = {q["id"]: q["options"][0]["id"] for q in diseases.questions()}
    assert diseases.next_question(all_answers) is None


def test_advice_carries_prevention_and_immediate_action():
    result = diseases.assess(BXW_ANSWERS)
    advice = result.advice
    assert advice["immediate_actions"], "must say what to do next"
    assert advice["prevention"], "must say how to stop it recurring"
    assert advice["seek_help"]


def test_image_upload_is_never_presented_as_a_diagnosis_source():
    result = diseases.assess(BXW_ANSWERS, image_provided=True)
    assert "photograph" in result.referral_reason.lower()
    assert "not enabled" in result.referral_reason.lower()


def test_knowledge_base_covers_the_major_matooke_constraint_set():
    keys = {c["key"] for c in diseases.conditions()}
    assert {"bxw", "black_sigatoka", "bunchy_top", "nematode", "weevil"} <= keys
    for c in diseases.conditions():
        assert c["tags"], c["key"]
        assert c["prevention"], c["key"]
        assert c["references"], c["key"]
