| Variant | Runs | Input tok (mean) | Cached input (mean) | Output tok (mean) | Total (mean / p90) | Cost / run |
|---|---|---|---|---|---|---|
| agent-low | 88 | 7608 | 2530 | 836 | 8444 / 10781 | $0.00095 |
| agent-medium | 52 | 8356 | 2984 | 1338 | 9693 / 13145 | $0.00124 |
| baseline | 62 | 150 | 0 | 254 | 404 / 549 | $0.00014 |

**At scale (shipped app, agent-low, 4 runs per user per month)**

| Users | Runs / month | Tokens / month | Cost / month | Avg tokens / day* |
|---|---|---|---|---|
| 1 | 4 | 33,776 | $0.0038 | 1,126 |
| 100 | 400 | 3,377,640 | $0.3804 | 112,588 |
| 10,000 | 40,000 | 337,764,000 | $38.04 | 11,258,800 |

*The app-wide daily budget is 2,000,000 tokens; raise it for 10,000 users.

Low vs. medium reasoning effort: low uses 13% fewer total tokens per run (8444 vs. 9693) and 38% fewer output tokens (836 vs. 1338), the most expensive token type.

Forecast compaction: the raw hourly forecast is about 904 tokens; the summary the agent sees is about 132 tokens (Token counts estimated at ~4 characters per token.)
