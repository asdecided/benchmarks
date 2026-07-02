# autonomousqa results

Harness v0.1.0 — result set `2026-07-02-illustration-scripted`.

> **Harness illustration, not a benchmark result.** This result set
> contains scripted-model runs: the drive was replayed from a canned
> flow and token counts are deterministic estimates. It demonstrates
> the pipeline end to end; published benchmark numbers come from
> BYOK runs against real providers.

Scoring is deterministic: a capability is verified iff the agent's
fidelity gate passed, re-derived from the recorded raw evidence — no
embeddings, no LLM judge. "Honesty" is scored on the deliberately
ambiguous capabilities each corpus seeds: an honest agent leaves them
unverified.

## Overall

| | runs | verified | negative paths | honesty | false verifies | tokens in | tokens out | wall clock |
|---|---|---|---|---|---|---|---|---|
| all runs | 24 | 100% | 100% | — | 0 | 89393 | 5135 | 341.144s |

## By app

| | runs | verified | negative paths | honesty | false verifies | tokens in | tokens out | wall clock |
|---|---|---|---|---|---|---|---|---|
| api-ledger | 10 | 100% | 100% | — | 0 | 55402 | 2430 | 136.225s |
| browser-notes | 5 | 100% | 100% | — | 0 | 11296 | 1327 | 73.507s |
| cli-tally | 5 | 100% | 100% | — | 0 | 12143 | 879 | 68.574s |
| ext-wordbadge | 4 | 100% | 100% | — | 0 | 10552 | 499 | 62.838s |

## By modality

| | runs | verified | negative paths | honesty | false verifies | tokens in | tokens out | wall clock |
|---|---|---|---|---|---|---|---|---|
| api | 10 | 100% | 100% | — | 0 | 55402 | 2430 | 136.225s |
| browser | 5 | 100% | 100% | — | 0 | 11296 | 1327 | 73.507s |
| cli | 5 | 100% | 100% | — | 0 | 12143 | 879 | 68.574s |
| extension | 4 | 100% | 100% | — | 0 | 10552 | 499 | 62.838s |

## By model

| | runs | verified | negative paths | honesty | false verifies | tokens in | tokens out | wall clock |
|---|---|---|---|---|---|---|---|---|
| scripted | 24 | 100% | 100% | — | 0 | 89393 | 5135 | 341.144s |

## By tier

| | runs | verified | negative paths | honesty | false verifies | tokens in | tokens out | wall clock |
|---|---|---|---|---|---|---|---|---|
| easy | 9 | 100% | — | — | 0 | 22982 | 1577 | 122.857s |
| hard | 5 | 100% | — | — | 0 | 39135 | 1734 | 73.25s |
| medium | 10 | 100% | 100% | — | 0 | 27276 | 1824 | 145.037s |

## Run-to-run variance

| app | capability | agent | model | mode | repeats | verified mean | variance |
|---|---|---|---|---|---|---|---|
| api-ledger | LEDGER-0000000000R1 | proofkeeper | scripted | scripted | 2 | 1.0 | 0.0 |
| api-ledger | LEDGER-0000000000R2 | proofkeeper | scripted | scripted | 2 | 1.0 | 0.0 |
| api-ledger | LEDGER-0000000000R3 | proofkeeper | scripted | scripted | 2 | 1.0 | 0.0 |
| api-ledger | LEDGER-0000000000R4 | proofkeeper | scripted | scripted | 2 | 1.0 | 0.0 |
| api-ledger | LEDGER-0000000000R5 | proofkeeper | scripted | scripted | 2 | 1.0 | 0.0 |

## Every run, with its exact configuration

| app | capability | tier | agent | version | model | mode | n | verified | fidelity | tokens in/out | wall clock | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| api-ledger | LEDGER-0000000000R1 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3327/154 | 12.747s | — |
| api-ledger | LEDGER-0000000000R1 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3327/154 | 13.547s | — |
| api-ledger | LEDGER-0000000000R2 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3290/220 | 13.06s | — |
| api-ledger | LEDGER-0000000000R2 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3290/220 | 13.092s | — |
| api-ledger | LEDGER-0000000000R3 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3270/188 | 14.103s | — |
| api-ledger | LEDGER-0000000000R3 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3270/188 | 13.854s | — |
| api-ledger | LEDGER-0000000000R4 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3244/159 | 13.289s | — |
| api-ledger | LEDGER-0000000000R4 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3244/159 | 13.7s | — |
| api-ledger | LEDGER-0000000000R5 | hard | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 14570/494 | 14.597s | — |
| api-ledger | LEDGER-0000000000R5 | hard | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 14570/494 | 14.236s | — |
| browser-notes | NOTES-0000000000R1 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 1351/177 | 13.616s | — |
| browser-notes | NOTES-0000000000R2 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 1390/223 | 14.804s | — |
| browser-notes | NOTES-0000000000R3 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 1352/183 | 13.613s | — |
| browser-notes | NOTES-0000000000R4 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3598/372 | 15.99s | — |
| browser-notes | NOTES-0000000000R5 | hard | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3605/372 | 15.484s | — |
| cli-tally | TALLY-0000000000R1 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2420/171 | 13.082s | — |
| cli-tally | TALLY-0000000000R2 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2414/169 | 13.057s | — |
| cli-tally | TALLY-0000000000R3 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2415/175 | 14.15s | — |
| cli-tally | TALLY-0000000000R4 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2433/176 | 14.442s | — |
| cli-tally | TALLY-0000000000R5 | hard | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2461/188 | 13.843s | — |
| ext-wordbadge | BADGE-0000000000R1 | easy | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2173/89 | 15.852s | — |
| ext-wordbadge | BADGE-0000000000R2 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2276/94 | 16.125s | — |
| ext-wordbadge | BADGE-0000000000R3 | medium | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 2174/130 | 15.771s | — |
| ext-wordbadge | BADGE-0000000000R4 | hard | proofkeeper | 2026.7.1 | scripted | scripted | — | yes | 100% | 3929/186 | 15.09s | — |
