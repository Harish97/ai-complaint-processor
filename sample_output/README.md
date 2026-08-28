# Sample Output

A committed snapshot of a **real run against OpenAI `gpt-4o-mini`**, so the
outputs can be inspected without running anything or spending anything:

```bash
python run.py                  # provider openai, model gpt-4o-mini
```

9 documents, 24 LLM calls, 29,050 tokens, 11.26 s wall clock, 8 succeeded /
1 failed by design. See `run_manifest.json` for the exact figures.

The same batch also runs offline with `python run.py --provider mock`, which
produces the same categories and statuses without an API key.

| Path | What it is |
| --- | --- |
| `structured_data/*.json` | Task 1 — the validated `ExtractedComplaint`, plus provenance, timings and any errors |
| `customer_emails/*.txt` | Task 2 — the generated customer response email, ready to send |
| `case_summaries/*.md` | Task 3 — the internal management case note |
| `final_report.csv` | Consolidated view, one row per document, 22 columns |
| `run_manifest.json` | Provider, model, timings and success/failure counts for the run |

`edge_case_empty_document.txt` and `edge_case_unsupported_format.xlsx` in `data/`
are deliberate error-handling fixtures. The empty file appears in
`final_report.csv` as a `FAILED` row with the reason recorded; the `.xlsx` is
reported as a skipped file. Neither produces per-case artefacts, which is why
this folder holds eight cases rather than ten.
