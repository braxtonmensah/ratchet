# FINDING (2026-11-05 19:37 ET, Silicyte lead): 0128's hindsight training rows render their targets as Python lists

Found by the 0135 NARITH builder agent while reusing 0128's rows; confirmed by the lead in code and data. Disclosure; no registered file
is edited.

## The defect
- bootseed0128.beam2 stores a failed search's end state as `"hend": [list(x) for x in best[0]]`: each target string becomes a list of
  characters.
- frontier_examples builds hindsight rows with `"tgt": r["hend"]` (bootseed0128.py, the hindsight append).
- reachlaw.train renders every row with `policy_prompt(r["cur"], r["tgt"])`, and with REACH_SPACED=0 `fmt(s)` returns s unchanged, so
  `"%s" % list` prints the target as `['C', 'C', 'C', 'G', ...]`.
- At inference (search) the target is a tuple of strings and prints as `CCCG...`.
- Data: FRONTIER_s2 own_1.jsonl has 606 rows: 303 with tgt as a list of strings (own) and 303 with tgt as a list of character lists
  (hindsight). 0128 adds hindsight rows 1:1 with own rows every round, so close to half of all rows after seed256 are in a prompt
  format the policy never sees when it acts.

## What it affects
- silicyte-0128 (all seeds and GUIDE): the registered loop as run. Its results describe that loop, bug included. The general reading
  "this self-training loop decelerates" now carries the caveat that about half its training rows were malformed, which may depress
  the learning exponent (alpha 0.175, ratchet silicyte-0137).
- silicyte-0129 OPEN imports beam2 and frontier_examples unchanged, so it has the same defect. It is NOT fixed mid-study, to keep
  0129 comparable with 0128 and with the registered law prediction; a dated note is added there.
- New studies (0133 LADDER, 0138 ALPHA, 0139 SUBGOAL, 0135 NARITH) must render hindsight targets as strings, and 0138 tests the fix
  itself as the first lever: the same rows with correctly formatted targets vs as-run, on the learning exponent.
