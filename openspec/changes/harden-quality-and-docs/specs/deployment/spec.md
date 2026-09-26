## ADDED Requirements

### Requirement: The dependencies that go into the build are audited

What the image installs is what the lock file resolves, so the lock file is
where a known vulnerability arrives. Continuous integration SHALL audit the
locked dependencies on every change and SHALL fail the run when one of them has
a known vulnerability for which a fix is available.

The audit SHALL read the lock file the build reads, not a fresh resolution of
the declared ranges: a run that audits something the image will not install
answers a question nobody asked. The repository SHALL carry the same audit as a
command, so that the answer can be had before a push rather than from a red run.

This requirement is about what the dependencies are known to contain. It does
not promise that they contain nothing else, and it SHALL NOT be read as one: an
advisory that does not exist yet is not a vulnerability the run can find.

#### Scenario: A dependency with a known fixable vulnerability
- **WHEN** the audit runs against a lock file holding a package with a known
  vulnerability that has a fix
- **THEN** the run fails and names the package

#### Scenario: The audit reads the lock rather than the ranges
- **WHEN** the audit runs
- **THEN** what it examines is the resolution the lock file records — the same
  versions the image installs — and a lock file that no longer matches the
  declared dependencies fails rather than being quietly re-resolved

#### Scenario: The same answer without a push
- **WHEN** somebody runs the repository's audit command before pushing
- **THEN** they get the same verdict CI would give them
