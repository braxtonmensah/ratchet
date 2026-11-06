# PRIOR ART: silicyte-0136 ONE-SHOT, meanings (d) amortisation and (b) one-shot weight generation

Written 2026-11-05 about 19:00 ET by the 0136 builder. Web search, abstracts and secondary summaries only; full papers were not read,
so the numbers below are the authors' own and are marked where only a summary carried them. We claim no "first" anywhere.

## (d) Amortisation: distil search into a one-shot policy

| work | what it shows | relation to 0136 (d) |
|---|---|---|
| Anthony, Tian, Barber 2017, "Thinking Fast and Slow with Deep Learning and Tree Search" (Expert Iteration, ExIt; arXiv 1705.08439, NeurIPS) | Tree search (expert) plans, a network (apprentice) imitates it, the apprentice then guides the next search. On Hex the policy-guided search beats plain MCTS. | 0128 IS an ExIt loop (beam = expert, LoRA = apprentice). ExIt asserts the apprentice-to-expert channel; 0136 measures it per round on our stored apprentices. |
| Silver et al. 2017/2018, AlphaGo Zero / AlphaZero | Search is used in training and play; the raw network alone is far weaker than network + MCTS. A secondary source (LessWrong thread citing the AGZ paper's figure) gives about 3,055 Elo for the raw network; the full AlphaGo Zero with search is about 5,185 (recalled, not re-checked). Neither number verified against the paper here. | The policy-vs-search gap is the known quantity; we found no published per-iteration curve of that gap. 0136's G_t over rounds is exactly that curve for an LLM expert-iteration loop. |
| Yu, Xu, Weston, Kulikov 2024, "Distilling System 2 into System 1" (arXiv 2407.06023) | Fine-tune the plain model on the filtered outputs of a System 2 method (including search); sometimes matches or beats the teacher at a fraction of the inference cost; fails on CoT for hard math. | One-step distillation. 0136 asks the iterated version: does the gap close round over round when the teacher is the loop's own search? |
| Zelikman et al. 2022, STaR; Singh et al. 2023, ReST-EM "Beyond Human Data" (arXiv 2312.06585) | Generate, filter by a binary verifier, fine-tune, repeat. ReST-EM reports gains in pass@k and majority voting as well as pass@1; on APPS the first iteration gives most of the gain and later ones can hurt (course slides). | Same loop family with sampling instead of search. pass@1 vs pass@k over iterations is the sampling analogue of one-shot vs searched reach. |
| Lehnert et al. 2024, "Beyond A*: Better Planning with Transformers via Search Dynamics Bootstrapping" (Searchformer, arXiv 2402.14083) | Train on A* traces, then expert iteration: solves 93.7% of unseen Sokoban optimally with search traces 26.8% shorter than A* (v2 numbers; the ICLR workshop abstract says 93.5% and 12.7%). | Direct evidence that expert iteration can shrink search effort per solve. 0136 measures the analogue (search-free reach) without retraining. |

## (b) One-shot weight generation

| work | what it shows | relation to 0136 (b) |
|---|---|---|
| Ha, Dai, Le 2016, HyperNetworks | A small network generates the weights of a larger one. | Origin of the mechanism. |
| Charakorn, Cetin, Tang, Lange 2025, Text-to-LoRA (Sakana; ICML 2025, PMLR 267); HyperLoRA (NeurIPS 2024 workshop, same group) | A hypernetwork writes a task LoRA in one forward pass from a text description. Trained by reconstruction of 9 existing LoRAs, or by SFT over hundreds of tasks; Mistral-7B average 73.9% with T2L vs 60.0% with no adapter (summary numbers). | The generator is trained on fixed human-made adapters or tasks. Not trained on its own verified outputs; no loop. |
| Liang et al. 2025, "Drag-and-Drop LLMs: Zero-Shot Prompt-to-Weights" (NeurIPS 2025) | Prompt batch -> text encoder -> hyper-convolutional decoder -> full LoRA; claims up to 12,000x lower overhead than fine-tuning and up to 30% over the training LoRAs on unseen benchmarks (authors' claims). | Same: one-shot generation from a fixed checkpoint collection. |
| Sakana 2026, Doc-to-LoRA (arXiv 2602.15902); SHINE (arXiv 2602.06358) | Hypernetworks trained with context distillation on mostly self-generated queries and the base model's own responses. | Closest to (b): self-generated TRAINING DATA for the generator. We found no iterative loop in which the generator retrains on adapters it generated and that a verifier accepted. Absence is from one search pass only, not a claim. |
| Zweiger et al. 2025, SEAL "Self-Adapting Language Models" (arXiv 2506.10943, NeurIPS 2025) | The model writes its own self-edits (data + update directives), the edits are applied by SFT, and RL on downstream reward improves the edit writer. SQuAD no-context 33.5 -> 47.0. | A loop in which the model improves its own weight-update writer, but via SFT on generated data, not one-shot weight generation. The nearest RSI precedent for (b). |

## What this means for 0136

- (d) is old as a mechanism (ExIt, AlphaZero). As far as this search found, the per-round trajectory of the gap between policy-only and searched reach in an LLM self-training loop is not reported. Measuring it on 0128's saved adapters is a measurement, not a new method.
- (b) as a closed loop (generator trained on its own verified adapters) was not found in one search pass. SEAL and Doc-to-LoRA are the closest. Any claim must say "we did not find", never "first".

Sources: arxiv.org/abs/1705.08439; lesswrong.com/posts/HAMsX36kCbbeju6M7; arxiv.org/abs/2407.06023; arxiv.org/abs/2312.06585;
arxiv.org/abs/2402.14083; sakana.ai/text-to-lora; proceedings.mlr.press/v267/charakorn25a.html; neurips.cc/virtual/2025/poster/116841;
arxiv.org/pdf/2602.15902; arxiv.org/pdf/2602.06358; arxiv.org/abs/2506.10943.
