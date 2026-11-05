# DEVIATION (A4 extension): a one-line fix to the POST checker, recorded before any extension read

Written 2026-11-05 18:25 ET (PowerShell clock) by the Silicyte lead. No extension reading (round > 10) has been read for any test.

## What happened
- The registered rule (PREREG_BOOTSEED_V1.md, A4): `extend_0128.py post` must print POST OK, meaning the redone round-10 MEAS rows
  equal the archived scored-only rows; otherwise that seed's extension is VOID.
- Run at 18:2x ET with the registered checker ext/extend_0128.py (md5 635d26e2):
  - FRONTIER_s3: POST OK. FRONTIER_s4: POST OK. Both had rounds 0..10 on disk.
  - FRONTIER_s2: POST FAIL. Its MEAS line passed ("redone round 10 MEAS fixed_rows equal the archived scored-only rows (300 rows)"),
    and every row-integrity line passed, including "round 10: own_10.jsonl 910 rows; 256 + own_0..own_10 = 8440 = train_examples
    8440". Only the final line "round 10 trained (own_new present, P_11 written)" failed.

## Why it failed (a checker defect, not a data defect)
- Line 173 compares round 10's train_examples to `cum`, the cumulative row count after the LAST round on disk.
- s2 already had round 11 on disk (round_11.json 18:05 ET), so cum was 9344 (through round 11) against round 10's 8440.
- s3 and s4 had no round 11 yet, so cum happened to equal round 10's count and they passed.

## The fix
ext/extend_0128_postfix.py (md5 70bbfce1) is extend_0128.py with exactly this diff (made by an asserted string replace, read-only after):

```
165a166
>             if u == 10: cum10 = cum
173c174
<             check(s10.get("train_examples") == cum if "own_new" in s10 else False, "round 10 trained (own_new present, P_11 written)")
---
>             check(s10.get("train_examples") == cum10 if "own_new" in s10 else False, "round 10 trained (own_new present, P_11 written)")
```

## Result with the fix (ext/post_1105_postfix.log)
- FRONTIER_s2, s3, s4: all three print POST OK; the MEAS equality line passes on all three; the P_11 directory exists for all three.
- For the --final gate, the gate log for s2 is ext/post_1105_postfix.log; s3 and s4 pass under both checkers.

## What this does not change
No rule, threshold, ruler, reader or label changes. The MEAS equality check, the substance of the registered rule, passed for s2 under
the original checker.
