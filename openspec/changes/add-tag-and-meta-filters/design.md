# Design — add-tag-and-meta-filters

## Context

See `proposal.md` — Why. What the design has to work with, and one thing it was
allowed to stop guessing about:

- **The failure this change exists to prevent was reproduced before anything was
  written.** On the integration database: 3 000 assets, one in three hundred
  carrying a rare tag, the rare ones shuffled so they are not the nearest rows,
  and a page of 20 asked for with `tags_all=rare`:

  | `hnsw.iterative_scan` | rows returned | what the index scan produced |
  |---|---|---|
  | `off` (today) | **0 of 20** | 40 rows — exactly `ef_search`, none of them rare |
  | `strict_order` | **10 of 20** | 3 000 rows — it kept going until the filter was satisfied |
  | `relaxed_order` | 10 of 20 | 3 000 rows |

  Ten is every rare asset that exists, so the last two answers are complete. The
  first is the defect FR-FLT-2 names in one line: the index chose its candidates,
  the filter then removed all of them, and the answer was empty while the store
  held ten matches.
- The search statement already has three layers and a place for a predicate in
  each: the **window** the index answers, the **page** cut from it (which since
  change 11 carries the self-exclusion), and the **threshold** outside both. Two
  of those steps — the offset and the threshold — move one layer up in this
  design, for the reason decision 3 gives; the window, the exclusion and the
  order stay where they are.
- `assets.tags` has a GIN index and `assets.meta` a GIN `jsonb_path_ops` index,
  both since change 3. The listing has used the first since change 5.
- The listing's repository can already express a metadata filter
  (`find_statement`); the paged listing and the API cannot.

## Goals / Non-Goals

Goals beyond the proposal's scope statement:

- One filter object, parsed and validated once, understood by four surfaces.
- A narrowed search that is honest in both directions: it does not stop at the
  first candidates, and it does not claim to have reached the end of a ranking
  it merely stopped scanning.
- The numbers change 14 needs, produced by a command anyone can re-run.

Non-goals at the design level: choosing the index or its parameters (change 14),
any filter shape beyond FR-FLT-2/3, and changing what a page means — the offset
still skips, the threshold still removes what the page already holds and still
reaches no further down, whichever layer performs either.

## Decisions

1. **The predicate lives in the window, beside the index scan.** The window
   becomes `embeddings` joined to `assets` with the narrowing as its `WHERE`,
   still ordered by distance and still bounded by the page's reach. The page
   above it does not change. Putting it in the page instead would be
   post-filtering by another name — the measurement above is what that returns.
   Rejected: a pre-selected set of asset identifiers passed into the vector query
   (`asset_id IN (…)`), which turns a filter into a bounded list and fails for
   any corpus where the filter matches more assets than the list may hold.

2. **`hnsw.iterative_scan = strict_order`, set per query beside `ef_search`.**
   The table above is the argument: with `off` the requirement cannot be met at
   all. `strict_order` returns rows in exact distance order, which is what the
   page contract of change 8 rests on.
   Rejected: `relaxed_order` — it is allowed to return rows slightly out of
   order, and this statement cuts the window by distance *before* the page
   re-orders, so a row that arrives late can be cut although it belonged inside.
   The measurement showed no difference in what came back at this size; the
   difference it would make is exactly the one that is hard to see and easy to
   ship.
   Set per query rather than in the configuration: an unnarrowed search does not
   need it, and it is one more thing a deployment could get wrong.

