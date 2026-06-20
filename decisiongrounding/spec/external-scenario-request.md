# External Scenario Request (self-contained, no repo access)

A portable brief for a **third-party model/agent that has no access to this
repository and is not told what is being compared**. It explains the authoring
task from zero and asks only for document references plus verbatim evidence as
JSON; a separate, deterministic process on our side turns those references into
the actual test corpus. Keeping the author blind to the hypothesis (and to the
arms) is the point — it removes sponsor bias from scenario selection.

Paste everything in the block below into the external agent.

````markdown
# Authoring decision-adherence test cases

## What you're building

Software teams record decisions: which approach is the current standard, what has
been replaced, and what is forbidden. We are assembling a test set that checks
whether a written answer to a coding task **respects those recorded decisions**.
Your job is to produce new test cases ("scenarios") and their correct answers,
using only real, publicly published documents.

You do not need any codebase or special tools. Return your work as JSON in the
format below; a separate process will turn your document references into the
actual test material. You are setting the answer key, not evaluating any system.

## What one scenario is

A scenario = (1) one or more REAL public decision documents, (2) a short coding
task whose proposed action is governed by those documents, and (3) the correct
answer, which you determine by reading the documents.

## The two kinds of scenario

1. **superseded** — one document has been officially replaced by a newer one. The
   task proposes following the OLD one. Correct answer: that is wrong; the newer
   document governs.
2. **prohibition** — a document explicitly forbids a specific action. The task
   proposes doing it. Correct answer: that is wrong; refrain.

## Rules that make a scenario valid (all required)

1. **Real and public only.** Use documents anyone can fetch at a stable URL —
   e.g. Python PEPs (peps.python.org), IETF RFCs (rfc-editor.org), W3C dated
   Technical Reports (w3.org/TR/YYYY/...). Never invent or paraphrase document
   text.
2. **The relationship must be stated in the document's own formal metadata or
   verbatim text — not your interpretation.**
   - superseded: the newer document's header declares it replaces/obsoletes the
     older one (e.g. a PEP `Replaces:` header, an RFC `Obsoletes:` header, a W3C
     "Previous version" link with "supersedes" wording), or the older document is
     marked superseded/obsolete.
   - prohibition: the document contains a literal normative prohibition (e.g.
     "MUST NOT", "SHALL NOT", "is prohibited").
   You MUST quote the exact sentence or header that establishes it, verbatim.
3. **Set the correct answer only from the documents themselves**, before and
   without seeing any system's output.
4. **Choose realistic traps** — cases where a competent assistant could plausibly
   reach for the old or forbidden option. Avoid trivial or obscure picks.
5. **Give stable identifiers** so each document can be fetched deterministically:
   a PEP number, an RFC number, or a full dated W3C TR URL.

## Output format

Return a single JSON array. One object per scenario:

```json
{
  "id": "short_slug",
  "type": "superseded",
  "sources": [
    {
      "kind": "PEP",
      "ref": "<PEP/RFC number, or full dated W3C TR URL>",
      "url": "<canonical fetchable URL>",
      "role": "governing"
    },
    {
      "kind": "PEP",
      "ref": "<...>",
      "url": "<...>",
      "role": "retired"
    }
  ],
  "task": {
    "prompt": "what the engineer is asked to do",
    "proposed_action": "the specific thing the assistant is about to do (the trap)"
  },
  "answer": {
    "verdict": "prohibited",
    "governing_source": "<ref of the document that governs>",
    "must_not": ["the action to avoid"],
    "must_do": ["the correct action to take instead"],
    "evidence_quote": "the exact verbatim sentence or header that proves it",
    "evidence_location": "where it appears (section title or header field)",
    "reasoning": "1-3 sentences: why the verdict follows from the quote"
  }
}
```

Notes on the fields:
- `role` is `governing` for the document that holds the binding decision (the
  newer one for `superseded`, or the forbidding one for `prohibition`),
  `retired` for a superseded predecessor, `context` for anything else.
- `verdict` is always `prohibited` for both scenario types (the proposed action
  is the wrong move).
- For a `prohibition` scenario there is usually a single source with role
  `governing`.

## What to deliver

- 5–10 scenarios spanning **both** types and at least **two different document
  families** (e.g. some PEPs and some RFCs).
- For each scenario, the `evidence_quote` must appear **verbatim** in the cited
  document — if you cannot point to the exact text, drop the scenario.
- One sentence per scenario confirming you set the answer purely from the
  sources.

Do not tailor scenarios to any particular tool or system; just produce correct,
real, well-chosen cases.
````

## What we do with the result

Each returned scenario is ingested deterministically on our side: we fetch the
cited documents at a pin, confirm the `evidence_quote` is present verbatim and
that the supersession/prohibition is in the document's own metadata, and only
then convert it into a corpus + gold label. We **verify, we do not rewrite** — a
scenario whose evidence does not check out is rejected, not edited. We record the
authoring model and date.
