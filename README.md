# Candidate Assessment Submission: AI Proposal Triage Design

**Candidate Name:** Muhammad Usman Khan  
**Assessment Reference:** MATACS-TH-2026-02  
**Expected Effort:** ~60 minutes  
**Actual Time Spent:** ~55 minutes  

---

## Repository Structure & File Links

- [WRITEUP.md](./WRITEUP.md): Complete answers to the five core design questions (AI vs. Rules, Consistency, Human-in-the-Loop, Changing Criteria, and Risks/Safeguards).
- [PROMPTS.md](./PROMPTS.md): Proposed AI extraction system prompt, per-field citation schema, and injection guardrails.
- [ranking.json](./ranking.json): Evaluated and scored ranking output for Proposals A through E.
- [diagram/process_flow.png](./diagram/process_flow.png) (editable source: [process_flow.drawio](./diagram/process_flow.drawio)): Architecture flow from PDF upload to ranked output.

> **Scope note:** This submission is a design deliverable. Features described in WRITEUP.md such as the append-only audit trail, OCR handling, and field redaction are specified, not implemented.

---

## Use of AI Tools & Refinement Disclosure

I utilized AI tools (ChatGPT / Claude) as an architectural sparring partner to brainstorm failure modes, edge cases, and extraction schema guardrails.

### Overruling & Correcting the AI Output
During initial prompt design, the AI attempted to calculate the 0–100 weighted scores directly inside its LLM completion output. I explicitly overruled this approach and instructed the AI to restrict its role solely to structured JSON fact extraction, delegating all scoring math and pass/fail gate checks to a deterministic Python rule engine. This removed calculation variance, makes results repeatable (extractions are stored and scoring is deterministic), and keeps injected text from directly influencing scores or rankings.

### Disagreements & Design Refinements
Throughout the architectural design process, I refined the system boundaries based on real-world procurement workflows:
1. **Data Retention over Early Discarding:** Rather than immediately discarding bids that fail standard threshold criteria, the design retains all extracted JSON facts and source text snippets. This guarantees full auditability, supports human verification, and powers the flagging queue for incomplete proposals (e.g., Proposal D).
2. **Human Confirmation of Exclusions:** Because pass/fail gate facts (e.g., licence held directly vs. subcontracted) are interpretive and extracted by an LLM, any `ineligible` status is shown with its evidence and requires human confirmation before a bidder is excluded.
3. **Procurement Integrity:** Evaluation criteria are versioned and locked at bid opening. Later changes need approval and a logged reason, and every score records the configuration version that produced it.
4. **Procurement Standards Alignment:** The workflow incorporates multi-stage tender evaluation principles (separating technical qualification from financial evaluation) to ensure the system reflects real-world conditions of contract rather than over-simplified AI assumptions.