3. **The scan's bound is part of the contract, and what reports it is how far
   the scan actually reached.** `hnsw.max_scan_tuples` (20 000 by default) is
   what keeps a narrowing nothing satisfies from walking the whole index. When
   the scan stops there, the answer is missing rows it would otherwise have had,
   and the service has to say so rather than let a client read it as the end of
   the ranking.

   Gate 1 rejected two earlier versions of this decision, and each rejection was
   arithmetic, not opinion. What they ruled out:

   - **the shape of the answer** (round 1, finding 1): a scan that finds exactly
     `limit` matching rows while more exist beyond its budget returns a *full*
     page with `has_more: false`;
   - **the answer after the threshold** (round 1, finding 2): `min_score`
     shortens a page for an honest reason, and a scan that was never limited
     would be reported as limited;
   - **`limit + 2` usable rows for an asset's own search** (confirmation 1,
     finding 1): the extra row an exclusion needs belongs to the *window*, not
     to the page — the page has always been capped at what the service asked
     for, so requiring one more would probe on every such search;
   - **`offset + candidates` as the prefix the scan consumed** (confirmation 1,
     finding 2): an empty page after a large offset says nothing about how many
     rows the scan produced, so a budget-limited answer could be declared
     exhausted.

   Four numbers, then, and each is defined before it is used:

   | | |
   |---|---|
   | **window reach** | `offset + limit + 1 + excluding` — what the index scan is asked for. The `+ 1` is the row beyond the page; `excluding` is 1 for an asset's own search, paying for the asset's own row, which the next layer removes. |
   | **candidates** | the rows that survive the exclusion, in order, **before** the offset and **before** the threshold. |
   | **reached** | how many candidates there were. Known in every case, including when the page is empty. |
   | **needed** | `offset + limit + 1` — the candidates an answer at this offset requires, the row beyond the page included. |

   The rule: **the scan was cut short when `reached < needed` and more matching
   rows exist than `reached`.** The first half alone cannot tell a short store
   from a stopped scan, so when it holds — and only then — one bounded question
   is asked:

   ```sql
   SELECT count(*) FROM (
     SELECT 1 FROM assets a JOIN embeddings e ON e.asset_id = a.id
     WHERE e.model = :model AND <narrowing> AND a.id <> :asking   -- for /similar
     LIMIT :reached + 1
   ) reachable
   ```

   It carries the search's own model, the search's own narrowing and the asking
   asset, and it stops at `reached + 1` because that is all the question needs.
   It is a GIN read on the slow path only; a narrowing the index satisfies
   comfortably never pays for it, and neither does any unnarrowed search.

   Worked, with `limit = 20`:

   | Situation | reached | needed | probe | answer |
   |---|---|---|---|---|
   | offset 0, scan finds 25 | 25 | 21 | not asked | complete |
   | offset 0, scan finds exactly 20, more exist | 20 | 21 | 21 > 20 | **cut short** |
   | offset 0, scan finds 20, exactly 20 match | 20 | 21 | 20 > 20 is false | complete |
   | offset 50, scan finds 10 of 40 matches | 10 | 71 | 11 > 10 | **cut short** |
   | offset 0, scan finds 25, threshold keeps none | 25 | 21 | not asked | complete |
   | `/similar`, offset 0, 21 neighbours after exclusion | 21 | 21 | not asked | complete |

   For `reached` to be knowable when the page is empty, the offset and the
   threshold are applied where that count survives — above the repository, over
   the candidates it returns. Both keep their meaning exactly: the offset still
   skips, and the threshold still removes results the page already holds without
   reaching further down (change 8), which a test asserts by comparing against
   the answers that change recorded. The extra rows crossing the wire are
   bounded by the searchable depth: at the deepest page the service accepts,
   about a thousand identifiers and distances.

   Rejected: reporting the bound from the plan (`EXPLAIN` per request is
   absurd), and re-running the scan to count it (the slow path would pay for the
   expensive part twice).

   One measured fact about the bound, found while building the tests for it and
   worth knowing before reading them: `hnsw.ef_search` budgets the scan's *first*
   iteration, and `max_scan_tuples` bounds what comes after. On the corpus of
   3 000 with thirty matches, a query needing 56 candidates reached all thirty
   at every bound down to 20, while a query needing 3 reached 2 at a bound of
   200. So a deep page is not what runs into this bound — a shallow one over a
   rare narrowing is, which is what the tests use.

4. **One filter object, four surfaces.** A frozen value in `app/domain.py` —
   the tags required, the tags any of which suffice, and the metadata
   equalities — built by one parser in the services layer that normalises tags
   the way FR-TAG-1 normalises them, checks metadata keys against
   `^[a-z0-9_]{1,64}$`, refuses more than five of them and refuses the same key
   twice (two values for one key can never both hold, and silently `AND`-ing
   them would answer an empty page to a request that was a mistake). The three
   searches and the listing pass the same object to their repositories.

