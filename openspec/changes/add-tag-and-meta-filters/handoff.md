# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-24 · claude
**State:** ready-to-merge
**Branch:** change/add-tag-and-meta-filters
**Security-sensitive:** yes — this change handles client input: a shared
parser for tag and metadata narrowings on four public surfaces, including the
multipart picture search, with parameters whose names the caller invents.
§Security-Sensitive Code of `AGENTS.md` puts that at `high`, which is why the
tier was raised at Gate 1 round 1.

## Done this session

All 28 tasks, then **Gate 2 round 1 (changes-requested) fixed — all four
findings**:

1. **blocker** — Python's `$` matches before a final newline, so the benchmark's
   schema check accepted `public\n` and its `DROP SCHEMA IF EXISTS` would have
   taken the service's own schema with it. Every validating pattern in the
   repository now ends at `\Z`: the schema name, the metadata key, the tag
   pattern, the request-id guard.
2. **major** — the benchmark owns its schema: `CREATE SCHEMA` with no drop
   before it, a taken name refused, and the cleanup conditional on that create.
3. **major** — the pair task 3.1 promised: an empty page at an offset the scan
   never reached against one the ranking never fills, with the probe's bound
   asserted.
4. **minor** — the metadata key with a newline, refused at the parser and on the
   wire, with the 64-character boundary at both ends.

Five demonstrated failing inputs, each run and restored (the commit body lists
them). `make check` 552, integration 262, ui 59.

## Next step

`/git:merge add-tag-and-meta-filters` — **Gate 2 confirmed** (confirmation 1 of
round 1, commit `6ace07c`, all four findings resolved), every task checked, the
branch pushed and CI green on that head. Only `review.md` and this file differ
from the reviewed commit, which is what the merge verifier allows.

After the merge: `/opsx:archive add-tag-and-meta-filters`, and the Russian
companion document outside the repository is refreshed.

## Blockers

None.
