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
  change 11 carries the self-exclusion), and the **threshold** outside both.
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
any filter shape beyond FR-FLT-2/3, and moving the threshold into the query.

## Decisions

1. **The predicate lives in the window, beside the index scan.** The window
   becomes `embeddings` joined to `assets` with the narrowing as its `WHERE`,
   still ordered by distance and still bounded by the page's reach. The page and
   the threshold above it do not change. Putting it in the page instead would be
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

3. **The scan's bound is part of the contract, and the answer says when it was
   reached.** `hnsw.max_scan_tuples` (20 000 by default) is what keeps a
   narrowing nothing satisfies from walking the whole index. A page that comes
   back short is therefore ambiguous: the ranking may be exhausted, or the scan
   may have stopped. The service resolves it rather than passing the ambiguity
   on — when a narrowed page comes back shorter than asked, it runs one bounded
   existence query over `assets` joined to `embeddings` under the same
   narrowing, capped at the page's reach plus one. If more matching assets exist
   than the answer holds, the scan stopped early and the answer says so.
   That query is a GIN index read with a `LIMIT`, and it runs *only* when a
   narrowed page came back short — never on the ordinary path.
   Rejected: reporting the bound from the plan (`EXPLAIN` per request is absurd)
   and guessing from row counts alone (it cannot tell "ten exist" from "ten were
   reachable").

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

## Risks / Trade-offs

- **An iterative scan can be much slower than a single scan** — that is the
  point of measuring it. Mitigation: the bound (`max_scan_tuples`) is stated,
  the numbers are published, and a deployment that wants a different trade has
  one setting to turn. An unnarrowed search is untouched.
- **The extra existence query on a short narrowed page** costs one bounded index
  read. Mitigation: it runs only when the page is short and only when a
  narrowing was given; the ordinary path never sees it.
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
