# Northgate Handbook Q&A

An assistant that answers Northgate Robotics employees' questions from the company handbook (64 documents in
Markdown, PDF, Word, CSV, plain text and HTML), and shows the document and the exact passage each answer rests on.
It runs as a small web app, and comes with an evaluation that measures how often it is right.

The handbook is deliberately messy: an old leave policy still marked "current", a deprecated deploy runbook, a
2027 policy that isn't in force yet, answers split across several files, a holiday calendar that is referenced
but missing, three people called Maya. The assistant is built around those traps, and the evaluation tests them.

- **Why it is built this way:** [DECISIONS.md](DECISIONS.md)
- **How AI was used:** [AI_USAGE.md](AI_USAGE.md)
- **The test questions and scoring rules:** [eval/README.md](eval/README.md)
- **Live demo:** https://northgate-handbook-qa.onrender.com (free plan: the first visit after a quiet spell takes about a minute to wake up)

## At a glance

| | |
|---|---|
| Reading | One reader per format (pypdf, python-docx, `csv`, `html.parser`); tables kept as tables |
| Old versions | Each document's state (current / superseded / deprecated / not yet in force) is worked out from the manifest; superseded and deprecated documents are never used to answer |
| Search | Hybrid: BM25 keywords + local `bge-small` embeddings, merged with reciprocal rank fusion; no API calls |
| Answers | Gemini (`gemini-3.1-flash-lite`, free tier) through its OpenAI-compatible API, returning JSON: status (answer / refuse / clarify), answer, and citations as passage + exact quote |
| Trust checks | Every quote is checked against the passage it cites; answers that can't be verified get a warning |
| Unfamiliar words | If the first answer is a refusal, the model rewrites the question in handbook terms and the search runs once more ("PTO" → "paid time off") |
| Web app | FastAPI backend + one plain HTML/CSS/JS page with a source viewer that highlights the quoted sentence |
| Uploads | Add a document from the page (title, effective date, which document it replaces); usable by the next question, no restart |
| Evaluation | 40 questions written before any code, 4 measures checked in code; every run saved in `eval/results/` |
| Tests | 159; no API key needed (internet only for the one-time model download) |

## Results

Measured on the 40 dev questions in [eval/dev_questions.jsonl](eval/dev_questions.jsonl), with "today" fixed
at 2026-11-22. Full reports, including every answer, are in [eval/results/](eval/results/).

| Run | What changed | All four measures pass | Model requests |
|---|---|---|---|
| 1 | first full run | 34/40 (36/40 after fixing two too-strict checks; 3 were Gemini 503 errors) | 40 |
| 2 | evaluation fixes only (retry 503s, matching rule) | 39/40 | 41 |
| **3** | **search again after a refusal** | **40/40** | **44** |
| 4 | prompt tweak for shorter quotes: **reverted** (broke one answer) | 38/40 | 46 |
| 5 | prompt rule against instructions inside uploads: **dropped** (cost an answer, blocked nothing extra in a test) | 38/40 | 54 |
| **6** | **final assistant: run 3's prompt, upload support, faster reloads** | **40/40** | **48** |

Run 6 measures the current code: retrieval 35/35, facts 36/36, citations 35/35, behaviour (answer / refuse /
clarify) 40/40, 0 unverified quotes, about 75,000 tokens in. The extra requests are retries after temporary
Gemini errors (HTTP 503), which the evaluation retries and counts.

**Read this number with care:** the questions were written before any code, from the traps in the handbook,
but two design choices (the search instruction and the second search after a refusal) were made while looking
at them, and there is no separate held-out set. 40/40 shows the traps found are handled; it is not a measure
of questions nobody has seen. See [DECISIONS.md](DECISIONS.md).

