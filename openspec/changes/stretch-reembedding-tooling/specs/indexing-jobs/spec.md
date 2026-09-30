## ADDED Requirements

### Requirement: A corpus can be rebuilt under a key, or filled under another

An operator can already ask for the work a key is **missing**. Two more
questions need answering before a model can be replaced: give me the work a key
would need to be rebuilt from scratch, and tell me whether a key is complete for
this corpus.

The service SHALL create work for every asset that **already has** a vector
under a named key, so that key's vectors are recomputed and replaced. This is
the same queue, the same leases and the same idempotent upsert as every other
piece of work: a vector replaced by a rebuild is written exactly as a vector
created by an upload is.

The service SHALL also answer, for an ordered pair of keys, how many assets have
a vector under the first and none under the second. Zero means the second key
can answer for everything the first answers for. The count SHALL be taken in one
statement, so that it describes one moment rather than a walk that a concurrent
upload can outrun.

Both SHALL be available to an operator without loading a model, because the
answer decides whether loading one is worth it.

#### Scenario: Work for a rebuild
- **WHEN** an operator asks for the work needed to rebuild a key over a corpus
- **THEN** every asset holding a vector under that key has work queued for it,
  including assets whose vector is current, because a rebuild's purpose is to
  replace vectors that already exist

#### Scenario: A rebuild asked for twice
- **WHEN** an operator asks for a rebuild's work twice, and the first request's
  work has not finished
- **THEN** the second adds nothing: an asset with work already waiting or
  running for that key is passed over, as it is for missing work

#### Scenario: How far a replacement has got
- **WHEN** an operator asks how many assets have a vector under one key and none
  under another
- **THEN** the answer is a single number taken in one statement, and no model is
  loaded to produce it

#### Scenario: A corpus one key cannot yet answer for
- **WHEN** some assets have a vector under the first key and none under the
  second
- **THEN** the count is greater than zero, and it names how many, so an operator
  can tell a run that is unfinished from one that failed
