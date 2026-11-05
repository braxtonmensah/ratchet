# PLANT_FAIL diagnosis: silicyte-0119 (Ratchet), pilot v1

Written 2026-11-04 20:55 ET (PowerShell Get-Date). Analysis and design only: nothing under `ratchet/`, `runs/v1/` or the Quartz
code copy was edited, and no job was submitted. Every number comes from read-only Python piped over ssh to the Quartz login node
(scripts in the session scratchpad, `a1.py` to `a7.py`; they read `runs/v1/pilot/{FLAT_A,FLAT_B,PLANT1}` and
`data/raw/{arc-dsl,ARC-AGI}` and write nothing). Pilot state: `PILOT_STOP.json` reason PILOT_PLANT_FAIL, PLANT1 21 demo-pass tasks
vs FLAT_A 24 (gain -3, needs >= 1); smoke passed (24 vs 22).

## 0. Answer

**Root cause.** arc-dsl primitives dispatch on `isinstance(x, tuple)` (Grid = tuple of tuples), but the harness hands `transform`
a list of lists and exposes the primitives raw, so 8 of the 13 grid-taking primitives in L_plant_1 (including `mostcolor` and
`objects(..., without_bg=True)`, the two the model reached for first) treat the grid as an Object and crash with "too many values
to unpack (expected 2)"; all 41 helper-using ERROR samples are this crash, and the library turned would-be programs into
errors. Under that bug sits a physics floor: no pilot task the model fails is solvable from L_plant_1 (0 of 50 Hodel solvers lie
inside it, 0 of the 24 FLAT-unsolved tasks lie even inside the full capped L_plant_R), so once the crash is fixed the true PLANT1
gain is about 0, and the registered "+1 task over FLAT_A" gate is then a coin flip (P about 0.34) that cannot show whether the
harness sees a library.

**Fix, five bullets.**
1. Boundary adapter (sandbox_child): execute the library in its own namespace and expose each helper to the program through a
   wrapper driven only by the helper's own annotations: an argument whose parameter is annotated Grid, Element or Piece and is a
   list of rows goes in as a tuple of tuples; a tuple-of-tuples result of a function annotated Grid, Element or Piece comes back as
   a list of lists. Unannotated helpers (every grown STOCK, STATIC, ONE-SHOT and SHAM helper) pass through untouched.
2. One grid-contract sentence in the callable library header, the same for every library arm: "Pass grids exactly as transform
   receives them; these functions accept and return grids as lists of lists of ints." Plus a rule-generated type legend only for
   annotation names that appear in the rendered helpers (empty for unannotated libraries). Signatures and docstrings are already
   rendered (verified in `L_plant_1.py`); they were not the problem.
3. Pre-job lever check: call every grid-typed helper, through the adapter, on one list-of-lists demo grid; refuse to start if any
   raises where its tuple call does not, and print `LEVER ADAPTER grid_helpers=<n> list_smoke_ok=<n>`. A replay test on the v1
   PLANT1 programs must reproduce at least 20 of the 41 recovered (measured 24).
4. Keep tranche assignment as is (round-robin by rank, `i mod R`). No primitive tranche within the 6,000-token cap can cover a
   FLAT-unsolved pilot task, and choosing tranche 1 by the pilot tasks would fit the gate to its own data and shrink the
   PLANT-DRIP vs PLANT-L1 contrast that decides VOID.
5. Add a plumbing positive control that can only pass if the harness renders, executes and type-adapts a library and the model
   calls it (PLANT-SOLVE, section 5): each pilot task's prompt carries arc-dsl's own verified solver for that task (renamed
   `solve_this`) plus its primitive closure, at most 3,182 tokens. It gates the pilot; the L_plant_1 vs FLAT_A count stays
   registered and reported. This is a change to a registered gate, so it needs his explicit decision (line B below).

**Expected PLANT1 gain** (L_plant_1 vs FLAT_A, fix 1 to 3 only): point -1 to 0 tasks, about [-4, +3]. Basis: replaying the 41
crashed programs through the adapter makes 24 of them pass demos, but on 10 tasks, 9 of which PLANT1 had already passed with
another sample; PLANT1 goes 21 to 22, vs FLAT_A 24 and FLAT_B 22. P(gate passes | true gain 0) = 22/64 = 0.34. Expected
PLANT-SOLVE gain if the harness works: +10 to +20 of the 24 FLAT-unsolved tasks (solvers 50 of 50 correct on train and test;
the floor is whether the model writes a call). Under the v1 harness the same control reads about 0: 22 of those 24 solvers crash
on list grids.

