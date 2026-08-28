# AI Customer Complaint & Case Processing System

A batch-oriented GenAI workflow that ingests business complaint documents in
multiple formats, extracts structured information with an LLM, and generates a
customer response email and an internal management summary for every case.

Built for the **IIT Patna / USDC GenAI Development Program — Final Evaluation,
Project 1: AI-Powered Document Processing & Business Workflow.**

---

## Problem statement

A customer support team receives complaint records as a mix of `.txt`, `.pdf` and
`.docx` files. Someone has to read each one, pull the key facts into a system of
record, draft a reply to the customer, and write a short internal note so a
manager can triage the queue. It is slow, inconsistent between agents, and it
does not scale with volume.

## Solution overview

Point the application at a folder. For every document it runs three distinct
LLM tasks and writes four kinds of output.

| # | Task | Input | Output |
| --- | --- | --- | --- |
| 1 | **Structured extraction** | Document text | Validated `ExtractedComplaint` — customer, contact details, category, issue, resolution, escalation flag, status, priority, sentiment |
| 2 | **Customer response email** | Validated record (+ document for tone) | Professional, sendable reply |
| 3 | **Internal case summary** | Validated record (+ document for detail) | Overview, key issue, action taken, current status, recommended next action |

Results are consolidated into `final_report.csv`, one row per document.

**Runs with no API key.** `python run.py --provider mock` executes the entire
pipeline against a deterministic rule-based provider, so the project can be
evaluated end to end at zero cost.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py --provider mock
```

That processes the ten sample documents in `data/` and writes everything to
`output/`. No API key, no network, no spend.

To run it against a real model:

```bash
cp .env.example .env        # then add your key to .env
python run.py               # uses LLM_PROVIDER from .env (default: openai)
```

---

## Architecture

```
                    data/  (.txt · .md · .pdf · .docx)
                              │
                    ┌─────────▼──────────┐
                    │  Ingestion layer   │  discover → dispatch by extension
                    │  Text/Pdf/Docx     │  → extract → normalise
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Batch runner     │  ThreadPoolExecutor(BATCH_WORKERS)
                    └─────────┬──────────┘
                              │  per document
                    ┌─────────▼──────────────────────────────┐
                    │  [1] Structured Extraction             │
                    │      → Pydantic validation             │
                    └─────────┬──────────────────────────────┘
                              │ validated record
                     ┌────────┴────────┐        (run concurrently)
                     ▼                 ▼
            ┌────────────────┐ ┌────────────────┐
            │ [2] Customer   │ │ [3] Internal   │
            │     Email      │ │     Summary    │
            └────────┬───────┘ └───────┬────────┘
                     └────────┬────────┘
                              ▼
     output/  structured_data/ · customer_emails/ · case_summaries/ · final_report.csv

     All three tasks call:  LLMClient.generate_structured(schema)
                            └── OpenAI │ Gemini │ Mock (offline)
