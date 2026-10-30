#!/usr/bin/env python3
"""
Prototype: run the extraction prompt on sample proposals, verify snippets,
score with a deterministic rule engine, and write ranking.json.

Setup:
    pip install anthropic pypdf
    export ANTHROPIC_API_KEY=...

Usage:
    python run_triage.py samples/              # folder of .txt or .pdf proposals
    python run_triage.py samples/ --refresh    # force re-calling the LLM
    python run_triage.py samples/ --rescore    # re-score cached JSON only (no LLM calls)

Design (matches WRITEUP.md):
  - LLM: extraction only (temperature 0, JSON, verbatim snippets).
  - Code: snippet verification, gate checks, scoring, ranking.
  - Extracted JSON is cached in out/extracted/, so changing CONFIG and
    running with --rescore re-scores instantly with zero LLM cost.
"""
import argparse
import json
import pathlib
import re
import sys

MODEL = "claude-sonnet-5-5"          # swap for any model/provider in call_llm()
PROMPTS_FILE = "prompts.md"
OUT_DIR = pathlib.Path("out")
CONFIG_VERSION = "solar-rfp-v1"

# ---- Tender configuration (example values: adjust to your RFP) -------------
CONFIG = {
    "gates": {
        "min_liability_insurance_cad": 5_000_000,
        "max_price_cad": 260_000,
        "max_weeks": 16,
    },
    # weights sum to 100
    "weights": {"price": 30, "experience": 25, "timeline": 15,
                "warranty": 15, "monitoring": 10, "admin": 5},
    "experience_full_marks_at": 10,   # projects for full experience marks
    "min_weeks_full_marks": 8,        # timeline at/below this = full marks
    "workmanship_full_years": 12,
    "panel_full_years": 25,
    "monitoring_full_months": 24,
}

FIELDS = [
    "contractor_name", "holds_direct_ontario_license", "license_number",
    "wsib_and_insurance_confirmed", "liability_insurance_amount_cad",
    "relevant_experience_count_over_100kw", "total_price_cad",
    "completion_timeline_weeks", "panel_warranty_years",
    "workmanship_warranty_years", "named_project_lead_present",
    "crew_size_specified", "safety_plan_included",
    "performance_monitoring_months",
]
# Fields whose absence/failed verification routes a bid to "flagged"
REQUIRED = ["holds_direct_ontario_license", "wsib_and_insurance_confirmed",
            "liability_insurance_amount_cad", "total_price_cad",
            "completion_timeline_weeks"]