5. **`meta.<key>` is read from the raw parameters.** Its name is not fixed, so
   the framework cannot declare it: the router reads the query string (and, for
   the picture search, the form fields), takes what starts with `meta.`, and
   hands the rest to the parser. Everything else about those endpoints keeps its
   declared parameters, and the OpenAPI document describes the convention in the
   operation's description, because it cannot list a parameter whose name the
   caller invents.

6. **The depth bounds do not move.** `limit + offset` stays at 999, and 998 for
   an asset's neighbours. They bound how deep a *page* may reach, which is a
   promise to the caller; the scan's own budget is a separate bound with its own
   report (decision 3). Tying the two together would make a narrowed search
   refuse pages it can answer perfectly well.

7. **The measurement is a command, not a paragraph.** `scripts/` gains a script
   that builds a synthetic corpus of a given size and selectivity in the
   integration database, runs the same statement the service runs at each
   setting, and prints rows-returned and latency; `docs/how-to/benchmarks.md`
   carries its output and the command that produced it. Synthetic on purpose:
   what is being measured is the index's behaviour against selectivity, and a
   real model's vectors would only add a variable nobody can control.

## Applicability

| Question | Answer |
|---|---|
| Empty / zero / null inputs | An empty narrowing is the search as it is today, and the parser treats "absent" and "empty after normalisation" alike — `tags_all=` is no narrowing, not a narrowing by nothing. A narrowing nothing satisfies is an empty page and never an error; an empty page with a narrowing still answers whether the scan stopped early, which is the case the probe exists for. Zero surviving rows after the threshold is *not* a stopped scan, and a test says so. |
| Authorization boundary | n/a — the service has no authentication (D12), and a filter narrows what a caller already sees in full; nothing here hides or reveals anything a listing did not already show. |
| Crash around an external effect | n/a — every path this change touches is a read. Nothing is written, so nothing can be half-written. |
| Concurrent writers | n/a for correctness of a write; a search runs against whatever is committed, and an asset whose tags change between two pages is the pagination caveat the capability already states. |
| Deletion / expiry | An asset deleted between the scan and the probe makes the probe count one fewer, which can only turn a "stopped early" into an "exhausted" — the answer is then correct for the store as it is. Nothing here deletes. |
| Idempotent retries | A search is a read: asking twice costs two scans and changes nothing. The probe is a read too. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **An iterative scan can be much slower than a single scan** — that is the
  point of measuring it. Mitigation: the bound (`max_scan_tuples`) is stated,
  the numbers are published, and a deployment that wants a different trade has
  one setting to turn. An unnarrowed search is untouched.
- **The extra existence query** costs one bounded index read. Mitigation: it
  runs only when the scan reached fewer candidates than the answer needed, and
  only when a narrowing was given; every unnarrowed search and every narrowing
  the index satisfies comfortably takes the fast path.
- **The offset and the threshold applied above the repository** move about a
  thousand more rows across the wire at the deepest page the service accepts.
  Mitigation: they are two columns wide, the bound is the searchable depth
  itself, and it buys the one number without which a cut-short answer cannot be
  told from a complete one.
- **A rule enforced one layer up** — the threshold, and now the offset — is a
  rule that moves, and a rule that moves is a rule that can be lost. Mitigation: the test change 8 wrote for
  it keeps running, and one more asserts that a threshold shortening a page is
  never reported as a stopped scan.
- **A new field in the search envelope** is a compatible addition, but it is a
  field every client now has to ignore or understand. Mitigation: it is the same
  shape as `query_truncated`, which clients already handle, and it is absent
  from the answer to an unnarrowed search.
- **`meta.<key>` parsed from the raw query string** is a convention the
  generated OpenAPI cannot express as a parameter. Mitigation: it is described
  in the operation, an example is carried in the document, and the refusals are
  the same problem details as every other bad parameter.

## Migration Plan

None. No schema change and no data change: both GIN indexes have existed since
change 3, and `hnsw.iterative_scan` is a session setting this change turns on
per query. A deployment that never sends a filter sees no difference at all.

## Open Questions

None.