```

Full diagrams (Mermaid), layer table, data model, concurrency model and failure
matrix: **[`docs/architecture.md`](docs/architecture.md)**.

### Why the workflow is split into three tasks

One prompt returning everything would be cheaper, but it degrades on long
documents, makes validation all-or-nothing, and cannot be parallelised. Three
focused tasks keep each prompt short, let a single failure be contained, and
allow tasks 2 and 3 to run side by side.

Tasks 2 and 3 read the **validated** extraction, not the raw document. By then
placeholders are `None` and malformed contact details have been dropped, so a
hallucinated email address cannot reach a customer-facing artefact.

---

## Technology stack

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.10+ | Required by the brief |
| Structured output | **Pydantic v2** as a native response schema | Provider-enforced schema; no JSON-fence parsing |
| LLM providers | **OpenAI**, **Google Gemini**, offline mock | Swappable behind one interface |
| PDF / DOCX | `pypdf`, `python-docx` | Pure-Python, no system dependencies |
| Config | `pydantic-settings` + `.env` | No hard-coded values or secrets |
| Retries | `tenacity` | Exponential backoff on transient errors |
| Concurrency | `ThreadPoolExecutor` | Tasks are network-bound I/O |
| Console / logging | `rich` + stdlib `logging` | Readable run, full audit trail on disk |
| Tests | `pytest` | 79 tests, no network required |

---

## Project structure

```
ai-complaint-processor/
├── run.py                        # entry point
├── requirements.txt
├── .env.example                  # config template (never commit .env)
├── pyproject.toml
│
├── data/                         # 10 sample documents (4 formats + 2 edge cases)
├── sample_output/                # committed snapshot of a real run
├── docs/architecture.md          # diagrams and design rationale
├── scripts/generate_sample_data.py
│
├── src/complaint_processor/
│   ├── cli.py                    # argument parsing, exit codes
│   ├── config.py                 # Settings (env-driven)
│   ├── models.py                 # ALL Pydantic schemas + validators
│   ├── exceptions.py             # error hierarchy
│   ├── logging_setup.py
│   │
│   ├── ingestion/loaders.py      # .txt .md .pdf .docx
│   ├── prompts/                  # extraction · response_email · case_summary
│   ├── llm/                      # base · factory · openai · gemini · mock
│   ├── tasks/                    # one module per AI task
│   │
│   ├── workflow.py               # per-document orchestration
│   ├── batch.py                  # concurrency across documents
│   ├── persistence.py            # per-case output files
│   └── reporting.py              # final_report.csv, manifest, console summary
│
└── tests/                        # 79 tests
```

---

## Setup

**1. Environment**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Configuration** — copy the template and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai` | `openai` \| `gemini` \| `mock` |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `GEMINI_API_KEY` | — | Required when provider is `gemini` |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model name |
| `LLM_TEMPERATURE` | `0.2` | Low — extraction should be reproducible |
| `LLM_MAX_RETRIES` | `3` | Retry attempts on transient errors |
| `LLM_TIMEOUT_SECONDS` | `90` | Per-call timeout |
| `INPUT_DIR` / `OUTPUT_DIR` | `data` / `output` | Paths |
| `BATCH_WORKERS` | `4` | Documents processed concurrently |
| `TASK_MODE` | `parallel` | `parallel` \| `sequential` |
| `MAX_DOCUMENT_CHARS` | `20000` | Truncation limit |
| `LOG_LEVEL` | `INFO` | Console verbosity |

`.env` is git-ignored. **API keys are never committed.**

---

## How to run

```bash
python run.py                          # process ./data with the configured provider
python run.py --provider mock          # offline demo — no API key needed
python run.py --provider gemini        # use Gemini instead of OpenAI
python run.py --task-mode sequential   # disable intra-document parallelism
python run.py --limit 2                # process only the first 2 documents
python run.py --input-dir /path/to/docs --output-dir /tmp/results
python run.py --log-level DEBUG        # verbose console output
python run.py --help
```

Every flag overrides the corresponding `.env` value. Exit codes: `0` all
succeeded, `1` some partial or failed, `2` configuration error, `3` fatal.

**Tests:**

```bash
pytest
```

---

## Sample input

`data/` holds ten documents chosen to exercise the pipeline, not just to fill it:

| File | Format | Scenario | Exercises |
| --- | --- | --- | --- |
| `complaint_001.txt` | txt | Duplicate billing, refunded | Resolved status, attachments |
| `complaint_002.pdf` | pdf | Delivery delay, very angry | Escalation, Critical priority |
| `complaint_003.docx` | docx | Faulty appliance under warranty | **Table-based** DOCX form |
| `complaint_004.txt` | txt | Cannot log in | Open case, **missing phone** |
| `complaint_005.pdf` | pdf | Refund not received | In-progress vs resolved |
| `complaint_006.md` | md | Billing question, polite | **Not a complaint** → enquiry |
| `complaint_007.txt` | txt | App crash, furious | **No contact details at all** |
| `complaint_008.docx` | docx | Poor service, resolved | Closed case, goodwill credit |
| `edge_case_empty_document.txt` | txt | Empty file | **Error handling** → `FAILED` row |
| `edge_case_unsupported_format.xlsx` | xlsx | Unsupported | **Format filtering** → skipped |

The last two are deliberate: they demonstrate that one bad file neither crashes
the batch nor disappears silently from the report.

Regenerate them with `python scripts/generate_sample_data.py`.

## Sample output

A full committed run against **OpenAI `gpt-4o-mini`** is in
**[`sample_output/`](sample_output/)** — 9 documents, 24 LLM calls, 29,050
tokens, 11.26 s.

