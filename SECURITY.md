# Security policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/maribakulj/saknussemm/security/advisories/new)
on the repository. Please do not open a public issue for a vulnerability.

Include what you have: the input that triggers it, the version or commit, and
what you observed. A reproducing XML file is the most useful thing you can
attach — this library's attack surface is almost entirely *documents it is
asked to read*.

There is no service to attack and no credential to steal: the library opens no
socket, stores no secret, and writes no file unless a caller asks it to.

## What is in scope

**Reading a hostile document.** The parsers are hardened against the known XML
attack surface — external entities, DTD loading, network access and entity
amplification are all disabled, in one place (`src/saknussemm/formats/_xml.py`)
so the two formats cannot disagree. A crafted ALTO or PAGE file that reaches
the network, reads a local file, exhausts memory through entity expansion, or
escapes as an unclassified exception is a vulnerability.

**Writing outside the target directory.** `CorrectionResult.write()` flattens
any directory part of a source name on purpose, so a document whose name says
`../../etc/passwd` cannot steer the write. A path that escapes anyway is a
vulnerability.

**Anything a producer can make the engine do.** A caller injects an
`EditProducer`, and the edit protocol is deliberately narrow: an operation can
replace text within one existing line and nothing else. An operation that
merges, splits, moves or deletes a line — or that reaches the XML without
passing the guards — is a vulnerability, not a feature request.

## What is not in scope

**What a language model says.** A producer that proposes a wrong correction is
producing a wrong correction; the library's job is to bound the damage and
report it, which is what the guards and the loss accounting are for. A
proposal the guards accepted and that turned out to be wrong is a quality
problem, and the bench (`cinoc`) is where it is measured.

**A caller's own credentials.** The library never sees an API key it was not
handed and never persists one. How a host stores its keys is the host's
concern.

**Denial of service through legitimate size.** A very large document costs
time and memory roughly in proportion to itself. That is documented behaviour,
not a vulnerability.

## Supported versions

**Nothing has been released yet.** There are no git tags and the package has
never been published to an index, so there is no released version to patch —
see the note at the top of `CHANGELOG.md`. Until the first release, the
supported version is the current `main`.

Once releases exist, this section will name which ones receive fixes.