## Quick start

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), and a free Gemini API key. On a fresh machine, follow
[Setting up on a new machine](#setting-up-on-a-new-machine) instead.

```bash
git clone https://github.com/Xenax33/northgate-handbook-qa.git
cd northgate-handbook-qa
uv sync
copy .env.example .env          # macOS/Linux: cp .env.example .env ; then put your key in .env
uv run handbook-web
```

Open http://127.0.0.1:8000 and ask, for example, *"What is the hotel limit in Chicago?"*. The first start
downloads the search model (about 67 MB) into `.cache/models/`.

### Other commands

| What | Command | Model requests |
|---|---|---|
| Run the tests | `uv run pytest -q` | none |
| Ask one question in the terminal | `uv run python -m handbook_qa.answer "how much PTO do i get"` | 1–2 |
| See which documents search finds | `uv run python -m handbook_qa.search "who approves a new laptop"` | none |
| See how a file is read | `uv run python -m handbook_qa.ingest data/corpus/hr-travel-policy.docx` | none |
| List every document and its state | `uv run python -m handbook_qa.ingest` | none |
| Retrieval measure only | `uv run python eval/run_retrieval.py` | none |
| Full evaluation (about 4 minutes) | `uv run python eval/run_eval.py` | about 44 |
| A few questions only | `uv run python eval/run_eval.py --only version-01,refuse-01` | 1 per question |
| Re-score a saved run with the current rules | `uv run python eval/rescore.py eval/results/<file>.json` | none |

The web app's API is documented at http://127.0.0.1:8000/docs while it runs.

### Adding a document

Open **Add a document** on the page: choose a Markdown, PDF, Word, CSV, TXT or HTML file (up to 1 MB), give it a
title and an effective date, and optionally pick the document it replaces. It is read straight away; the next
question can use it. A replaced document is shown as superseded and no longer used for answers; a future date
makes the upload "not yet in force" until then. Answers resting on an upload show an *Uploaded, not from the
handbook* badge.

Uploads are kept in `data/uploads/` (git-ignored, separate from the official `data/corpus/`, which is never
changed). Remove one with **Remove** in the document list, or delete the folder to reset. At most 20 uploads.
If `UPLOAD_TOKEN` is set (do this on any public server), uploading and removing need that token; without it,
uploads are open, which is fine on your own machine. The evaluation ignores uploads and always measures the
official handbook.

## Deploy on Render (free)

The repo includes a [Render Blueprint](render.yaml) for Render's free plan.

1. Sign in at [render.com](https://render.com) with your GitHub account.
2. Click **New → Blueprint**, pick this repository, and click **Connect**.
3. When it asks for `GEMINI_API_KEY`, paste your key. It is stored by Render, never in the repo.
   (Render asks for such secrets only when a Blueprint is first created. If the service already exists,
   add `GEMINI_API_KEY` under the service's **Environment** tab and redeploy.)
4. Click **Apply**. The build installs everything and runs `python -m handbook_qa.prepare`, which downloads
   the search model and computes the passage vectors, so a sleeping instance wakes up quickly.

`UPLOAD_TOKEN` is generated by Render: find it under the service's **Environment** tab and share it with
anyone who should be able to upload documents on the public link.

What to expect on the free plan (512 MB of memory, a tenth of a CPU):

- It **sleeps after 15 minutes without visitors**; the next visit wakes it in about a minute.
- The disk is **reset on every restart**, so uploaded documents disappear.
- The app uses about 270 MB while serving (measured locally). Embedding runs in batches of 4 on one
  thread: fastembed's defaults peaked at 2.5 GB, which a 512 MB instance can't survive.
- Every push to `main` redeploys automatically.

## Setting up on a new machine

Step by step, from a machine with nothing installed. Commands are for **Windows** (PowerShell or Command
Prompt); macOS/Linux differences are noted.

**1. Install the tools (once per machine).**

| Tool | How | Check (in a **new** terminal) |
|---|---|---|
| Python 3.12 or newer | [python.org/downloads](https://www.python.org/downloads/). On Windows tick **"Add python.exe to PATH"** | `python --version` |
| Git | [git-scm.com/downloads](https://git-scm.com/downloads) | `git --version` |
| uv | `python -m pip install uv` (**not** `--user`; see [If the `uv` command doesn't work](#if-the-uv-command-doesnt-work)) | `uv --version` |

Open a **new** terminal after installing, so it picks up the updated PATH.

**2. Get the code and run the tests.**

```bash
git clone https://github.com/Xenax33/northgate-handbook-qa.git
cd northgate-handbook-qa
uv sync
uv run pytest -q
```

`uv sync` installs the exact versions in `uv.lock`. The first test run downloads the search model (about 67 MB)
and takes about a minute; it should end with `159 passed`. No API key is needed for the tests.

**3. Add a Gemini API key** (free, for the web app and the evaluation).

1. Open [Google AI Studio](https://aistudio.google.com/apikey), sign in with a Google account, and create an API key.
2. Copy the example file and open it:
   ```bash
   copy .env.example .env
   notepad .env
   ```
   (macOS/Linux: `cp .env.example .env` and any editor.)
3. Put the key after `GEMINI_API_KEY=`, with no quotes and no spaces, and save. The file must be named exactly
   `.env`. It is git-ignored, so the key is never committed.

**4. Run it.**

```bash
uv run handbook-web
```

Open http://127.0.0.1:8000. Stop it with `Ctrl+C`. Without a key the page still opens and the document browser
works; asking a question explains how to add the key.

### If the `uv` command doesn't work

Try these in order.

1. **Open a new terminal** and run `uv --version` again. A terminal opened before uv was installed doesn't see it.
2. **Check whether uv is installed but not on PATH:**
   ```bash
   python -m uv --version
   ```
   If that prints a version, uv was installed with `--user` into a folder that isn't on PATH. Either fix it:
   ```bash
   python -m pip install --ignore-installed uv
   ```
   and open a new terminal (plain `python -m pip install uv` only says "already satisfied"), **or** type `python -m uv`
   wherever this README says `uv`: `python -m uv sync`, `python -m uv run pytest -q`, `python -m uv run handbook-web`.
3. **If uv isn't installed at all:** `python -m pip install uv` (not `--user`), then a new terminal. If `python` itself
   isn't found, see the troubleshooting table below.
4. **Skip uv entirely.** Plain Python works too (tested on Windows with Python 3.12: all tests pass, the app runs):
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install -e . pytest httpx
   ```
   (macOS/Linux: `.venv/bin/python -m pip install -e . pytest httpx`.) Then use the environment's programs instead of `uv run`:

   | With uv | Without uv (Windows) | Without uv (macOS/Linux) |
   |---|---|---|
   | `uv run pytest -q` | `.venv\Scripts\python -m pytest -q` | `.venv/bin/python -m pytest -q` |
   | `uv run handbook-web` | `.venv\Scripts\handbook-web` | `.venv/bin/handbook-web` |
   | `uv run python <script or -m module>` | `.venv\Scripts\python <script or -m module>` | `.venv/bin/python <...>` |

   For example: `.venv\Scripts\python eval\run_eval.py`. In Command Prompt you can also run `.venv\Scripts\activate`
   once and then drop the prefix (`pytest -q`, `handbook-web`). PowerShell may refuse to run `Activate.ps1`; use the
   `.venv\Scripts\...` form there instead.

   The difference: pip installs the newest compatible versions, while `uv sync` installs the exact versions in
   `uv.lock` (the same today, but they can drift over time).

### Troubleshooting

| Problem | Fix |
|---|---|
| `'uv' is not recognized` but `python -m uv --version` works | uv was installed with `--user`, into a folder that isn't on PATH. Run `python -m pip install --ignore-installed uv`, then open a new terminal. (Plain `python -m pip install uv` says "already satisfied" and changes nothing.) Or use `python -m uv` instead of `uv` everywhere |
| `uv` doesn't work at all | Follow [If the `uv` command doesn't work](#if-the-uv-command-doesnt-work) above; step 4 runs everything with plain Python and pip |
| `'python' is not recognized` | Python isn't on PATH. Re-run the installer, choose *Modify*, tick *Add Python to environment variables*; or use `py` instead of `python` |
| First run prints `To support symlinks on Windows…` or `You are sending unauthenticated requests to the HF Hub` | Harmless warnings from the model download (Hugging Face). The model is copied instead of linked; no token is needed |
| The model download fails (proxy or no internet) | The search model must be downloaded once into `.cache/models/`. Connect, run `uv run pytest -q` once, and it works offline afterwards |
| The page says no API key is set | Create `.env` as in step 3 (not `.env.txt`; in Explorer turn on *File name extensions* to check), then restart the app |
| `The model's rate limit was reached` | Gemini's free tier allows 15 requests a minute and 500 a day for `gemini-3.1-flash-lite`. Wait a minute; the daily limit resets at midnight Pacific time. AI Studio's rate-limit page shows your usage |
| `The model service returned HTTP 503` | Google's service was briefly overloaded. Ask again; the evaluation retries automatically |
| Port 8000 is already in use | `uv run handbook-web --port 8001` (or set the `PORT` variable) |
| Answers about dates look odd | The app uses today's real date; the evaluation uses 2026-11-22. To try a date: PowerShell `$env:HANDBOOK_TODAY = "2027-01-02"`, Command Prompt `set HANDBOOK_TODAY=2027-01-02`, then start the app; remove it afterwards |
| An upload is refused | The message says why: the format (md, txt, pdf, docx, csv, html), size (1 MB), no text found (a scanned PDF has none), or the 20-upload limit (remove one first) |
| `The upload token is missing or wrong` | The server has `UPLOAD_TOKEN` set; type that token in the form |
| An uploaded document disappeared | On a free host the disk is temporary, so uploads are lost when the server restarts. Locally they stay in `data/uploads/` |
| A file saved from Notepad or PowerShell won't load | Files with a byte-order mark and Windows-1252 text are supported; a CSV with an unquoted comma in a value is refused with a message naming the row. Quote such values |

## How it works

```
question ─► search (BM25 + embeddings, old documents hidden) ─► top 5 documents
        ─► the model reads them (whole when small, best sections of the long runbook)
        ─► JSON: status + answer + citations (passage key + exact quote)
        ─► refused? model suggests handbook wording ─► search again ─► ask once more
        ─► every quote checked against its passage ─► answer, sources, warnings
```

- **Reading** (`ingest/`): each format has its own reader, so the passage shown as a source is clean text: PDF
  bullets and wrapped lines are repaired, Word tables and headings are kept, each CSV row becomes a
  self-describing line ("grade: L3, city_tier: 2, … per_diem_usd: 75").
- **Document states** (`ingest/manifest.py`): the manifest's own `status` field is wrong for two documents, so
  the state is derived from `supersedes`, `status: deprecated` and the effective date, for a given "today".
- **Passages** (`passages.py`): one per section, each labelled with document, section, state and effective date.
- **Search** (`search/`): keyword and meaning rankings merged; superseded and deprecated documents are left out.
- **Answering** (`answer/`): the prompt's rules cover outside knowledge, not-yet-in-force documents, refusing,
  asking for clarification, dates and citations. Quotes are checked in code.
- **Web** (`web/`): JSON API plus a static page; "Open source" shows the whole document with the quote
  highlighted, and the original file can be downloaded.

## The evaluation

40 questions in 7 categories (simple lookups across all six formats, old-vs-new versions, date-dependent,
multi-document, different wording, must refuse, must ask), each with the documents it needs, facts that must
and must not appear, and the expected behaviour. Four measures are scored in code, so every run costs only the
model calls and gives the same score for the same answers. Details: [eval/README.md](eval/README.md).

## Configuration

Settings come from environment variables or `.env` (see [.env.example](.env.example)).

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | (none) | Gemini API key (`LLM_API_KEY` also works) |
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Model name |
| `LLM_BASE_URL` | Gemini's OpenAI-compatible URL | Any OpenAI-compatible endpoint works, so the provider is a config change |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model (fastembed) |
| `HANDBOOK_TODAY` | today's date | Pretend it is this date (YYYY-MM-DD) |
| `HANDBOOK_CORPUS` | `data/corpus` | Folder with `manifest.json` and the documents |
| `HANDBOOK_MODEL_CACHE` | `.cache/models` | Where the embedding model is downloaded |
| `HANDBOOK_UPLOADS` | `data/uploads` | Where uploaded documents and `uploads.json` are kept |
| `UPLOAD_TOKEN` | (none) | If set, uploads and removals need this token (set it on any public server) |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Where `handbook-web` listens (Render sets `PORT`) |
| `EMBEDDING_THREADS` | `1` | Threads for the embedding model |

## Project layout

```
src/handbook_qa/
  ingest/        one reader per format (text, pdf, word, csv_table, html_page) + manifest.py (document states)
  passages.py    sections → labelled passages
  search/        keyword.py (BM25), semantic.py (embeddings), hybrid search in __init__.py
  answer/        context.py (what the model reads), prompt.py, llm.py (client), citations.py (quote check)
  evaluation/    questions.py, scoring.py (the 4 measures), text_match.py, report.py, retrieval.py
  ingest/uploads.py  checks and stores uploaded documents (data/uploads/, own manifest)
  web/           app.py (FastAPI) + static/ (index.html, app.js, styles.css)
  config.py      settings from the environment / .env
eval/            dev_questions.jsonl, run_eval.py, rescore.py, run_retrieval.py, results/ (every run)
tests/           one file per part that can break
data/corpus/     the 64 handbook documents and manifest.json, unchanged
```

## Known limitations

- **The score is on my own questions.** 40/40 says the traps I found are handled; questions written by someone
  else, never used for tuning, would be the real test (not done yet).
- **The measures check required facts, not everything said.** A refusal once added a false aside ("the handbook
  doesn't cover organisational charts"); nothing in the scoring catches that.
- **One reader limit:** a PDF bullet without closing punctuation runs into the next line (none in this handbook).
- **Free-tier limits:** 15 questions a minute and 500 a day across all users; Google may use free-tier prompts
  to improve its products (the handbook is fictional and no personal data is sent).
- **Wording varies with the prompt:** any prompt change rewords many answers; the evaluation is how changes are checked.
- **Uploads are trusted content.** The defences are the upload token, checked quotes and the "Uploaded" badge. One
  hostile upload ("ignore your rules…") was ignored by the model in a test, but that is one attack, not a guarantee.
- **Uploads on a free host are temporary** (lost on restart).
