"""5.1 Smart farming / farm doctor: guided symptom reasoning.

The proposal states the prototype should use "a guided symptom questionnaire
and a curated knowledge base" while a validated image dataset is arranged,
that results must be labelled as a *possible* diagnosis, and that
low-confidence cases must be referred to a human. All three constraints are
implemented here rather than bolted on in the UI.

Scoring (log-free, auditable, deliberately simple):

    score = 0.55 * coverage + 0.35 * precision - 0.45 * contradiction - 0.20 * denial
    coverage      = fraction of the condition's symptom tags the farmer reported
    precision     = fraction of the farmer's reports this condition explains
    contradiction = fraction of the condition's 'against' tags the farmer reported
    denial        = fraction of the condition's tags the farmer explicitly ruled out

    confidence = 0.6 * best + 0.4 * (best - runner_up)      # capped at 0.95

Follow-up questions are chosen by simulated information gain: the question
whose answers most change the gap between the leading candidates is asked
next. Image recognition is not part of this build (see ml/README.md).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import settings

KNOWLEDGE = Path(__file__).parent / "knowledge" / "matooke_diseases.json"

# Never present AI advice as certain.
CONFIDENCE_CAP = 0.95


@lru_cache(maxsize=1)
def kb() -> dict:
    return json.loads(KNOWLEDGE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def conditions() -> tuple[dict, ...]:
    return tuple(kb()["conditions"])


@lru_cache(maxsize=1)
def questions() -> tuple[dict, ...]:
    return tuple(kb()["questions"])


def condition(key: str) -> dict:
    for c in conditions():
        if c["key"] == key:
            return c
    raise KeyError(key)


@dataclass
class Candidate:
    key: str
    name: str
    type: str
    severity: str
    score: float
    confidence: float
    matched: list[str] = field(default_factory=list)
    unexplained: list[str] = field(default_factory=list)
    contradicted: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class Assessment:
    answers: dict[str, str]
    candidates: list[Candidate]
    observed_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    referred: bool = False
    referral_reason: str = ""
    needs_more_answers: bool = False
    next_question: dict | None = None
    unanswered: list[str] = field(default_factory=list)
    disclaimer: str = ""
    advice: dict | None = None

    @property
    def top(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def _tags_from(answers: dict[str, str]) -> tuple[set[str], set[str]]:
    """Return (observed tags, tags argued against by the chosen answers)."""
    observed: set[str] = set()
    contra: set[str] = set()
    by_id = {q["id"]: q for q in questions()}
    for qid, opt_id in answers.items():
        q = by_id.get(qid)
        if not q:
            continue
        for opt in q["options"]:
            if opt["id"] == opt_id:
                observed |= set(opt.get("tags", []))
                contra |= set(opt.get("contra", []))
    return observed, contra


def _score_all(answers: dict[str, str]) -> list[Candidate]:
    observed, denials = _tags_from(answers)
    out: list[Candidate] = []
    for c in conditions():
        tags = set(c["tags"])
        ctags = set(c.get("contra_tags", []))
        matched = sorted(observed & tags)
        unexplained = sorted(tags - observed)
        contradicted = sorted(ctags & observed)
        # Tags the farmer explicitly reported as absent: strong evidence against.
        denied = sorted(denials & tags)
        coverage = len(matched) / len(tags) if tags else 0.0
        precision = len(matched) / len(observed) if observed else 0.0
        contradiction = len(contradicted) / len(ctags) if ctags else 0.0
        denial = len(denied) / len(tags) if tags else 0.0
        score = 0.55 * coverage + 0.35 * precision - 0.45 * contradiction - 0.20 * denial
        out.append((score, coverage, matched, unexplained, contradicted, denied, c))

    scored = [c for c in out if c[0] > 0.0]
    scored.sort(key=lambda t: (-t[0], t[6]["name"]))
    second = scored[1][0] if len(scored) > 1 else 0.0

    cands: list[Candidate] = []
    for score, _cov, matched, unexplained, contradicted, denied, c in scored[:4]:
        conf = 0.6 * score + 0.4 * (score - second)
        cands.append(
            Candidate(
                key=c["key"],
                name=c["name"],
                type=c["type"],
                severity=c["severity"],
                score=round(score, 3),
                confidence=round(max(0.0, min(conf, CONFIDENCE_CAP)), 3),
                matched=matched,
                unexplained=unexplained[:6],
                contradicted=contradicted,
                denied=denied,
                summary=c["summary"],
            )
        )
    return cands


def _discriminative_value(q: dict, answers: dict[str, str]) -> float:
    """Spread of best-minus-runner-up across this question's possible answers."""
    gaps: list[float] = []
    for opt in q["options"]:
        trial = dict(answers)
        trial[q["id"]] = opt["id"]
        cands = _score_all(trial)
        if not cands:
            gaps.append(0.0)
            continue
        best = cands[0].score
        second = cands[1].score if len(cands) > 1 else 0.0
        gaps.append(best - second)
    if len(gaps) < 2:
        return 0.0
    hi, lo = max(gaps), min(gaps)
    return hi - lo


