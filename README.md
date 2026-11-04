# Silicyte Ratchet (silicyte-0119)

**Status: Registered 2026-11-04, cc5fb5b. Result: pending.**

Page: [silicyte.com/ratchet](https://silicyte.com/ratchet). Pre-registration: [PREREG.md](PREREG.md). Loop register id:
silicyte-0119 (16:46 ET). Not arXiv 2605.22148 ("Ratchet: How Reliable Must an LLM Judge Be to Retire a Skill?"), which is
an unrelated paper that shares the name.

A pre-registered, compute-matched test of whether a library of verified program helpers **compounds** on ARC-AGI-1:
does a library that keeps growing beat the same library frozen after round 1, the same tokens spent at once, verified
exemplars, a matched sham library, and plain extra sampling, all at equal total tokens?

Results, frozen libraries and the token ledger will be committed here whatever they show, including a null.

## The test in one table

400 sealed ARC-AGI-1 evaluation tasks (sorted id list sha256
`911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd`, committed under `splits/`). The loop never reads them.
Every arm spends the same total tokens. Full definitions are in [PREREG.md section 4](PREREG.md#4-arms).

| Arm | Role | Library during growth |
|---|---|---|
| STOCK | treatment | grows after every round from demo-passing programs |
| STATIC | control | the round-1 library, frozen |
| ONE-SHOT | control | the same tokens spent in one round, then one library |
| EXEMPLAR | control | verified whole programs in context, no helper extraction |
| SHAM | control | size-, token- and genre-matched library of unverified code |
| FLAT-TTC | control | no library; the tokens go to extra samples per sealed task |
| PLANT-DRIP | positive control | Hodel arc-dsl primitives released in tranches |
| PLANT-L1 | positive control | tranche 1 only |

**COMPOUNDS** needs STOCK to beat each of the five controls by an exact one-sided McNemar test at p < 0.05, plus a reuse
gate, a helper knockout and a contamination gate ([PREREG.md section 6](PREREG.md#6-primary-metric-and-decision)). If
PLANT-DRIP fails to beat PLANT-L1, the run is VOID, not NULL.

## Registered prediction

STOCK minus STATIC net sealed solves of 400: **+2**, 80% band [-8, +14]. Calibrated band (Amendment 0, fitted on 728
resolved predictions): [-10.68, +17.216]. P(COMPOUNDS) = 0.15.

## Result log

| Date | Event |
|---|---|
| 2026-11-04 | Registered as silicyte-0119 (16:46 ET); PREREG.md committed as cc5fb5b (16:47 ET), before any model call |

## Cite

See [CITATION.cff](CITATION.cff), or use GitHub's "Cite this repository" button.

By Silicyte (silicyte.com). Design and implementation are AI-assisted; the founder sets the questions, pass rules and
retractions. Not peer reviewed.