```
output/
├── structured_data/complaint_001.json     # Task 1 + provenance + timings + errors
├── customer_emails/complaint_001.txt      # Task 2, ready to send
├── case_summaries/complaint_001.md        # Task 3, internal note
├── final_report.csv                       # 22 columns, one row per document
├── run_manifest.json                      # provider, model, counts, timings
└── logs/run.log                           # full DEBUG audit trail
```

All examples below are from a **real `gpt-4o-mini` run**, not the offline provider.

**Console summary:**

```
                            Batch Processing Results
┏━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━┓
┃ Case ID       ┃ Type ┃ Status  ┃ Category       ┃ Priority ┃ Esc. ┃ Time (s) ┃
┡━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━┩
│ complaint_001 │ txt  │ SUCCESS │ Billing        │  Medium  │  No  │     5.06 │
│ complaint_002 │ pdf  │ SUCCESS │ Delivery       │   High   │ Yes  │     6.21 │
│ complaint_003 │ docx │ SUCCESS │ Product Defect │  Medium  │  No  │     4.63 │
│ complaint_004 │ txt  │ SUCCESS │ Account Access │   High   │  No  │     4.62 │
│ complaint_005 │ pdf  │ SUCCESS │ Refund         │   High   │  No  │     5.33 │
│ complaint_006 │  md  │ SUCCESS │ General Enq.   │   Low    │  No  │     5.17 │
│ complaint_007 │ txt  │ SUCCESS │ Technical Iss. │   High   │ Yes  │     5.34 │
│ complaint_008 │ docx │ SUCCESS │ Service Qual.  │  Medium  │  No  │     5.93 │
│ edge_case_..  │ txt  │ FAILED  │ —              │    —     │  —   │     0.00 │
└───────────────┴──────┴─────────┴────────────────┴──────────┴──────┴──────────┘

Provider: openai (gpt-4o-mini)   Task mode: parallel   Workers: 4
Documents: 9   8 succeeded   0 partial   1 failed   Wall clock: 11.26s
LLM calls: 24   Tokens: 29,050 (25,471 in / 3,579 out)
Skipped (unsupported format): edge_case_unsupported_format.xlsx
```

**Structured extraction** (`complaint_007.json` — the web-form submission with no
contact details, showing that missing values become real nulls rather than
invented text):

```json
{
  "case_id": "complaint_007",
  "processing_status": "SUCCESS",
  "extraction": {
    "customer_name": null,
    "email": null,
    "phone_number": null,
    "product_or_service": "mobile app",
    "complaint_category": "Technical Issue",
    "issue_description": "The mobile app crashes every time the customer tries to open the reports tab since the last update...",
    "resolution_provided": null,
    "is_complaint": true,
    "escalation_required": true,
    "supporting_document_available": true,
    "overall_case_status": "Escalated",
    "priority": "High",
    "customer_sentiment": "Very Negative",
    "extraction_notes": "Contact details were not provided in the web form submission."
  }
}
```

**Generated customer email** (`complaint_002.txt` — the angry, escalated delivery
case). Note that it cites the real ticket IDs from the source document and does
**not** invent a resolution, because the document records none:

```
Subject: Update on Your Delivery Complaint for Order ORD-77821

Dear Rahul Verma,

I understand that you are experiencing significant frustration regarding your
order ORD-77821, which was promised for delivery on 6 March but has not yet
arrived as of 18 March. The tracking information has indicated 'out for
dispatch' for eleven days, and you have not received any updates despite your
previous inquiries.

I want to assure you that your case is currently being worked on and has been
escalated for further review. We recognize the urgency of this matter,
especially given your previous attempts to resolve it through tickets TKT-4411
and TKT-4622.

We appreciate your patience as we look into this issue, and we will keep you
updated on any developments as soon as possible.

Kind regards,
Customer Support Team
```

**Internal case summary** (`complaint_002.md`) — same case, different audience:

```
Case Overview  — Delivery complaint raised by Rahul Verma regarding order ORD-77821.
Key Issue      — Third contact about an Express order promised for 6 March...
Action Taken   — No action recorded.
Current Status — Escalated. Priority High; customer sentiment very negative.
Next Action    — Assign to a senior specialist and make contact within 24 hours.
```

---

## Key design decisions