def next_question(answers: dict[str, str]) -> dict | None:
    """Pick the unanswered question that best separates the leading candidates."""
    todo = [q for q in questions() if q["id"] not in answers]
    if not todo:
        return None
    ranked = sorted(todo, key=lambda q: (-_discriminative_value(q, answers), q["id"]))
    best = ranked[0]
    if _discriminative_value(best, answers) <= 0.0:
        # Nothing left that could change the ranking: stop rather than interrogate.
        return None
    return {
        "id": best["id"],
        "text": best["text"],
        "options": [{"id": o["id"], "label": o["label"]} for o in best["options"]],
        "why": "Asking this usually separates the most likely explanations.",
    }


def advice_for(cand: Candidate) -> dict:
    c = condition(cand.key)
    return {
        "key": c["key"],
        "name": c["name"],
        "type": c["type"],
        "severity": c["severity"],
        "causal_agent": c.get("causal_agent"),
        "summary": c["summary"],
        "immediate_actions": c["immediate_actions"],
        "prevention": c["prevention"],
        "spread": c.get("spread", []),
        "favouring_conditions": c.get("favouring_conditions", []),
        "explain_what_may_be_wrong": c.get("explain_what_may_be_wrong", []),
        "seek_help": c.get("seek_help"),
        "quarantine_relevant": c.get("quarantine_relevant", False),
        "references": c.get("references", []),
    }


def assess(answers: dict[str, str], *, image_provided: bool = False) -> Assessment:
    cands = _score_all(answers)
    top_conf = cands[0].confidence if cands else 0.0
    unresolved = [q["id"] for q in questions() if q["id"] not in answers]

    a = Assessment(
        answers=answers,
        candidates=cands,
        observed_tags=sorted(_tags_from(answers)[0]),
        confidence=top_conf,
        unanswered=unresolved,
        disclaimer=kb()["disclaimer"],
    )

    reasons: list[str] = []
    if not cands:
        reasons.append(
            "The answers do not match any condition in the knowledge base well enough to rank one."
        )
    else:
        if cands[0].confidence < settings.disease_referral_confidence:
            reasons.append(
                f"Best match is only {cands[0].confidence * 100:.0f} % confident, "
                f"below the {settings.disease_referral_confidence * 100:.0f} % floor."
            )
        if len(cands) > 1 and (cands[0].score - cands[1].score) < 0.08:
            reasons.append(
                f"'{cands[0].name}' and '{cands[1].name}' are too close to separate from symptoms alone."
            )
        if cands[0].key in {"bxw", "bunchy_top", "moko"}:
            # Quarantine-relevant, community-level response: always involve a person.
            reasons.append(
                f"Suspected {cands[0].name} is a notified, community-level problem, so a "
                "district officer must see it regardless of confidence."
            )
    if image_provided:
        reasons.append(
            "A photograph was attached, but image recognition is not enabled in this build; "
            "the ranking is from your answers only."
        )

    a.referred = bool(reasons)
    a.referral_reason = " ".join(reasons)

    if cands and not a.referred and a.confidence < 0.85 and unresolved:
        a.needs_more_answers = True
        a.next_question = next_question(answers)
    elif unresolved:
        # Still offer the next most useful question so the flow is guided.
        a.next_question = next_question(answers)
        a.needs_more_answers = bool(a.next_question) and a.confidence < 0.85

    if cands:
        a.advice = advice_for(cands[0])
    return a


def to_dict(a: Assessment) -> dict:
    d = asdict(a)
    return d


def safe_headline(a: Assessment) -> str:
    """Wording rule: 'possible', never 'you have'."""
    if not a.candidates:
        return "No clear match from the answers given"
    top = a.candidates[0]
    if a.referred:
        return f"Possible {top.name.lower()} - needs a person to confirm"
    return f"Possible {top.name.lower()} (about {top.confidence * 100:.0f} % match)"
