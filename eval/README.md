# Evaluation questions

`dev_questions.jsonl` holds 40 questions, one JSON object per line. They were written before any assistant code existed, from a read-through of all 64 handbook documents, so they test what the handbook makes hard rather than what the assistant already does well.

## The mix

| Category | Count | What it tests |
|---|---|---|
| `lookup` | 12 | One fact from one document. Covers every format: Markdown, PDF, Word, CSV, TXT, HTML. |
| `version` | 6 | An older or deprecated document gives a different answer (Leave Policy v1, the 2023 Deploy Runbook). |
| `date` | 3 | The right answer depends on today's date (the 2027 parental leave revision, the next release freeze). |
| `multi` | 6 | The full answer needs two or more documents read together. |
| `words` | 5 | The question uses different words from the handbook ("PTO", "WFH", "probation") or casual phrasing. |
| `refuse` | 5 | The handbook doesn't contain the answer; the assistant must say so instead of guessing. |
| `clarify` | 3 | The question is ambiguous (three people called Maya); the assistant must ask or cover every case. |

## Fields

| Field | Meaning |
|---|---|
| `id` | Unique id, `<category>-NN`. |
| `category` | One of the categories above. |
| `format` | File format of the main source document (empty for `refuse`). |
| `question` | What the employee types. |
| `expect_docs` | Documents that must be retrieved and cited. |
| `must_include` | Facts that must appear in the answer. |
| `must_not_include` | Facts that must not appear, usually the stale value from an old document. |
| `forbid_docs` | Documents that must not be cited (deprecated ones). |
| `behaviour` | Expected status: `answer`, `refuse` or `clarify`, or a list of acceptable ones. |
| `note` | What the question tests and why. JSON has no comments, so this field takes their place. |

## Matching rules

- A list means every item is required. An item that is itself a list is a set of alternatives, and any one of them is enough: `[["3", "three"]]` accepts either.
- Text matching is case-insensitive. A number must not touch other digits, so `"16"` does not match `"160"`.
- Date-dependent questions assume today is **2026-11-22**. The eval fixes that date so results are the same whenever it runs.

## The four measures

1. **Retrieval:** were the `expect_docs` among the passages retrieved? This needs no model call.
2. **Facts:** all `must_include` present and no `must_not_include` present.
3. **Citation:** the answer cites the `expect_docs` and none of the `forbid_docs`.
4. **Behaviour:** the status matches `behaviour`.
