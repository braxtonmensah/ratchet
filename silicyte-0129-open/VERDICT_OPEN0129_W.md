VERDICT: GO

Independent verification of DEVIATION 1105-W (silicyte-0129 OPEN), 2026-11-05 19:31 ET (Quartz clock). Read-only; no process touched.

## 1. Diffs, parse, file name use
- md5: open0129.py 4e46988a5d47448cbbb63c13d82b2b7b, open0129_w.py 76eac0733e653261e83bb9776339b6ea, run_open0129.sh 600bf85dffcfeda5a138320b24f26173, run_open0129_w.sh da6c3475a8dad7122aa4f688eae00921.
- diff open0129.py open0129_w.py: only "346a347,348", the two DEVIATION 1105-W lines before `trs, omd5, amd5 = train(` (now line 349).
- diff run_open0129.sh run_open0129_w.sh: only lines 2 (comment), 12 (META md5s of open0129_w.py and run_open0129_w.sh) and 14 (python runs open0129_w.py). The launch-shape comment on line 4 still names run_open0129.sh (comment only, harmless).
- python3 -I ast.parse(open0129_w.py): PARSE_OK.
- Own-name uses: HERE = dirname(abspath(__file__)) (:74, directory only, same dir); CODE_MD5 = fmd5(abspath(__file__)) (:206, recorded in META and in round_t.json summary code_md5, now 76eac073, the intended record; nothing asserts it equals 4e46988a); ruler child Popen([sys.executable, "-u", abspath(__file__), D, FL, OD, "ruler", ...]) (:285), so the child runs open0129_w.py in MODE "ruler", whose branch (:134-171) is byte-identical to the registered one. The md5 asserts in the code are on bootseed0128.py (c54e21d2, confirmed on disk), opengen and the frozen rulers, not on the script itself. Docstring text naming open0129.py is inert. Fine.

## 2. No registered quantity changes
- Ruler: scores final P_t only (refuses P_t without round_{t-1}.json, :141), checks the adapter bytes and mtimes are unchanged (VOID_ADAPTER_CHANGED, :160), deterministic beam: runs/det.log has "RULER_DETERMINISM MATCH rows_equal 300 of 300". When it runs cannot change its rows.
- Trainer: train(seed_rows + allown, P_{t+1}, rs, rs, "r%d") with rs = 1000k + t + 1 is the same call with the same inputs; bootseed0128.train (:267-294) sets torch.manual_seed and the order shuffle itself, and the ruler is a separate process, so no RNG state is shared. The wait only delays the call.
- Later rounds: after the wait RPROC[0] holds a finished Popen; next round's ruler_kick sees p.poll() is not None, sets RPROC[0] = None and respawns for every final P_u lacking ruler_u.json (so a failed ruler, rc != 0, is retried next round). Final ruler_kick(T_TO+1, wait=True) unchanged.
- Seed 2 resume path (state now: P_0 present, search_0.json, own_0.jsonl, train_r0.jsonl, no P_1, no round_0.json, no ruler_0.json, no ruler tmp file): start_check (alone, before any ruler) -> P_0 present, no copy -> round 0: ruler_kick(0) prints RULER_SPAWN rounds=[0] -> "SEARCH 0 cached" (asserts D 10, max_steps 12) -> own_0.jsonl rewritten from the same S (deterministic) -> RULER_WAIT_DONE t=0 -> train. train_r0.jsonl is rewritten by train (open "w") and tmp_r0 is removed first, so the crash leftovers are harmless.
- Concurrency: the trainer can no longer overlap a ruler started by this process. P_0 training (k without a copied P_0) happens before the loop, before any ruler spawn; start_check is a scorer, not the trainer, and also precedes the first spawn. Each round spawns at most one ruler (ruler_kick returns if one is running) and that ruler is always waited before train. The only other risk is an orphan ruler from a dead run: on g61 no open0129 process of bsmensah exists now (ps empty; the crash ruler pid 1653588 is gone).

## 3. Peak memory
- Search phase: search scorer (about 21.5 GB) + ruler (21.15 GiB) = about 43 GB.
- Train phase: trainer alone, about 59.8 GiB (47.59 in use + 12.24 requested at the crash).
- Three at once cannot happen (the search scorer is freed before train, the ruler is waited). Worst case: trainer alone, about 60 GiB of 79.18 GiB.

## 4. Seeds 1 and 3 on old code
Agree. The change is scheduling only, so mixed code is harmless if they survive, and relaunching a crashed seed on open0129_w.py is the same deviation. Note: seed 1 (H10, g56) is in round 0 training now with its ruler running, and logged at 19:29:47 "expandable_segments: memory mapping failed with OOM on device 0 ... free: 19726336"; expect it to crash the same way. Seed 3 (I1, g90) is in its round 0 search with its ruler; its trainer faces the same risk when its search ends.

## 5. PREREG
No PREREG change needed. Sec. 3 O5 says the ruler "is scored by a side process on every final P_t"; it still is. No rule, ruler, reader, label, threshold or seed changes. The dated note DEVIATION_0129_W_1105.md (19:29 ET, before any round result) is the right record; publish it with this verdict. One disclosure to add to the note: rounds get longer by the ruler tail, so fewer rounds may finish before the deadline cutoff (sec. 5 counts P_t by round_{t-1}.json mtime). That changes how many rounds exist, not how any round is measured; in exchange rulers no longer lag, so none is missing at the deadline except the last P_t.

## Holder check and relaunch line
H9 12694676 on g61 is Slurm GRES IDX 3. Slurm IDX is not the nvidia-smi index on g61 (vparakka 12674560_43 is IDX 2 but its process sits on smi GPU 3). smi GPUs 0, 1, 3 hold the other three jobs' processes (VLLM 1626626 of arct-rsi-p26, bootseed.py 1646249 of maxSELFFT_H2, vparakka 1645849); smi GPU 2 shows 0 MiB and no process. So H9's GPU is empty at 19:29:57 ET. Seed 2's META at its first start also read 0 MiB.

setsid nohup srun --jobid=12694676 --overlap -n1 -c 24 bash /N/scratch/bsmensah/silo/open0129/run_open0129_w.sh 2 99 >> /N/scratch/bsmensah/silo/open0129/runs/OPEN_s2.log 2>&1 < /dev/null &

After launch, confirm in OPEN_s2.log: META code_md5=76eac073..., START_CHECK rows_equal_60 true, RULER_SPAWN rounds=[0], SEARCH 0 cached, RULER_WAIT_DONE t=0 rc=0, then LEVER ... tag=r0.
