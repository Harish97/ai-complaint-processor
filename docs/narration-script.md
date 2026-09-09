# Narration Script — `complaint-processor-demo.mp4`

Timed to the 89-second screencast. About 205 words, which lands at a relaxed
pace with pauses. Read it slightly slower than feels natural — technical
narration always sounds rushed on playback.

Every cue below is the moment the caption changes on screen, so you can watch
the caption and know you are on time. **Bold** words are the assessment brief's
own skill names — hitting them out loud is the point.

---

### 0:00 – 0:04 · Title card

> "This is my final project — an AI Customer Complaint and Case Processing
> System. It runs three separate LLM tasks on every document."

---

### 0:04 – 0:09 · `ls data/` — Requirement 1, Document Ingestion

> "It reads business documents from a folder. Ten here, across four formats —
> text, markdown, PDF and Word."

---

### 0:09 – 0:19 · `python run.py` — Requirements 5 and 6

> "One command runs the whole **batch** against GPT-4o-mini. Eight documents,
> three AI tasks each — twenty-four orchestrated calls, not one large prompt.
> Documents run concurrently, and inside each document the email and summary
> tasks run in **parallel** once extraction has finished."

**Pause here.** Let the results table sit on screen for a beat.

---

### 0:19 – 0:31 · The JSON — Requirement 2, Structured Extraction

> "Task one extracts a structured record. The **Pydantic** schema is sent to the
> model as a strict JSON schema, so these are provider-enforced **structured
> outputs** — there's no JSON parsing anywhere in my code. Notice
> `resolution_provided` is null: the document records no resolution, so the
> model returns nothing rather than inventing one."

---

### 0:31 – 0:41 · The email — Requirement 3, Automated Response Generation

> "Task two writes the customer reply from that validated record. Same case.
> Careful **prompt engineering** keeps it grounded — it cites the real ticket
> numbers from the source document, and never claims the problem is fixed,
> because it isn't."

---

### 0:41 – 0:51 · The summary — Requirement 4, Management Case Summary

> "Task three writes the internal note for a manager triaging the queue. Same
> case again — overview, key issue, action taken, current status, and one
> recommended next action."

---

### 0:51 – 0:59 · `find output` — Expected Output

> "Every document produces all three outputs, plus a consolidated report and a
> full debug log."

---

### 0:59 – 1:09 · The CSV — Error handling

> "Twenty-two columns, one row per document. That includes the empty file, which
> fails by design — the reason is recorded, not hidden. One bad document never
> aborts the batch."

---

### 1:09 – 1:14 · `pytest` — Engineering practices

> "Seventy-nine tests cover the loaders, the validators, the failure policy and
> the reporting. None of them need an API key."

---

### 1:14 – 1:25 · Technical skills card  ← **the skills line**

> "Which covers the capabilities the brief asks for — **LLM API integration**,
> **prompt engineering**, **structured outputs** with **Pydantic**, **batch
> processing**, a **sequential and parallel workflow**, plus **error handling**,
> **modular code** and **logging**."

*Ten seconds on screen, and the card lists all twelve with where each one lives —
so you don't have to rush the list. Let it breathe.*

---

### 1:25 – 1:29 · End card

> "The whole thing runs in one command, with no API key required. Thank you."

---

## Recording tips

- **Record audio separately** and lay it over the video, rather than narrating
  live. You can retake a sentence without redoing the whole thing.
- **The three task scenes (0:19–0:51) are the ones that matter.** They are the
  heart of the brief. If you fluff a line, retake those.
- **Don't rush the skills card.** It has the longest hold in the video for a
  reason — that line is what an evaluator ticks boxes against.
- If you run long, the safe cuts are the `find output` line and the last
  sentence of the title card.
- If you run short, add to the JSON scene: *"Placeholder text like 'N/A' is
  normalised to real nulls, and malformed email addresses are dropped — the raw
  model response is never saved as-is."*

## If a mentor asks a follow-up

`docs/demo-script.md` has prepared answers to the six most likely questions —
why three LLM calls instead of one, how you know it isn't hallucinating, why
the downstream tasks read the extraction rather than the document, what happens
if the API fails mid-batch, why there's no LangChain, and whether it handles
scanned PDFs.
