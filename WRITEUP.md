# Technical Assessment Write-Up

**Candidate Name:** Muhammad Usman Khan  
**Reference:** MATACS-TH-2026-02  

---

## 1. AI vs. Rules

AI (LLM) is strictly limited to **unstructured text extraction**: parsing natural language from uploaded contractor proposal PDFs into standardized JSON schemas, with a verbatim source snippet for every field.

All compliance validation, mandatory pass/fail gate checks, and mathematical scoring are handled by a **deterministic Python rule engine**. We draw the line here because LLMs are unreliable at strict arithmetic, prone to variance, and vulnerable to prompt injection.

Qualitative criteria (e.g., technical approach) follow the same principle: the AI may *suggest* a rating only within a fixed, admin-defined rubric, and a human confirms it before it counts.

### Tender-Specific Configuration Workflow
1. **Configurable Criteria:** Each tender defines its own eligibility criteria, mandatory requirements, weights, thresholds, and rubrics, stored as a **versioned configuration** in the database.
2. **AI Fact Extraction:** The LLM extracts facts into structured JSON using a broad, versioned schema.
3. **Deterministic Rules Engine:** Python evaluates those facts against the configured rules, calculates scores, and applies pass/fail conditions. Price scoring formula, tie-breaking, and currency/tax normalization are defined in the configuration, not in code.
4. **Ranking:** Eligible proposals are ranked per the configured methodology, with score margins shown.

---

## 2. Consistency and Explainability

Results are **repeatable because extraction output is stored and scoring is deterministic**. Extraction runs at `temperature = 0` with strict JSON schema enforcement to minimize variance, but the guarantee comes from persisting the extracted JSON: re-evaluating the same stored data always yields the same scores, regardless of model version changes.

Explainability: every extracted parameter carries its exact source snippet and page reference. The reviewer UI shows a score breakdown (e.g., 25/25 price, 15/30 experience) with clickable, highlighted citations into the original PDF. Snippets are programmatically verified to exist in the document text, so a fabricated citation is caught automatically. Scanned documents go through OCR first, and low-confidence OCR is flagged.

---

## 3. Human in the Loop

A human evaluator is the final decision-maker, with checkpoints at three stages:

1. **Flagged Queue Resolution:** Incomplete or ambiguous bids (e.g., Proposal D's missing schedule) and low-confidence extractions are reviewed before scoring.
2. **Ineligibility Confirmation:** Any bid marked `ineligible` (e.g., Proposal B) is shown with its evidence and **requires human confirmation** before the bidder is excluded, because gate facts are interpretive and a wrong extraction must not silently eliminate a bidder.
3. **Award Confirmation:** The evaluator inspects the Bid Evaluation Report and approves the top-ranked recommendation. Near-ties are highlighted, and a sensitivity view shows whether the winner changes under small weight shifts, to reduce automation bias.

Roles are separated: the person who resolves flags cannot give final award approval. Every override, status change, or approval is logged with timestamp, user ID, and justification in an **append-only, hash-chained audit trail**.

---

## 4. Changing Criteria

Criteria and weights are **locked at bid opening**. Any later change requires approval and a logged reason, and creates a new configuration version. Every score records the version that produced it, so results are reproducible and defensible against challenge.

Because extracted JSON is stored separately from scores, changing weights or thresholds triggers an instant, cost-free recalculation with no LLM calls. If a new criterion needs a field the stored schema doesn't contain, only that field is re-extracted from the cached text.

### Rule Engine Configurability Example
- **Scenario 1 (Current Commercial Solar RFP):**
  Mandatory criteria: direct Electrical Licence held by the bidder, WSIB clearance, $5M liability insurance, budget ceiling $260,000 CAD, maximum 16-week timeline.
  - *Proposal A:* Passes all gates ($238k, 12 weeks, direct licence); Rank 1.
  - *Proposal B:* Proposed `ineligible` (licence subcontracted post-award); pending human confirmation.
  - *Proposal D:* `flagged` for a missing completion timeline.

- **Scenario 2 (Updated Criteria / Future RFP):**
  If the team requires $\ge 10$ past commercial projects and rewards 12-year workmanship warranties:
  - *Proposal A* receives lower warranty marks (10 years).
  - *Proposal E* rises to Rank 1 (12-year warranty, strong monitoring). The same stored JSON is re-scored instantly under the new configuration version.

---

## 5. Risks and Safeguards

- **Prompt Injection:** Adversarial text (e.g., Proposal C's *Appendix C* requesting top rank) is **contained**: the LLM only extracts and cannot influence scoring or ranking directly. Because injected text could still distort extracted facts, we also scan for instruction-like text and flag it, verify snippets against the source, and require human confirmation of gate-deciding fields.
- **Hallucinations & False Extractions:** Mitigated by verbatim, programmatically verified snippets and rapid human verification on the dashboard.
- **Missing / Ambiguous Specs:** Bids lacking vital metrics route to `status: "flagged"` with `score: null` rather than unsafe assumptions.
- **Procurement Integrity:** Criteria locking, versioned configs, role separation, and the tamper-evident audit log guard against post-hoc manipulation.
- **Confidentiality:** Bid documents are sent to the LLM under a no-retention, no-training agreement (or a self-hosted model), and sensitive fields can be redacted before extraction.
- **API Cost & Latency:** Extracted JSON snapshots are cached, so extraction runs once per document upload.