# ---- Input handling --------------------------------------------------------
def load_text(path: pathlib.Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        pages = [p.extract_text() or "" for p in PdfReader(str(path)).pages]
        return "\n".join(f"[[PAGE {i}]]\n{t}" for i, t in enumerate(pages, 1))
    return path.read_text(encoding="utf-8")


def load_prompt_template() -> str:
    md = pathlib.Path(PROMPTS_FILE).read_text(encoding="utf-8")
    m = re.search(r"```\n(SYSTEM INSTRUCTION:.*?)```", md, re.S)
    if not m:
        sys.exit(f"Could not find the primary prompt block in {PROMPTS_FILE}")
    return m.group(1)


# ---- LLM call (the only AI step) -------------------------------------------
def call_llm(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    msg = client.messages.create(
        model=MODEL, max_tokens=2500, temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def parse_json(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    return json.loads(raw)


def extract(text: str, template: str) -> dict:
    prompt = template.replace("{{proposal_text}}", text)
    for attempt in (1, 2):
        try:
            return parse_json(call_llm(prompt))
        except (json.JSONDecodeError, ValueError):
            if attempt == 2:
                return {"_extraction_failed": True}


# ---- Verification (code, not AI) -------------------------------------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[\[PAGE \d+\]\]", " ", s)).strip().lower()


def verify(facts: dict, source_text: str) -> list:
    """Null any field whose snippet is not found verbatim in the source."""
    src, problems = norm(source_text), []
    for f in FIELDS:
        cell = facts.get(f)
        if not isinstance(cell, dict) or cell.get("value") is None:
            continue
        snip = cell.get("snippet")
        if not snip or norm(snip) not in src:
            problems.append(f)
            cell["value"] = None
    return problems


# ---- Deterministic rule engine ---------------------------------------------
def val(facts, key):
    cell = facts.get(key)
    return cell.get("value") if isinstance(cell, dict) else None


def clamp(x):
    return max(0.0, min(1.0, x))


def evaluate(facts: dict, unverified: list) -> dict:
    g = CONFIG["gates"]
    flags = []
    if facts.get("suspicious_instruction_text"):
        flags.append("suspicious_instruction_text")
    if unverified:
        flags.append("unverified_snippet:" + ",".join(unverified))

    missing = [k for k in REQUIRED if val(facts, k) is None]
    if facts.get("_extraction_failed") or missing:
        return {"status": "flagged", "flags": flags + ["missing_required_field"],
                "reason": "Missing or unverifiable required data: "
                          + (", ".join(missing) or "extraction failed")
                          + ". Requires human clarification before scoring."}

    fails = []
    if val(facts, "holds_direct_ontario_license") is not True:
        fails.append("electrical licence not held directly by bidder")
    if val(facts, "wsib_and_insurance_confirmed") is not True:
        fails.append("WSIB/insurance not confirmed")
    if val(facts, "liability_insurance_amount_cad") < g["min_liability_insurance_cad"]:
        fails.append("liability insurance below minimum")
    if val(facts, "total_price_cad") > g["max_price_cad"]:
        fails.append("price above budget ceiling")
    if val(facts, "completion_timeline_weeks") > g["max_weeks"]:
        fails.append("timeline above maximum")
    if fails:
        return {"status": "ineligible", "flags": flags + ["failed_mandatory_gate"],
                "reason": "Fails mandatory gate(s): " + "; ".join(fails)
                          + ". Exclusion proposed, pending human confirmation."}
    return {"status": "eligible", "flags": flags, "reason": ""}


def partial_score(facts: dict) -> float:
    """Everything except price (price is relative to the field)."""
    w, c, g = CONFIG["weights"], CONFIG, CONFIG["gates"]
    n = lambda k: val(facts, k) or 0
    exp = clamp(n("relevant_experience_count_over_100kw") / c["experience_full_marks_at"])
    span = g["max_weeks"] - c["min_weeks_full_marks"]
    tl = clamp((g["max_weeks"] - n("completion_timeline_weeks")) / span)
    warr = (0.67 * clamp(n("workmanship_warranty_years") / c["workmanship_full_years"])
            + 0.33 * clamp(n("panel_warranty_years") / c["panel_full_years"]))
    mon = clamp(n("performance_monitoring_months") / c["monitoring_full_months"])
    adm = (0.4 * bool(val(facts, "named_project_lead_present"))
           + 0.4 * bool(val(facts, "safety_plan_included"))
           + 0.2 * bool(val(facts, "crew_size_specified")))
    return (w["experience"] * exp + w["timeline"] * tl + w["warranty"] * warr
            + w["monitoring"] * mon + w["admin"] * adm)


def rank(results: dict) -> list:
    eligible = {p: r for p, r in results.items() if r["status"] == "eligible"}
    if eligible:
        best_price = min(val(r["facts"], "total_price_cad") for r in eligible.values())
    for p, r in eligible.items():
        price_pts = CONFIG["weights"]["price"] * best_price / val(r["facts"], "total_price_cad")
        r["score"] = round(price_pts + partial_score(r["facts"]), 1)
        r["status"] = "ranked"
        r["reason"] = "Passes all mandatory gates; deterministic weighted score."
    ordered = sorted((p for p, r in results.items() if r["status"] == "ranked"),
                     key=lambda p: -results[p]["score"])
    for i, p in enumerate(ordered, 1):
        results[p]["rank"] = i

    rows = []
    for p in sorted(results, key=lambda p: (results[p].get("rank") or 99, p)):
        r = results[p]
        rows.append({
            "proposal": p, "rank": r.get("rank"), "status": r["status"],
            "score": r.get("score"), "config_version": CONFIG_VERSION,
            "flags": r["flags"],
            "requires_human_confirmation": r["status"] in ("flagged", "ineligible"),
            "reason": r["reason"],
        })
    return rows


# ---- Main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", help="folder with .txt/.pdf proposals")
    ap.add_argument("--refresh", action="store_true", help="re-call the LLM")
    ap.add_argument("--rescore", action="store_true", help="use cache only, no LLM")
    args = ap.parse_args()

    cache = OUT_DIR / "extracted"
    cache.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in pathlib.Path(args.samples).iterdir()
                   if p.suffix.lower() in (".txt", ".pdf"))
    if not files:
        sys.exit("No .txt or .pdf proposals found.")
    template = None if args.rescore else load_prompt_template()

    results = {}
    for f in files:
        pid = f.stem
        cached = cache / f"{pid}.json"
        text = load_text(f)
        if cached.exists() and not args.refresh:
            facts = json.loads(cached.read_text())
            print(f"[cache] {pid}")
        elif args.rescore:
            print(f"[skip]  {pid}: no cached extraction")
            continue
        else:
            print(f"[LLM]   {pid}")
            facts = extract(text, template)
            cached.write_text(json.dumps(facts, indent=2))
        unverified = verify(facts, text)
        results[pid] = {"facts": facts, **evaluate(facts, unverified)}

    rows = rank(results)
    pathlib.Path("ranking.json").write_text(json.dumps(rows, indent=2))
    print(f"\n{'Proposal':<12}{'Rank':<6}{'Status':<12}{'Score':<8}Flags")
    for r in rows:
        print(f"{r['proposal']:<12}{str(r['rank']):<6}{r['status']:<12}"
              f"{str(r['score']):<8}{','.join(r['flags'])}")
    print("\nWrote ranking.json (extracted JSON cached in out/extracted/)")


if __name__ == "__main__":
    main()
