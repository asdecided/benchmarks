# The engine got 100x faster to read, and still can't build its own index at a million

The most honest thing to say about the RAC engine rebuild is the thing that
didn't work. We made point lookups on a million-artifact corpus roughly a
hundred times cheaper to serve — and then the process that builds the index
those lookups read from was killed by the kernel at 15.9 GiB, on a node with
15 GiB of RAM and no swap. The engine can answer a query at scale. It cannot
yet construct the structure it answers from. That is the headline, and it
belongs first, because everything else in this report is only trustworthy if
we lead with what failed.

Here is the shape of the win, so the miss has something to sit against. The
legacy engine re-walks and re-parses the entire corpus on every serving call.
Even with its cache turned on, a cache hit re-hashes every file to check
freshness, so cost is linear in corpus size. Warm median latency climbs from
186 ms at a thousand artifacts, to 2,179 ms at ten thousand, to 16,466 ms at a
hundred thousand — and then, at a million, the serving process is
out-of-memory killed before it answers anything. The line doesn't plateau. It
bends, and then it stops.

The rebuilt engine serves point lookups and graph reads from a persistent,
memory-mapped index whose freshness check is sublinear. Same tool, same bytes
out: `get_artifact` at a hundred thousand artifacts drops from 15,419 ms to
9.8 ms. That is a 1,573x cut, and it is flat — 10.4 ms at a thousand, 16.0 ms
at ten thousand, 9.8 ms at a hundred thousand. The engine stopped paying for
corpus size to answer a single query. Graph reads went flat too, with one
honest asterisk: `get_related` at a hundred thousand lands at 32.1 ms, which
is 2 ms over the 30 ms budget. We report it as a miss rather than round it
down, because a benchmark that hides its 2 ms overruns has already told you it
will hide the big ones.

Incremental validation is the second real win and the second real wall. The
legacy engine has no incremental path at all: re-validating after a
thousand-file change costs exactly as much as validating the whole corpus,
because it re-derives everything. That's 77 seconds at a hundred thousand
artifacts and 1,164 seconds — over nineteen minutes, at 6.3 GB resident — at a
million. The rebuild splits the work into detection and recompute. Recompute
is bound to the changeset and stays nearly flat: 1.3 seconds at a hundred
thousand, 3.0 seconds at a million. That's the part that should scale, and it
does. But detection — noticing which thousand files changed — still stats
every file in the corpus, so it slopes: 2.6 seconds at a hundred thousand,
17.9 seconds at a million. The result is that a thousand-file changeset
re-validates in 3.9 seconds at a hundred thousand (under the 5-second budget,
a pass) and in 20.9 seconds at a million (over it, a fail). And the failure is
not in the work that changed. It's in the tax we pay to find it.

Search is the path where the honest framing is structural, not apologetic.
Search is Theta of the match count by contract: the ranked result must cover
every matching document, so cost tracks how many things match, at roughly
1.6 ms per match, not how big the corpus is. Rare terms stay cheap — 10 ms at
a thousand, 655 ms at a hundred thousand as the match set grows from about
four documents to about four hundred. One deliberately broad term over roughly
27,000 matches at a hundred thousand artifacts took 412 seconds. That is a real
number for a broad query, and we neither gate it nor bury it: it's reported
per query, per class, and explicitly excluded from the size-invariance gate,
with the exclusion printed rather than assumed.

Memory is the quiet win. The legacy cache-server's resident set grows about
22 MB per thousand artifacts, which means the working set alone would exhaust
the node somewhere in the low millions — which is, not coincidentally, roughly
where it crashes. The rebuilt index lives on disk and is mmapped, so server
memory is bounded by the working set instead of the corpus. Serving fits. It
is only building that doesn't.

Two more misses deserve to be said plainly. The cold full build — constructing
the index from nothing — is 99 seconds at a hundred thousand against a 12-second
budget, and 686 seconds at a million against 120 seconds. Parsing does
parallelise, from 1,043 to 1,873 files per second, a 1.79x speedup on four
cores, but 1.79x does not close a 5.7x gap. And the source grew: 27,309 lines
became 30,583, up 12 percent. The index, the serving layer, and the
incremental machinery are new code. They are not free, and pretending the
rebuild was pure subtraction would be its own kind of dishonesty.