**1 · Structured outputs are provider-enforced, not parsed.** Both real providers
accept a Pydantic model as a response schema and return a validated object. This
eliminates the whole class of "the model wrapped its JSON in markdown fences"
bugs that hand-rolled parsing has to defend against.

**2 · The raw LLM response is never saved.** Every response passes through
Pydantic validators that collapse whitespace, map placeholder text (`"N/A"`,
`"unknown"`, `"not provided"`) to real `None`, lowercase and format-check emails,
and sanity-check phone-number length. An invalid email is **dropped**, because
sending mail to a hallucinated address is worse than recording that we have none.

**3 · No defaults on LLM-facing schemas.** OpenAI's strict structured-output mode
requires every property to be required, so optional values are typed `T | None`
rather than given a default. A test asserts this so the constraint cannot be
broken by accident.

**4 · Two levels of concurrency, both bounded.** Documents run in a pool of
`BATCH_WORKERS`; within a document, the email and summary tasks run in a pool of
2. Threads, not processes, because every task is network-bound I/O. The batch
pool is bounded so 500 documents do not open 500 connections and trip rate
limits.

**5 · Graded failure, not all-or-nothing.** Extraction failing means the record
is `FAILED` and downstream tasks are skipped (they need its output). One
downstream task failing means `PARTIAL` — everything that did succeed is still
written. A failed file always appears in the report with its reason; it is never
silently dropped.

**6 · Prompt engineering is structural.** Rules live in the system prompt, data
in the user prompt, and documents are wrapped in explicit `<document>`
delimiters. Separating them means document content cannot dilute the rules and
makes prompt injection from a hostile document substantially harder. The
anti-hallucination rule is phrased as a concrete action ("return null") rather
than a vague plea ("be accurate").

**7 · The provider is an abstraction with three implementations.** Nothing
outside `llm/` imports a vendor SDK. That is what makes `--provider mock`
possible, and it is what lets the test suite exercise the real workflow, batching
and reporting code with no network and no non-determinism.

---

## Limitations and future work

- **Scanned/image-only PDFs are not supported.** There is no OCR step, so such a
  file fails with a clear message rather than returning empty extraction.
- **Long documents are truncated**, not chunked, at `MAX_DOCUMENT_CHARS`. A
  map-reduce summarisation step would handle very long cases properly.
- **The offline provider is heuristic, not intelligent.** It reads labelled
  fields and scores keywords, so it does well on semi-structured business forms
  and poorly on free-form prose. It exists for zero-cost evaluation and
  deterministic tests, not as a substitute for a real model.
- **English only.** The prompts and the offline keyword rules assume English.
- **No human-in-the-loop step.** Generated emails are written to disk, not sent.
  A production deployment should queue them for agent review before sending.
- **No persistent store.** Output is files on disk; a real deployment would write
  to a case-management database and expose the report as a dashboard.
- **Cost is not capped per run.** Token usage is tracked and reported, but there
  is no spend ceiling that aborts a large batch partway.

---

## Assessment requirements coverage

| Requirement | Where |
| --- | --- |
| Read from `data/`, ≥2 formats, batch, graceful file errors | `ingestion/loaders.py` — 4 formats; `batch.py` |
| Structured extraction, all listed fields, Pydantic schema | `models.py::ExtractedComplaint` |
| Not simply saving the raw LLM response | Validators in `models.py`; `persistence.py` |
| Automated customer response email | `tasks/response_email.py` |
| Management case summary (5 sections) | `tasks/case_summary.py`; `models.py::CaseSummary` |
| Workflow orchestration, not one big LLM call | `workflow.py` — 3 separate calls |
| Sequential / parallel execution | `workflow.py::_run_parallel`; `--task-mode` |
| Batch processing of multiple documents | `batch.py::run_batch` |
| Output structure + `final_report.csv` | `persistence.py`, `reporting.py` |
| Error handling | `exceptions.py`; failure matrix in `docs/architecture.md` |
| Modular code, no hard-coded values | `src/` layout; `config.py` |
| Basic logging | `logging_setup.py` — console + `output/logs/run.log` |
| Git / GitHub, no committed secrets | `.gitignore`, `.env.example` |
| README with architecture, setup, samples, decisions, limitations | This file + `docs/architecture.md` |
| Sample data and sample output | `data/`, `sample_output/` |
