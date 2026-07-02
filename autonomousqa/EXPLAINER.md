# AutonomousQA — what it is, how to run it, and why it matters

## The one-sentence version

AutonomousQA measures how much of a product an autonomous testing agent can
*prove* works — not how much it says works — by giving the agent small frozen
apps, a written list of what each app should do, and a scorer that only
counts a capability when the agent's own test passed repeatedly.

## The background

AI agents that test software make impressive claims: point one at your app
and it explores, writes tests, and reports what works. The hard question is
whether those reports can be trusted. An agent that "verifies" everything —
including things no test could actually check — is worse than useless,
because it launders uncertainty into false confidence.

This benchmark exists to make those claims comparable and honest. It is
**agent-agnostic**: the apps, the requirement lists, and the scoring are
fixed, and any agent that can be run from a command line against a URL can
be measured. [Proofkeeper](https://github.com/itsthelore/proofkeeper) is the
reference agent, but a benchmark the reference agent merely *wins* carries
more weight than a marketing page — and if another agent beats it here, the
results page will say so.

## How it works (in plain terms)

1. **Four tiny apps** — a notes web page, a money-ledger API, a
   number-crunching command-line tool, and a browser extension that counts
   words. Each is a handful of files with no third-party code, so they will
   behave identically for years.
2. **A written contract per app** — a set of requirements (in the Lore
   requirements-as-code format) saying what the app should do. Some are
   easy, some take several steps, some describe things the app must *refuse*
   to do, and a few are deliberately vague — "the interface feels calm" —
   which no test can honestly prove.
3. **The agent does its thing** — reads the contract, drives the app,
   records a test for each capability, and re-runs that test several times
   (the fidelity gate). The harness meters every model token it spends and
   times every run.
4. **The scorer only believes evidence** — a capability counts as verified
   only if the recorded test kept passing. Vague capabilities count as
   *honestly handled* only when the agent leaves them unverified. Everything
   is re-checkable later from the recorded output, without paying for a
   single new model call.

## How a non-technical person can read the results

The results page shows, per app and per model: the fraction of real
capabilities the agent proved, the fraction of trick (ambiguous)
capabilities it was honest about, how many tokens the whole thing cost, and
how much the numbers wobble between identical runs. A high verified rate
with a low honesty rate means the agent invents proof — the single most
important thing the page can tell you.

## The honest caveats (because credibility is the whole point)

- The apps are deliberately small. The benchmark measures the agent loop —
  read, drive, prove, stay honest — not whether an agent can handle a
  million-line codebase.
- The result set shipped in this repository comes from a **scripted model**
  (a canned replay that exercises the machinery). It proves the pipeline
  works; it is labelled as an illustration and is not a benchmark claim.
- Real numbers depend on the model you bring (it is a bring-your-own-key
  benchmark), which is why every published row states its exact
  configuration and its run-to-run variance.
