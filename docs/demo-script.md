# Demo Script — 4 minutes

A tight walkthrough for a screen recording or a live demo. Every command is
copy-pasteable. Timings assume you talk while things run.

---

## Before you record

```bash
cd ai-complaint-processor
source .venv/bin/activate          # Windows: .venv\Scripts\activate
rm -rf output                      # start from a clean slate
clear
```

Have two things open: a terminal (large font, at least 100 columns) and a file
browser or editor showing the project folder.

**Check `.env` has your key** if you plan to show the live model. If you would
rather not show a real key on camera, run the whole demo with `--provider mock`
and say so — the flow is identical.

---

## 0:00 — 0:30 · What it is

> "This is my submission for Project 1 — an AI-powered document processing and
> business workflow. It reads customer complaint documents from a folder in four
> different formats, and for every document it runs three separate LLM tasks:
> structured extraction, a customer response email, and an internal case summary.
> Everything is consolidated into a CSV report at the end."

Show the folder:

```bash
ls data/
```

> "Ten sample documents — text, markdown, PDF and Word. The last two are
> deliberate edge cases: an empty file and an unsupported spreadsheet. I'll come
> back to those."

---

## 0:30 — 1:15 · The structure

```bash
ls src/complaint_processor/
```

> "The code is layered. Ingestion handles the file formats. Prompts are kept
> separate from logic. The `llm` package wraps the providers. `tasks` has one
> module per AI task. `workflow` orchestrates a single document, and `batch`
> handles concurrency across documents. No module imports from a layer above it,
> and no vendor SDK is imported outside the `llm` package."

Open **`src/complaint_processor/models.py`** and scroll to `ExtractedComplaint`.

> "This is the core of it. Every field the brief asked for — customer name,
> email, phone, category, issue description, resolution, the three yes/no flags,
> and case status. This Pydantic model is sent to the provider *as the response
> schema*, so the model is constrained to return exactly this shape. I'm not
> parsing JSON out of a text response anywhere."

Scroll down to the validators.

> "And this is what makes it trustworthy rather than just well-formed. Anything
> the model returns as 'N/A' or 'unknown' becomes a real null. Malformed email
> addresses get dropped entirely — because sending mail to a hallucinated address
> is worse than recording that we don't have one. The raw response is never
> saved."

---

## 1:15 — 2:15 · Run it

```bash
python run.py
```

While it runs:

> "It's processing all nine eligible documents concurrently. Within each
> document, extraction has to finish first because both downstream tasks consume
> its validated output — but the email and the summary don't depend on each
> other, so those two run in parallel."

When it finishes, point at the summary table:

> "Eight documents succeeded. One failed — that's the empty file, and it's failed
> *by design*: it shows up in the report with the reason recorded, rather than
> crashing the batch or silently disappearing. The spreadsheet was skipped as an
> unsupported format, and that's reported too."

> "Twenty-four LLM calls, about eleven seconds wall clock."

---

## 2:15 — 3:00 · The output

```bash
ls output/
cat output/structured_data/complaint_007.json
```

> "This one is interesting — it's a web form that was submitted with no contact
> details at all. Name, email and phone all come back as proper nulls. The model
> didn't invent them, and the extraction notes say why."

```bash
cat output/customer_emails/complaint_002.txt
```

> "This is the angry delivery complaint. Notice it cites the real ticket numbers
> from the source document, and it does *not* claim the problem is fixed —
> because that document records no resolution. It says the case has been
> escalated, which is what the document actually supports."

```bash
open output/final_report.csv     # or: column -s, -t < output/final_report.csv | less -S
```

> "And the consolidated report — twenty-two columns, one row per document,
> including the failed one."

---

## 3:00 — 3:40 · The engineering

```bash
python run.py --provider mock --limit 3
```

> "The provider is fully swappable. This is the same pipeline running against an
> offline rule-based provider — no API key, no network, no cost. That's there so
> the project can be evaluated for free, and so the test suite can exercise the
> real workflow deterministically. It's regex and keyword rules, not a model, and
> I say that plainly in the README."

```bash
pytest
```

> "Seventy-nine tests — the loaders, the validators, the failure policy, batching
> and reporting. All of them run without an API key."

---

## 3:40 — 4:00 · Close

> "Everything is in the GitHub repo — source, sample data, a committed sample
> run, the README with setup and design decisions, and an architecture document
> with the diagrams. The limitations are written up too: there's no OCR for
> scanned PDFs, long documents are truncated rather than chunked, and the
> generated emails are written to disk rather than sent, because a production
> deployment should put a human in the loop before anything goes to a customer.
>
> Thank you."

---

## If they ask you something

**"Why three LLM calls instead of one?"**
One prompt returning everything degrades on long documents, makes validation
all-or-nothing — one bad field fails the whole thing — and can't be parallelised.
Three focused prompts keep each one short, contain failures, and let two of them
run concurrently.

**"Why do the email and summary read the extraction instead of the document?"**
By that point the extraction has been validated: placeholders are nulls and
malformed contact details are gone. If the email read the raw document it could
reintroduce a bad email address that validation had already stripped. The
document is still passed as read-only context for tone and detail.

**"How do you know it isn't hallucinating?"**
Three defences. The schema constrains the shape. The prompts instruct the model
to return null rather than guess — phrased as a concrete action, not a vague plea
to be accurate. And the validators drop anything malformed. On top of that, the
live model and the offline provider independently produced the same eight
categories, which cross-checks the extraction.

**"What happens if the API goes down mid-batch?"**
Transient errors retry with exponential backoff. If a call still fails,
extraction failing marks that document FAILED and skips its downstream tasks;
a downstream task failing marks it PARTIAL and still writes everything that
worked. Either way the batch continues and the reason lands in the report.

**"Is this using LangChain?"**
No. Project 1's skill list is LLM API integration, prompt engineering, structured
outputs, Pydantic and workflow orchestration — none of which need a framework
here. Calling the provider SDKs directly kept the code smaller and made the
control flow explicit, which matters when I have to explain it. The provider
abstraction is one small interface I own.

**"Could it handle a scanned PDF?"**
Not today — there's no OCR step, so it fails with a clear message rather than
silently returning an empty extraction. Adding Tesseract behind the existing
loader interface would be the fix, and the loader registry is designed for
exactly that kind of addition.