**Amendment line (required, harness fix):** section 6, line A. **Optional, his decision (gate change):** section 6, line B.

## 1. What the model did (step 1)

### 1.1 Counts (PLANT1, 400 samples)

| status | n | helper referenced statically (`static_refs`) |
|---|---|---|
| NO_CODE | 239 | 0 |
| OK | 92 | 3 |
| ERROR | 43 | 41 |
| DEMO_FAIL | 11 | 1 |
| SYNTAX | 11 | 0 |
| BAD_OUTPUT | 4 | 0 |

- 161 samples carried code; 45 of them (28%) referenced a planted helper. So the library was seen and read. The rendering
  reached the model and the sandbox reported `helpers_callable 35` on every library exec.
- All 41 helper-referencing ERROR samples raised `ValueError: too many values to unpack (expected 2)`. The other 2 ERROR samples
  (`not enough values to unpack (expected 3, got 2)`, task a9f96cdd) reference no helper: the model wrote
  `for di, dj, color in mappings` over `((di, dj), color)` pairs, its own bug.
- Helpers named in the 41 crashes: mostcolor 37, objects 19, size 11, toindices 6, ofcolor 5, palette 4, leftmost 3, colorfilter 2,
  uppermost 2, and dneighbors, paint, numcolors, height, width 1 each.
- "Only 1 of 92 OK programs called a helper" is correct accounting, not a second bug: `helper_calls` counts calls on test inputs
  after all demos pass, and only 3 OK programs referenced a helper at all (2c608aff `size`, 868de0fa `height objects width`,
  a2fd1cf0 `connect ofcolor paint`); the first two reference names on paths not taken.

### 1.2 The 12 crashed programs read

00d62c1b s2, 08ed6ac7 s0, 0b148d64 s2, 2204b7a8 s2, 2281f1f4 s7, 444801d8 s0, 469497ad s6, 5ad4f10b s2, 6e02f1e3 s1,
7468f01a s0, 8731374e s5, 941d9a10 s1. Every one calls the helpers the way their names and docstrings say:
`bg = mostcolor(grid)`, `objs = objects(grid, univalued=False, diagonal=False, without_bg=True)`, `size(obj)`,
`toindices(obj)`, `for value, (i, j) in obj`. The model even guessed the Object cell layout `(value, (i, j))` correctly, which no
rendered text states. Nothing is wrong with the model's use; the call crashes inside the helper. 444801d8 s0 shows the model
also converts to `[list(row) for row in grid]` before calling, which makes it worse, because the prompt promises lists.

### 1.3 The 10 OK programs read

00d62c1b s6, 08ed6ac7 s2, 0b148d64 s7, 2204b7a8 s0, 2281f1f4 s0, 22eb0ac0 s0, 2c608aff s3, 3af2c5a8 s0, 3bd67248 s0, 6e02f1e3 s0.
Each re-implements in plain Python what a helper offers (BFS components instead of `objects`, `Counter(...).most_common` instead of
`mostcolor`), often on the same task where a sibling sample crashed on the helper. Same algorithm, no helper, passes.

### 1.4 Why it crashes (code read, not inferred)

- `prompt.INSTRUCTION`: "takes the input grid as a list of lists of ints". `sandbox_child.run_one`: `fn([list(r) for r in grid])`.
- `plant.py` renders each primitive by `ast.unparse` with string annotations (`grid: 'Grid'`), docstring kept. The type aliases
  (`Grid = Tuple[Tuple[Integer]]`, `Object = FrozenSet[Cell]`) are never rendered; the prompt says nothing about tuples.
- `sandbox_child` execs the library into the program's own globals and wraps names only for call counting. No type adaptation.
- arc-dsl dispatches on type: `mostcolor` is
  `[v for r in element for v in r] if isinstance(element, tuple) else [v for v, _ in element]`. A list grid takes the Object
  branch and unpacks each row into `v, _`: any row wider than 2 raises exactly the observed error. `palette`, `numcolors` do the
  same; `width` / `height` / `shape` fall to `toindices`, which returns the list, then `for i, j in` the rows; `objects(...,
  without_bg=True)` and `underfill` call `mostcolor`.

