"""Rule tiers (user, 2026-11-24: fixed rules must not stop a figure the user asks for, yet no rules lets errors in).

1. **Invariants** — correctness: the figure says what the paper says, it can be read, it prints. Code-enforced and never
   waived: the facts gate, coverage, overlap, text that fits and keeps its contrast, no line through anything, the
   venue's text floor, the page, the authors' module names.
2. **Defaults** — design priors with a reason (wide overviews, few colours, light fills, stages as panels, losses in
   their stream, …). Every other lint code and the plan validator's design checks. A plan may deviate from one with
   a reason and evidence (`plan.deviations`): a knowledge-base card or selected reference that does it, the author's
   own figure (`user-draft`), or the user's own instruction. A deviated finding is reported, not fixed.
3. **Taste** — composition, richness, emphasis: not rules at all; judged by the critic's reader test and the user.
"""
from __future__ import annotations

# Tier 1: lint / gate codes no plan can deviate from (a test keeps this in step with the codes the engine emits).
INVARIANTS = frozenset({
    # faithful: the figure states what the paper states, under the authors' names
    "fact-missing", "fact-reversed", "fact-unknown-id", "fact-out-of-scope", "facts-all-omitted",
    "coverage-missing", "coverage-extra", "proposed-name-missing", "proposed-mismatch",
    # legible: nothing hides text or another element
    "overlap", "child-outside-parent", "text-overflow", "text-contrast", "badge-overlaps-text", "stub-overlap",
    "edge-through-node", "edge-through-label", "edge-through-title", "edge-through-legend", "edge-through-annotation",
    "edge-overlap", "bracket-coverage", "callout-missing",
    # printable
    "min-font", "page-overflow", "png-mismatch",
})

# Tier 2 design checks of the plan validator (artifacts._figure_plan): id -> what the default asks.
PLAN_RULES = {
    "plan:paradigm-concept": "one concept adapts the paradigm's source figure when the scout selected one",
    "plan:unit-enclosed": "a unit is an enclosed region (frame box or dashed)",
    "plan:unit-losses": "a unit's loss nodes sit inside it",
    "plan:stages-partition": "a text that separates stages / streams gets one enclosed unit each",
    "plan:loss-collapse": "no single box stands for several of a stream's method-defining losses",
    "plan:losses-per-stream": "every method-defining loss a stream optimises is drawn in that stream's unit",
    "plan:supervision": "two or more contrastive objectives get a supervision structure (what is a positive)",
    "plan:existing-figure": "a module the text shows in a figure of its own is one box here",
    "plan:merge-consistency": "components merged in one place are not drawn apart elsewhere",
    "plan:depth-inline": "a module drawn inline on the main line has at most 3 parts (else a box with an inset or its own figure)",
    "plan:picked-reference": "the chosen concept adapts a reference the user picked at the `references` confirmation",
}

EVIDENCE_KINDS = ("card", "reference", "user-draft", "user")
MIN_WHY_WORDS = 6


def tier(code: str) -> str:
    if code in INVARIANTS:
        return "invariant"
    return "default"


def deviations_of(plan: dict | None) -> dict:
    """rule -> deviation, for well-formed entries (the validator reports the malformed ones)."""
    out = {}
    for d in (plan or {}).get("deviations") or []:
        if isinstance(d, dict) and isinstance(d.get("rule"), str) and d.get("why"):
            out[d["rule"]] = d
    return out


def deviation_problems(plan: dict, known_cards=(), known_refs=(), has_user_draft=False, key=lambda s: s) -> list[str]:
    """A deviation needs a tier-2 rule, a reason and evidence that exists — flexibility, bounded by something real."""
    probs = []
    for i, d in enumerate(plan.get("deviations") or []):
        rule = d.get("rule", "")
        if rule in INVARIANTS:
            probs.append(f"deviations[{i}]: '{rule}' is an invariant (faithful, legible, printable) — it cannot be "
                         "deviated from; fix the figure instead")
            continue
        if rule.startswith("plan:") and rule not in PLAN_RULES:
            probs.append(f"deviations[{i}]: unknown plan rule '{rule}' (known: {', '.join(sorted(PLAN_RULES))})")
        if len(str(d.get("why", "")).split()) < MIN_WHY_WORDS:
            probs.append(f"deviations[{i}] ({rule}): say why in a sentence — what this figure gains by it")
        ev = d.get("evidence") or {}
        kind, ref = ev.get("kind"), str(ev.get("ref") or "").strip()
        if kind not in EVIDENCE_KINDS:
            probs.append(f"deviations[{i}] ({rule}): evidence.kind must be one of {', '.join(EVIDENCE_KINDS)}")
        elif kind == "card" and ref not in known_cards:
            probs.append(f"deviations[{i}] ({rule}): evidence card '{ref}' is not in the knowledge base or this run")
        elif kind == "reference" and key(ref) not in known_refs:
            probs.append(f"deviations[{i}] ({rule}): evidence reference '{ref}' is not a selected reference")
        elif kind == "user-draft" and not has_user_draft:
            probs.append(f"deviations[{i}] ({rule}): evidence user-draft, but RUN/inputs/user-draft.* is missing")
        elif kind == "user" and len(ref.split()) < 3:
            probs.append(f"deviations[{i}] ({rule}): evidence user — quote what the user asked for")
    return probs


def apply_deviations(findings: list, plan: dict | None) -> list:
    """Findings of a deviated tier-2 rule are reported as info, with the reason; invariants are never touched."""
    devs = deviations_of(plan)
    if not devs:
        return findings
    from .lint import Finding
    out = []
    for f in findings:
        d = devs.get(f.code)
        if d is not None and f.code not in INVARIANTS and f.severity in ("warn", "error"):
            out.append(Finding(f.code, "info", f.ids, f"deviated ({d['why']}) — {f.message}", f.provisional))
        else:
            out.append(f)
    return out
