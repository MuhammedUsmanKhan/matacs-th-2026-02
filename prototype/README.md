# Prototype Testing Instructions: `run_triage.py`

This optional prototype script (`run_triage.py`) automates the full proposal evaluation pipeline—from reading proposal documents to LLM fact extraction, hallucination guardrail verification, deterministic scoring, and generating `ranking.json`.

---

## Environment Setup

### 1. Prerequisites
Ensure you have Python 3.9+ installed along with the required dependencies:

```bash
pip install anthropic pypdf
```

### 2. Configure API Credentials
Set your Anthropic API key as an environment variable (never commit your actual API key to Git):

```bash
# On Linux/macOS
export ANTHROPIC_API_KEY="your-anthropic-api-key-here"

# On Windows (Command Prompt)
set ANTHROPIC_API_KEY="your-anthropic-api-key-here"

# On Windows (PowerShell)
$env:ANTHROPIC_API_KEY="your-anthropic-api-key-here"
```

If using an environment file, copy `.env.example` to `.env` and populate your key.

---

## Directory Setup & Sample Preparation

1. Create a `samples/` directory at the root of the repository:
   ```bash
   mkdir samples
   ```
2. Place the proposal files in the `samples/` folder using the proposal letter as the filename (e.g., `A.txt`, `B.pdf`, `C.txt`, `D.txt`, `E.pdf`).
   > **Note:** Filenames directly map to the proposal ID in `ranking.json`.

---

## Execution Workflow

Run the prototype script pointing to your samples directory:

```bash
python run_triage.py samples/
```

### What Happens During Execution:
1. **Document Ingestion:** Reads each `.txt` or `.pdf` file in `samples/`. Automatically inserts `[[PAGE n]]` markers for PDF files to preserve auditability.
2. **Structured LLM Extraction:** Loads system instructions from `PROMPTS.md` and invokes Claude at `temperature = 0` to parse key parameters and verbatim source citations.
3. **Verbatim Hallucination Guardrail:** Verifies that extracted snippet citations exist verbatim within the source document text. If a citation check fails, the associated field is safely nulled out.
4. **Deterministic Rule Engine:** Evaluates mandatory pass/fail gates and calculates 0–100 weighted technical/financial scores using python logic.
5. **Output Generation:** 
   - Caches raw extracted JSON payloads into `out/extracted/` for instant re-scoring and auditability.
   - Outputs the final `ranking.json` to the root directory matching the required assessment layout.

---

## Expected Output Verification

After execution, verify the generated `ranking.json` file against expected outcomes:
- **Proposal A:** Ranked #1 (`status: "ranked"`)
- **Proposal E:** Ranked #2 (`status: "ranked"`)
- **Proposal C:** Ranked #3 (`status: "ranked"`, prompt injection neutralized)
- **Proposal D:** Flagged (`status: "flagged"`, missing schedule)
- **Proposal B:** Ineligible (`status: "ineligible"`, subcontracted licence)