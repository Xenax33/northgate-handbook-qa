# AI usage

## Tools I used

- Claude (Opus 5.5) in Claude Code, the desktop app, for nearly all of the work: reading, spikes, code, tests, docs.
- A second Claude agent as an independent code reviewer. It got the code but not our reasoning, so its review wasn't anchored on ours.

Gemini 3.1 Flash-Lite is the model inside the product. I didn't use it as an assistant.

## What I used them for

| Task | Tool | How much of the result I kept |
|---|---|---|
| Reading the brief and all 64 documents, listing the traps | Claude Code | The list of 22 traps. One claim in it was wrong (that some Markdown files had incomplete front matter); it was corrected after a re-check. |
| Options and a recommendation for each decision, one at a time | Claude Code | I made all 28 decisions. I chose differently from the recommendation 5 times (repo name, JSONL over YAML, a provider other than Groq, Flash-Lite 3.1 over 3.5, skipping the held-out set) and found a flaw in one (below). |
| Drafting the 40 test questions | Claude Code | All 40, after I reviewed each category with its expected answers. One question's accepted wordings were extended later, after a correct answer failed the check. |
| Spikes: comparing readers, search methods, models, memory use | Claude Code | The measured numbers. Several decisions rest on them, e.g. hybrid search and the batch size for Render. |
| Code and tests | Claude Code | Nearly all of it, checked by 158 tests, deliberate-bug checks, a fresh-clone install, six eval runs and testing the page in a browser. |
| Independent code review | Claude (separate agent) | 16 findings. The high-confidence ones were reproduced and fixed, each with a test. Two were rejected with a reason, and a few rare cases were documented as known limits instead. |
| README, DECISIONS.md and this file | Claude Code | Drafted from my decision log at my request. I asked for plain wording, and the numbers were re-checked against the saved results. |

## One thing the AI got wrong

How to split documents for search. Claude recommended searching sections and sending the model only the matching sections. I asked what happens when the information needed sits in a different section of the same document. That's what happens in this handbook. Leave Policy v2's "2. Annual leave" says 16 days, but the sentence saying it supersedes v1 is in the intro, and the rule about old balances is in "6. Transition". In the Expense Policy, the VoyageHub exception is in section 4, while a travel question may only match section 3.

Claude agreed and changed the design: search still runs on sections, but small documents (63 of 64) are sent to the model whole. Later evidence backed this up. For "how many leave days do I get?", the best-matching section of Leave v2 is "4. Carry forward" (8 days), not "2. Annual leave" (16 days).

Other things it got wrong:

- It said fastembed adds bge's search instruction to queries. It doesn't. A direct comparison of the vectors showed it, so the instruction is now added in our code.
- It said markitdown left junk in 2 of 6 PDFs. Re-running it showed 1 of 6.
- Its prompt tweak for shorter quotes broke a correct answer ("Who is the Security Lead?"). Eval run 4 caught it, and I had it reverted.
- Its first diagnosis of a failed quote (a literal "\n") was wrong. Printing the quote showed three non-adjacent rows glued together.
- Its first version of the search would have used 2.5 GB of memory on a 512 MB free server. Measuring before deploying caught it.

## What I did without AI

- Every decision in the log, after reading the options. I asked for explanations with visuals when something was unclear.
- Reviewed the 40 test questions and their expected answers before any code existed.
- Asked to move off Groq to a separate provider, got the Gemini key, and read the real rate limits from AI Studio.
- Set up Render and deployed. Ran every git commit and push myself.
- Decided when to stop tuning: I reverted the prompt tweak and dropped the injection rule when the eval showed they cost more than they gave.

I didn't type the code myself. I checked it through the tests, the eval runs and by using the app.
