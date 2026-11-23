# Decision log

## 1. Approach in five lines

Each file format has its own reader; each document gets a state (current, superseded, deprecated, not yet in force) worked out from the manifest.
Documents are split at headings into 122 labelled passages, searched with BM25 plus local bge-small embeddings. Superseded and deprecated documents are left out.
The top 5 documents go to Gemini 3.1 Flash-Lite, whole when small. It returns JSON: answer, refuse or clarify, and citations as passage + exact quote.
Code checks every quote. After a refusal the model suggests handbook wording and search runs once more.
FastAPI and a plain HTML page show the answer and open the source with the quote highlighted. 40 questions written before the code are scored on four measures.

## 2. Key decisions

| Decision | What else I considered | Why I chose this |
|---|---|---|
| One reader per format | markitdown for all formats | markitdown left `(cid:127)` junk in the Code of Conduct and lost the Word table header. Sources must be clean text. |
| Derive document state from `supersedes`, `deprecated` and the date; hide old documents from search | Trust the manifest's `status`; label everything and let the model decide | The manifest calls Leave v1 and the 2027 revision "current". Hiding raised top-3 retrieval from 32 to 33 of 35. |
| Search sections, but send small documents whole | Sections only; whole documents; fixed-size chunks | Precise search and citations, and the model still sees rules in other sections. I first chose sections only; that gap was caught in review. |
| BM25 + bge-small embeddings, merged | Keyword only; embeddings only | Embeddings missed "$40,000", keywords missed "What does Tyler do?". Together they ranked best. |
| Gemini 3.1 Flash-Lite, free tier | Groq; NVIDIA NIM; local Ollama | 500 requests a day is about 10 full eval runs. The provider is one `.env` setting. |
| Quotes checked in code | Passage ids only | Catches a right-looking answer citing the wrong passage; the page can highlight the sentence. |
| Second search after a refusal, in the model's handbook wording | A synonym list; rewriting every question | "PTO" appears nowhere in the handbook. Costs a call only after a refusal. |
| Score in code: retrieval, facts (incl. forbidden stale facts), citation, behaviour | One pass/fail; an LLM judge | Free, repeatable, and shows where it failed. "Must not include 12 days" catches the stale answer. |

## 3. Things in the data or the problem that surprised me

- The manifest marks Leave Policy v1 "current" although v2 supersedes it (12 vs 16 days), and marks the 2027 parental leave revision "current" before it starts. I derive states in code, with tests.
- A deprecated 2023 deploy runbook gives different freeze and rollback times. It is hidden from search but can still be opened.
- Exceptions live in other files: VoyageHub travel and the WFH allowance don't need the VP approval that the expense policy and approval matrix require. Sending small documents whole handles this.
- The "Holiday Calendar CSV" is referenced but missing. The assistant says so instead of working out the date.
- Three Mayas and three Tylers; "RTO" has two meanings; "PTO" never appears. The prompt asks for clarification on names; the second search handles PTO.
- The template mentions a "provided dev set", but the brief says no test questions are given. I wrote 40.
- pypdf turns bullets into an invisible `\x7f`, the hotel caps are a Word table, and 25 files use `**bold**` inside sentences that quotes must match. Each has a reader rule and a test.

## 4. What I tried that did not work

- A prompt change asking for shorter quotes made "Who is the Security Lead?" ask which Tyler (run 4, 38/40). It repeated on re-run, so I reverted it and fixed the table display in the page instead.
- A prompt rule against instructions inside uploads cost one answer its detail (run 5, 38/40). A hostile test upload was ignored with and without it, so I dropped it.
- Run 1 scored 34/40, but 5 of 6 failures were my measuring: 3 unretried Gemini 503 errors and 2 correct answers my checks rejected ("45-minute" vs "45 minutes"). I fixed the harness and re-scored before touching the assistant.
- Embedding with fastembed's defaults peaked at 2.5 GB, which would have crashed Render's 512 MB. Batches of 4 on one thread peak at 322 MB, and vectors are computed during the build.

## 5. Results

My 40 questions, "today" fixed at 2026-11-22. Model: gemini-3.1-flash-lite via the Gemini API free tier. Embeddings: bge-small-en-v1.5, local. Run: `eval/results/eval-20261123-151048.md`.

| Measure | Passed |
|---|---|
| All four (question passes) | 40/40 |
| Retrieval | 35/35 |
| Facts | 36/36 |
| Citation | 35/35 |
| Behaviour (answer / refuse / clarify) | 40/40 |

All seven question categories pass in full; 0 unverified quotes. The full run made 48 model calls: 40 questions, 4 second searches, 4 retries after HTTP 503. Earlier runs: 34, 39, 40, 38, 38 (all kept in `eval/results/`).

These are my own questions, and two choices were made while looking at them. There is no held-out set, so 40/40 shows the traps I found are handled, not how it does on unseen questions.

## 6. What I would do with one more week

1. A check for what substring tests miss. One refusal added a false aside ("the handbook doesn't cover org charts"). A model-graded pass on refusals would catch that.
2. Safer uploads on a shared server: more injection tests, persistent storage (a free host wipes it), and an hourly question limit to protect the 500 daily requests.

## 7. Time spent

Rough hours: reading the brief and documents 1.5, designing the measurement and writing the questions 1.5, readers and search 3, answer step and eval runs 2.5, web app and upload 2.5, deploy and docs 1.5. About 12.5 in total.
