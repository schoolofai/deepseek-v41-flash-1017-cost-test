# SCO-637 harness-vs-harness results

| Harness | Task | Status | Hidden tests | Model requests | Wall | Tokens in (cached) | Tokens out | Billed | Cost source |
|---|---|---|---|---|---|---|---|---|---|
| GPT-6.1 Sol in Codex CLI | t1_checkout_bugfix | solved | 30/30 | 8 | 1.8 min | 89,446 (71,817) | 5,491 | 10.6 cents | OpenRouter usage.cost per response; generation stats found for 8 of 8 requests |
| Claude Sonnet 5.5 in Claude Code | t1_checkout_bugfix | solved | 30/30 | 5 | 0.4 min | 101,828 (79,423) | 2,825 | 9.2 cents | OpenRouter usage.cost per response; generation stats found for 5 of 5 requests |
| Claude Sonnet 5.5 in Claude Code | t3_logstats_perf | solved | 8/8 | 4 | 1.0 min | 81,985 (64,092) | 6,149 | 11.3 cents | OpenRouter usage.cost per response; generation stats found for 4 of 4 requests |
| GPT-6.1 Sol in Codex CLI | t3_logstats_perf | solved | 8/8 | 15 | 7.3 min | 306,651 (271,602) | 17,233 | 28.7 cents | OpenRouter usage.cost per response; generation stats found for 13 of 15 requests |
| DeepSeek V4.1 Flash 1017 in OpenCode | t1_checkout_bugfix | solved | 30/30 | 6 | 0.5 min | 57,219 (47,744) | 3,837 | 0.4 cents | OpenRouter usage.cost per response; generation stats found for 6 of 6 requests |
| DeepSeek V4.1 Flash 1017 in OpenCode | t3_logstats_perf | solved | 8/8 | 19 | 4.0 min | 425,525 (408,192) | 21,037 | 1.6 cents | OpenRouter usage.cost per response; generation stats found for 19 of 19 requests |

Total billed: 61.8 cents