### 1.5 What the crash cost

PLANT1 lost 6 FLAT_A tasks (72ca375d, 941d9a10, a87f7484, cce03e0d, d406998b, eb5a1d5d) and gained 3 (0b148d64, 2c608aff,
868de0fa). 12 of the 19 tasks with a crash were FLAT_A demo-pass tasks. Amendment 2's draft independently found the same signature:
stopped-sample demo-pass rate 0.738 for PLANT1 vs 0.885 / 0.850 for FLAT, the difference being ERROR.

## 2. Physics floor and rule 5 (step 2)

### 2.1 Is the library usable as presented? Run on all 173 demo input grids of the 50 pilot tasks, list vs tuple

| class | count | names |
|---|---|---|
| no grid parameter (work on any input) | 22 | dneighbors, ineighbors, neighbors, size, merge, colorfilter, combine, toindices, leftmost, rightmost, subtract, uppermost, lowermost, add, connect, shoot, interval, flip, contained, outbox, hfrontier, pair |
| grid parameter, run correctly on list of lists | 5 | asindices, ofcolor, paint, replace, tophalf |
| grid parameter, raise on list of lists | 8 | mostcolor, objects (without_bg=True), palette, numcolors, width, height, shape, underfill |

**27 of 35 run on list-of-lists input; 8 of the 13 grid-taking primitives do not**, and the broken 8 hold the most-used grid
entry points (`objects` is called by 217 of 400 Hodel solvers, rank 1; `mostcolor` is the model's first call in 37 of 41 crashes).
On 2-column grids `width`, `height` and `shape` do not raise but return wrong numbers (1 of 173 grids), a silent failure.
`paint` and `replace` return tuples, so a program that then assigns `out[i][j] = v` would get a TypeError (none seen).

### 2.2 Can L_plant_1 solve any pilot task? (arc-dsl `solvers.py`, primitives each solver calls)

| library | Hodel solvers fully inside it: 50 pilot tasks | all 400 growth tasks |
|---|---|---|
| L_plant_1 as built (round-robin tranche 1, 35 primitives with deps, 2,549 tokens) | **0** | 2 |
| contiguous top 25 roots by rank (41 primitives, about 2,669 tokens) | 1 | 15 |
| contiguous top 50 roots (65 primitives, about 4,316 tokens) | 4 | 40 |
| greedy set cover on the 350 non-pilot growth solvers, 6,000-token budget | 11 | 75 (of 350) |
| full capped set = L_plant_R (about 92 primitives, about 5,954 tokens) | 9 | 114 |

- The closest pilot task to L_plant_1 is a416b8f3 (needs `hconcat`), which FLAT already solves.
- **All 9 pilot tasks inside L_plant_R are tasks FLAT already solves** (3af2c5a8, 3bd67248, 6e02f1e3, 6fa7a44f, 7468f01a,
  941d9a10, a416b8f3, a9f96cdd, cce03e0d). The 24 tasks that both FLAT runs fail all need at least one primitive outside even the
  full capped library, and their solvers are long (12 to 39 primitives).
- The tranche rule (`plant.build_tranches`: rank by distinct calling solvers, then `i mod R`) puts ranks 0, 4, 8, ... in tranche 1,
  so L_plant_1 has `objects`, `ofcolor`, `paint`, `size`, `merge` but not `fill` (rank 2), `shift`, `subgrid`, `canvas`, `recolor`,
  the mirrors or `crop`. This is by design (it balances the DRIP tranches) and is not the cause: no tranche choice under the cap
  covers a FLAT-unsolved pilot task.
- Hodel solvers are verified: 50 of 50 pilot solvers reproduce every train and test output on tuple grids. Fed list-of-lists
  grids as the v1 harness does, 42 of 50 crash (22 of the 24 FLAT-unsolved), 40 of them with the same "expected 2" error.

### 2.3 Noise floor of the gate

FLAT_A and FLAT_B agree on 20 tasks and differ on 6 (union 26), d = 0.12. Under a true gain of 0, PLANT1 minus FLAT_A behaves like
2X - 6 with X ~ Bin(6, 0.5), so P(gain >= +1) = P(X >= 4) = 22/64 = 0.34. For the gate to pass with 80% the true gain must be
about +3 tasks. Section 2.2 says a primitive library cannot supply +3 on these 50 tasks at S = 8: the model already solves the
tasks the primitives reach, and the tasks it fails are out of their reach.

## 3. Replay of the fix on the v1 samples (rule 4: prove the lever reaches the system)

The 41 crashed programs and the 4 other helper-referencing programs re-executed on Quartz in a forked child (2 s alarm per input,
import allowlist as the sandbox), with the L_plant_1 source executed in its own namespace and three modes at the program boundary:

| mode | 41 crashed programs | tasks demo-passed | other 4 helper programs |
|---|---|---|---|
| none (v1) | 41 ERROR "expected 2" | 0 | unchanged (3 OK, 1 DEMO_FAIL) |
| args only (Grid/Element/Piece list to tuple) | 24 OK, 12 DEMO_FAIL, 5 ERROR | 10 | unchanged |
| args and Grid results back to lists | 24 OK, 12 DEMO_FAIL, 5 ERROR | 10 | unchanged |

- The 5 remaining errors are `TypeError: 'NoneType' object is not iterable` in programs cut by max_tokens (truncation, not the
  adapter).
- 24 of 41 (59%) pass demos once the helpers work, against 89 of 116 (77%) for code samples that used no helper. Helper users
  pass less often (they concentrate on object-heavy tasks), so there is no sign that helpers make programs more correct.
- The 10 tasks: 00d62c1b, 08ed6ac7, 0b148d64, 2204b7a8, 2281f1f4, 6e02f1e3, 7468f01a, d631b094, d8c310e9, f25ffba3. Only
  d8c310e9 is new to PLANT1 (FLAT_B solved it, FLAT_A did not). **Corrected PLANT1 = 22 demo-pass tasks, vs FLAT_A 24, FLAT_B 22.**
- The adapter removes the harm (-3 becomes about -1 against the FLAT mean of 23) and breaks nothing that worked.

## 4. Fix design (step 3)

### 4.1 F1. Boundary adapter, `sandbox_child.py` (mode callable)

1. `lib_g = {'__name__': '__ratchet_library__', '__builtins__': safe_builtins}`; exec the library there, not in the program's `g`.
   Library-internal calls keep resolving inside `lib_g`, so arc-dsl's own tuple dispatch is never disturbed.
2. Call counting stays where it is now: wrap each callable in `lib_g` with the existing counter (internal calls still counted,
   so `helper_calls` semantics and the reuse gate input are unchanged).
3. For each library name, `g[name] = adapt(lib_g[name], params, ret)` where `params` and `ret` are the helper's annotation
   strings (read once from the library source by `ast`, or carried in the library JSON). Rule:
   - argument at a parameter annotated `Grid`, `Element` or `Piece` (also by keyword) that is a non-empty list whose items are
     lists or tuples: pass `tuple(tuple(r) for r in x)`;
   - result of a function whose return annotation is `Grid`, `Element` or `Piece` that is a non-empty tuple of tuples: return
     `[list(r) for r in result]` (arc-dsl patches are frozensets, so this touches grids only);
   - anything else, and every unannotated helper: identity.
4. `inline` mode (knockout b) is unchanged: helpers are text there. Knockout runs on STOCK helpers, which are list-native.

Arm neutrality: the rule reads only the helper's own annotations. Grown STOCK, STATIC, ONE-SHOT and SHAM helpers come from
model programs that run on list grids and carry no arc-dsl annotations, so for them the wrapper is a pass-through and their
behaviour is byte-identical to v1. If a grown helper ever does carry a `Grid` annotation, it gets the same treatment.

### 4.2 F2. Rendering and prompt, `prompt.py` / `config.py`

- `LIB_HEADER_CALLABLE` becomes: "These functions are already defined; call them directly. Pass grids exactly as transform
  receives them; these functions accept and return grids as lists of lists of ints." (one header for every library arm).
- Type legend, rule-generated: if any rendered helper's annotations name arc-dsl aliases, prepend one comment block of only those
  aliases, rewritten for the model's view, e.g. `# Grid: list of lists of ints (rows)`, `# Object: frozenset of (value, (i, j))
  cells`, `# Indices: frozenset of (i, j)`, `# Patch: Object or Indices`. About 60 to 120 tokens for L_plant_1, counted against
  the 6,000 cap like any other library text. Empty for unannotated libraries, so STOCK/SHAM pay 0 tokens unless their helpers
  name these types.
- Signatures and one-line docstrings are already rendered for the plant; grown helpers render as their source, as in v1. No
  per-arm text.
- Compatibility with Amendment 2 and with the coordinator's 8B datapoint (Qwen3-8B, prompt ending "Return only the Python code in
  one ```python block.", job 12678665: mean 257 generated tokens, 0.31% at max_tokens, 100% with `def transform`): **yes, the
  helper documentation belongs in that same code-first prompt, and it should live in the library header, not in the closing
  instruction.** Message order stays: library block (header, legend, helper sources), task block, then the instruction. The
  library note (`LIB_NOTE_CALLABLE`) is currently appended after the instruction; with a code-first instruction it must go before
  the instruction's final code-only sentence, so the last thing the model reads is still the code-only order. Concretely the
  user message ends: `<INSTRUCTION body> <LIB_NOTE_CALLABLE> <code-first sentence>`. With little or no prose, the model chooses
  helpers from the header alone, which is another reason the contract and types must be in the header. Caveat: the 8B datapoint
  is a different model; it anchors Amendment 2's F1 (which the draft dropped for lack of an anchor) but not the 35B pass rate.

### 4.3 F3. Lever check and tests

- Pre-job: for every library the job will put in context, call each helper with a grid-typed first parameter through the adapter
  on one list-of-lists demo grid from the job's own split, with defaults for other args (`True` for Boolean, a cell colour for
  Integer, a 1-cell frozenset for Patch). Refuse to start if a helper raises where its tuple call does not. Print
  `LEVER ADAPTER grid_helpers=<n> list_smoke_ok=<n>`; on v1's L_plant_1 this reads 13 and 5 and refuses.
- Unit test (CPU, tests/): replay the 41 v1 crashed programs (copy their code into a fixture) and require >= 20 demo-pass
  (measured 24); require the 4 other helper programs unchanged; require a grown STOCK-style unannotated helper to be returned by
  identity (same object).

### 4.4 F4. Tranche 1: no change

Round-robin stays. Section 2.2 shows no tranche under the cap reaches a FLAT-unsolved pilot task, and a pilot-chosen tranche
would both overfit the gate and make L_plant_1 closer to L_plant_R, raising the VOID risk of section 6 of the PREREG. Forward
risk to note now: PLANT-DRIP minus PLANT-L1 on the seal faces the same floor (L_plant_R covers 114 growth solvers vs 2 for
L_plant_1, but whether the model turns coverage into solves is unmeasured; sealed tasks have no Hodel solvers to count).

### 4.5 F5. A positive control that tests the plumbing: PLANT-SOLVE (pilot only)

- Same 50 pilot tasks, S = 8, same sampling, same instruction and header as every library arm. Per task, the callable block holds
  that task's arc-dsl solver renamed `solve_this(grid: 'Grid') -> 'Grid'` with docstring "returns the output grid for this
  puzzle", plus its primitive dependency closure. Largest closure among the 24 FLAT-unsolved tasks: 47 primitives, about 3,182
  tokens, under the 6,000 cap.
- It passes only if the block is rendered, the helpers are callable, the type adapter works and the model calls them. It fails
  on the v1 harness (22 of 24 solvers crash on list grids), so it would have caught this bug in the first pilot.
- Gate: PLANT-SOLVE demo-pass tasks >= FLAT_A + 5 (2 noise SDs at d = 0.12). Expected +10 to +20 of the 24 FLAT-unsolved tasks if
  the harness works; the uncertainty is the call rate. Generic helpers were referenced in 28% of v1 code samples, and a named
  task solver should draw far more; with Amendment 2's truncation fix most samples carry code.
- Never used in any growth round, any library, any sealed read; growth tasks only. Cost: one extra pilot arm, 400 samples.
- The L_plant_1 vs FLAT_A count stays in PILOT.md as registered and reported. Without F5 the re-run pilot is a 0.34 coin flip
  on the PLANT step, and a pass would be noise.

### 4.6 Expected PLANT1 gain

| configuration | PLANT1 minus FLAT_A, 50 tasks | basis |
|---|---|---|
| v1 (measured) | -3 | PILOT_CHOICE.json |
| F1 to F3, v1 instruction | point -1 to 0, about [-4, +3] | replay: 22 vs 24 (A) and 22 (B); no FLAT-unsolved task reachable |
| F1 to F3 plus Amendment 2 | about 0 | more samples finish in every arm; the 24 hard tasks stay outside the primitives' reach |
| PLANT-SOLVE (F5) | +10 to +20 | solvers 50 of 50 correct; closure fits the cap; limited by call rate |

## 5. Does the fix change anything registered? (step 4)

- F1 to F3 are a harness fix under PREREG sec. 7 ("Fail = fix the harness, re-run"): the registered arms, cap, sampling, model and
  metrics are unchanged. But F2 changes the text every library arm sees (header sentence, legend) and F1 changes how every library
  arm's helpers execute, so it is recorded as a dated amendment line (line A) before any growth job and any sealed read.
- F4 changes nothing.
- F5 changes the gate of sec. 7.2 (adds a gating control and turns the registered L_plant_1 check into report-only). That is a
  registered change and needs his explicit yes; line B. If he declines, line A alone stands and the PLANT step stays the
  registered +1 test with P about 0.34 under the expected null.
- Numbering: AMENDMENT 1 (self-FT) and AMENDMENT 2 (truncation) are drafts. The line below uses `AMENDMENT <n>`: fill in the next
  free number at append time, and the time from PowerShell Get-Date. If Amendment 2 is appended first, line A's header sentence
  goes in the library header, which is independent of the INSTRUCTION text that Amendment 2 changes, and the order rule of 4.2
  applies.

## 6. Exact amendment lines

Line A (required, harness fix):

```
- AMENDMENT <n> (2026-11-04 HH:MM ET, after pilot v1 job 12678501 read PLANT_FAIL, before any growth job and any sealed read):
  harness fix under section 7. In v1, 8 of the 13 grid-taking arc-dsl primitives in L_plant_1 (mostcolor, objects with
  without_bg, palette, numcolors, width, height, shape, underfill) raised on the list-of-lists grid that transform receives,
  because arc-dsl dispatches on tuple type; 41 of the 43 PLANT1 ERROR samples were this crash, and replaying them through the fix
  below makes 24 pass their demos. For every library arm, phase, round and seed, the library now executes in its own namespace and
  each helper reaches the program through an adapter that reads only the helper's own annotations: an argument at a parameter
  annotated Grid, Element or Piece that is a list of rows is passed as a tuple of tuples, and a tuple-of-tuples result of a
  function so annotated is returned as a list of lists; unannotated helpers pass through unchanged. Helper call counting is
  unchanged. The callable library header gains, exactly: "Pass grids exactly as transform receives them; these functions accept
  and return grids as lists of lists of ints." A type legend listing only the arc-dsl type names that appear in the rendered
  helpers' annotations is prepended to the library block and counts against the 6,000-token cap. The library note is placed
  before the instruction's final sentence. Each job prints LEVER ADAPTER grid_helpers=<n> list_smoke_ok=<n> and refuses to start
  if any grid-typed helper raises on a list-of-lists demo grid. Section 7 is re-run in full.
```

Line B (optional; changes the registered sec. 7.2 gate; append only on his explicit yes):

```
- AMENDMENT <n+1> (2026-11-04 HH:MM ET, same conditions): section 7.2 gains a plumbing control PLANT-SOLVE that gates the pilot:
  on the same 50 pilot tasks at S = 8, each task's callable library holds arc-dsl's own solver for that task, renamed solve_this
  with docstring "returns the output grid for this puzzle", plus its primitive closure (at most 3,182 tokens), rendered and
  executed exactly as every library arm. It passes iff its demo-pass tasks are at least FLAT_A's plus 5. The L_plant_1 check is
  still run and reported but no longer gates, because no Hodel solver of a FLAT-unsolved pilot task fits inside any primitive
  library under the 6,000-token cap (0 of 24) and its +1 rule passes with probability 22/64 under no effect at the measured
  d = 0.12. PLANT-SOLVE is pilot-only: it never enters a growth round, a library or a sealed read. PLANT-DRIP, PLANT-L1 and the
  VOID rule of section 6 are unchanged.
```
