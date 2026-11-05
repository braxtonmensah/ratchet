# AMENDMENT 5 DRAFT (written 2026-11-05 06:46 ET, BEFORE the A5 smoke has produced any sample)

Status: draft. Not registered until an independent verifier gives GO and the lead appends it to PREREG.md. The decision
rule in part C is fixed now, before any smoke sample exists, so that the smoke cannot tune it.

## A. Withdraw run v2 before any sealed read

Run v2 (code b636ce5) finished growth at 06:04 ET and wrote FREEZE.json (sha256 730ec199...). The lead does not ack it.
Reason (GROWTH_V2_DIAGNOSIS.md, measured on the run's own files):
- every grown arm is empty: STOCK 0 helpers in all 4 rounds, ONE-SHOT 0, SHAM 0, EXEMPLAR pool n = 0;
- so every section 6 contrast is zero by construction;
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

## Open item before registration

The cause of EXEMPLAR pool n = 0 in v2 must be found and fixed, or shown not to recur under v3, before part D runs. The
builder is diagnosing it with file:line.