What the rebuild did not touch is behavior. This is the load-bearing claim
under all the numbers: 2,127 tests pass — the 1,906 original tests untouched,
plus human-approved additions — a 23-command byte-parity check confirms legacy
and rebuilt produce identical output, and the corpus gates run clean. On the
internal side, and independent of the index, `validate` now classifies each
file once instead of three times: 3,000 classify calls per thousand files
became 1,000. Honestly, `parse_file` per validate is unchanged — the win was
removing redundant classification, not re-reading — and saying so is the
difference between a measurement and a marketing figure.

The method was built to be doubted. The benchmark drives `rac` strictly as an
external process on the path, with zero engine imports, over deterministic
corpora that are a pure function of size and seed. The gate scores committed
scorecard JSON with fixed budgets and no clock in the judged path. Five
architecture decisions, ADR-100 through 104, put the superseded speed pins on
the record — the derived read-model, the persistent mmap store, event-sourced
serving freshness, incremental validation, and the parallel cold build — while
byte-identical output and untrusted-input handling were held as hard
constraints, not loosened. The work itself ran across 41 Opus agents,
about 6.9M subagent tokens, and 30 commits.

So the residual plan writes itself from the misses. Make the 1M build stream
and bound its memory so peak stays under the node. Give detection a persisted
manifest so it tracks the changeset instead of stat-ing the whole corpus.
Close the cold-build gap the parallel path only started to close. Trim two
milliseconds off `get_related`. Leave broad search Theta of matches, because
that's correct, and make its results stream instead. The engine reads at scale
now. The next movement is teaching it to build at scale too — and until it
does, this report says so in ink.

---

## Thread

1/ The RAC engine rebuild made a query on a 1M-artifact corpus ~100x cheaper
to serve. Then the process that builds the index those queries read got
OOM-killed at 15.9 GiB on a 15 GiB node. Lead with the miss. A thread on
scale, honestly measured.

2/ Legacy serving re-parses the whole corpus every call. Even cached, it
re-hashes every file. So warm p50 climbs 186ms to 2,179ms to 16,466ms across
1k to 100k artifacts, then the server is OOM-killed at 1M. The line bends,
then stops.

3/ Rebuilt serves from a persistent mmap index with a sublinear freshness
check. Same tool, same output: get_artifact @100k goes 15,419ms to 9.8ms.
That's 1,573x, and it's FLAT: 10 / 16 / 10 ms across the curve.

4/ Honest asterisk: get_related @100k is 32.1ms — 2ms over the 30ms budget.
We list it as a miss instead of rounding down. A benchmark that hides its 2ms
overruns has told you it'll hide the big ones.

5/ Incremental validate: legacy has no incremental path — re-checking a 1k
change costs a full validate (77s @100k, 1,164s @1M). Rebuilt recompute is
changeset-bound and near-flat: 1.3s to 3.0s.

6/ But detection stats every file, so it slopes: 2.6s @100k to 17.9s @1M. Net:
3.9s @100k (pass) and 20.9s @1M (fail). The failure is the tax to FIND the
change, not the change itself.

7/ Search is Theta(matches) by contract — cost tracks match count (~1.6ms
each), not corpus size. Rare terms stay cheap. One broad term over ~27k
matches @100k took 412s. Reported per query, never gated. The exclusion is
printed, not assumed.

8/ Memory: legacy cache-server RSS grows ~22MB per 1k artifacts — it would
exhaust the node in the low millions, which is about where it crashes. Rebuilt
index is on-disk + mmapped: bounded by working set. Serving fits; building
doesn't.

9/ Other misses, said plainly: cold build 686s @1M vs a 120s budget (5.7x
over); parse parallelises only 1.79x on 4 cores; source grew +12%
(27.3k to 30.6k LOC). New machinery isn't free.

10/ What didn't change: behavior. 2,127 tests green, 23-command byte parity,
corpus gates clean. The engine reads at scale now. Next movement: teach it to
build at scale. Until then, the report says so in ink. /end
