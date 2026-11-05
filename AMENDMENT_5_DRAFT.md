# AMENDMENT 5 DRAFT (written 2026-11-05 06:46 ET, BEFORE the A5 smoke has produced any sample)

Status: draft. Not registered until an independent verifier gives GO and the lead appends it to PREREG.md. The decision
rule in part C is fixed now, before any smoke sample exists, so that the smoke cannot tune it.

## A. Withdraw run v2 before any sealed read

Run v2 (code b636ce5) finished growth at 06:04 ET and wrote FREEZE.json (sha256 730ec199...). The lead does not ack it.
Reason (GROWTH_V2_DIAGNOSIS.md, measured on the run's own files):
- every grown library is empty: STOCK 0 helpers in all 4 rounds, ONE-SHOT 0, SHAM 0 (EXEMPLAR's pool holds 217
  exemplars);
- so STOCK sends the FLAT prompt, and COMPOUNDS and LIBRARY HELPS are unreachable by construction;
- 1,225 of 1,600 STOCK round-1 samples stop at 4,096 tokens;
- at most 4 of about 435 demo-passing programs per round define a top-level helper.

v2 is WITHDRAWN_PRE_SEAL: none of its rows is ever sealed-sampled or scored, and its files stay on disk as evidence. It is
not a VOID attempt (section 6 defines VOID as PLANT-DRIP failing to beat PLANT-L1, which v2 never tested).

## B. Candidate harness change (measured by the smoke, then chosen by part C)

- P1: INSTRUCTION_V1 unchanged, plus an assistant prefill "```python\n" (vLLM continue_final_message). The model writes
  code at once, and the program text is the prefill plus the completion.
- P2: INSTRUCTION_V1 with this sentence appended: "Put each reusable step (for example finding objects, cropping,
  rotating, recolouring, counting) in its own top-level function with a descriptive name, and keep transform short by
  calling those functions." It uses the same prefill.

Whichever is chosen applies to every arm, phase, round and seed of run v3, the sealed phase included, so all arms stay
compute-matched. Max tokens, temperature, top_p, model, thinking flag, sealed tasks, arms, gates and the section 6 rule
are unchanged.

## C. Decision rule (fixed before the smoke)

The smoke uses the 50 pilot growth ids at S = 4 for P0 (V1 control), P1 and P2, all in one job. For each variant:
- A = helpers accepted by the registered rule (helpers.accept, empty previous library);
- H = share of demo-passing programs with at least one top-level helper reachable from transform;
- D = demo-pass tasks of 50.

Exact definitions (added 2026-11-05 07:14 ET, after the verifier's GO and before the smoke job was submitted; per
diag/VERDICT_SMOKE_A5.md item 1):
- H's numerator counts demo-passing programs with at least one helper that is (i) a top-level def other than transform,
  (ii) reachable from transform, and (iii) valid under PREREG 4's extraction rule. Rule (iii) drops a helper whose free
  names are not builtins, allowed imports or other valid helpers, so a helper that reads a module-level constant does
  not count.
- H's denominator is demo-passing programs (samples), not tasks and not deduped solutions.
- A counts helpers.accept on the deduped demo-passing solutions with an empty previous library.

Provenance: the smoke runs code dir b636ce5 plus two files that commit does not contain. They are diag/smoke_a5.py
(sha256 f765be121421835c59b3f2a9b93edd4b4e132c6e7d499c012acf710e6a28d06d) and slurm/smoke_a5.sbatch (sha256
745c7cac3647e4fcc51db252012a544a13a973436ebc99eba3481d2d8305b76e), both pushed in 02eb335.

A variant QUALIFIES if all three hold:
- A >= 5;
- H >= 0.20;
- D >= D(P0) - 5.

Choose P2 if it qualifies. Otherwise choose P1 if it qualifies. If neither qualifies, there is no run v3. Ratchet then
reports LIBRARY_CANNOT_FORM (model, instruction and budget stated) as its pre-seal result, and silicyte-0119 ends
without a sealed read.

## D. Run v3 (only if part C chooses a variant)

- Fresh run dir runs/v3, with the code sha committed and pushed before the first job.
- Pilot 7.1 to 7.3 as registered, plus a new gate 7.4 LIBRARY FORMATION. On the pilot FLAT_A round, A >= 5 and H >= 0.20
  must hold, measured as in part C. If 7.4 fails, report LIBRARY_CANNOT_FORM and stop.
- S and R are chosen by the registered rule at the AMENDMENT 4 budget of 48 H100-hours for run v3. v2's consumption is
  reported separately and not charged to v3.
- The section 8 prediction stays as registered (point +2, 80% band [-8, +14], P(COMPOUNDS) = 0.15).

## Closed item (07:06 ET)

The EXEMPLAR "n = 0" was a reader error by the lead; pool_R.json holds 217 exemplars (diag/BUILD_SMOKE_A5.md). There is
a latent inconsistency for v3 to fix or document: arms.py:1003 writes the pool without `sha256` and `scaler`, so
exemplar.load_pool (exemplar.py:155) would refuse it. Sealed sampling reads `exemplars` directly (arms.py:1376-1381).
