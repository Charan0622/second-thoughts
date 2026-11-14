# Benchmark results

40 labelled scenario cards (`bench/cards.jsonl`).

| Method | Agreement with labels | Critical errors (said BUY when label = WAIT) | Median latency | Cost / verdict |
|---|---|---|---|---|
| Drex council (ours, 4 selves + veto + negotiation) | 28/40 (70%) | 0 | 0.59 s | $0.00071 |
| Single Drex call, all docs | 13/40 (32%) | 0 | 0.32 s | $0.00031 |
| Single frontier LLM call (Qwen/Qwen3.8-Max) | 13/40 (32%) | 0 | 1.82 s | $0.00127 |
| Frontier-LLM council (4× Qwen/Qwen3.8-Max, same pooling) | 16/40 (40%) | 0 | 2.08 s | $0.00236 |
