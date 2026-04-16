# MCP Framework — Claude / Agents / MCP Enhancement Recommendations

*Prepared April 15, 2026*

This document synthesizes research on recent Anthropic releases (Claude Agent SDK, Managed Agents, MCP ecosystem, prompt caching, extended thinking, batch API) into concrete, prioritized recommendations for the MCP Framework (Karma Marketing's blog + chatbot + lead platform).

---

## Executive Summary

Four changes would meaningfully cut cost, improve quality, or reduce maintenance burden across the platform:

1. **Prompt caching on blog system prompts** — 30-50% input-cost reduction on the highest-volume feature, ~1 day of work.
2. **Batch API for scheduled / bulk blog generation** — stacks with caching, up to 50% additional discount on non-realtime jobs.
3. **Migrate `agent_service.py` to the Claude Agent SDK** — replaces ~600 lines of custom agentic-loop code with a supported harness, gets compaction/streaming/MCP for free.
4. **Wrap WordPress + CallRail + SendGrid as MCP servers** — makes every tool reusable by the chatbot, blog agent, and future automations, and plays nicely with Claude Managed Agents.

A fifth, lower-priority item — **extended thinking for fact-check and "premium" blog mode** — improves quality at a known cost and should be gated per-client.

---

## 1. Prompt Caching (Highest ROI, Lowest Risk)

### What it is
Anthropic's prompt caching lets you mark chunks of a prompt as cacheable. Subsequent calls that reuse that prefix pay ~10% of the normal input token cost for the cached portion (90% discount). The cache lives for 5 minutes by default, extendable to 1 hour on most models.

### Why it fits us
The blog generation system prompts in `app/services/blog_ai_single.py` are long (brand voice, tone guidelines, SEO rules, examples). Every blog call re-sends the same preamble. Same story with the chatbot `system_prompt` built in `chatbot.py` — it embeds the full business description, services list, hours, FAQs.

### Where to apply it

| Call site | Cacheable prefix | Estimated savings |
|---|---|---|
| `blog_ai_single.generate_blog()` | System prompt + brand voice + few-shot examples | 40-60% of input cost |
| `chatbot.py` chat handler | Business context + service descriptions + FAQs | 50-70% of input cost (chatbots reuse context aggressively) |
| `fact_check_service.py` | Evaluation rubric + examples | 30-50% |
| `agent_service.py` tool definitions | Tool schemas (they never change within a run) | 20-30% |

### Implementation shape
```python
# In the Anthropic SDK call:
messages = [...]
system = [
    {
        "type": "text",
        "text": STATIC_BRAND_VOICE_PROMPT,
        "cache_control": {"type": "ephemeral"}   # <-- mark as cacheable
    },
    {
        "type": "text",
        "text": dynamic_client_context,  # changes per call, NOT cached
    }
]
```

Cache hits/misses show up in `response.usage` as `cache_creation_input_tokens` and `cache_read_input_tokens` — already trackable through our existing `token_tracker.py`. Minor edit to `track_usage()` to log these fields would let us measure the actual savings on the dashboard.

### Effort: ~1 day
### Risk: Very low — purely additive; if cache is cold, you pay normal price.

---

## 2. Batch API for Scheduled & Bulk Generation

### What it is
Anthropic's Batch API runs non-urgent jobs at 50% off. Combined with prompt caching, marketing teams have reported 90-95% total spend reduction on bulk content pipelines.

### Why it fits us
Two workflows in this codebase are ideal candidates:
- **Scheduled blog generation** — anything queued through `scheduler.py` that doesn't need immediate delivery
- **Bulk blog regeneration** — the "regenerate all" operations in `client-dashboard.html`

Real-time features (chatbot, single "generate now" click) should stay on the synchronous API.

### Implementation shape
- New service: `app/services/batch_blog_service.py`
- Submits jobs via `client.messages.batches.create(...)`
- Background poller (leverage existing `scheduler.py`) checks status, writes results to `DBBlogPost` when complete.
- UI surface: dashboard gets a "Queue (economy)" vs "Generate now" toggle.

### Effort: 2-3 days
### Risk: Low — fallback to synchronous API on batch failure.

---

## 3. Migrate `agent_service.py` to Claude Agent SDK

### Current state
`agent_service.py` implements a custom tool-loop: read tool definitions, call Claude, parse tool_use blocks, execute, loop. It's ~600 LOC of harness code we maintain ourselves. It doesn't support streaming, compaction, sub-agents, or parallel tool calls.

### What the Agent SDK gives us for free
- **Automatic tool loop** — no more manual `while response.stop_reason == "tool_use"` scaffolding
- **Context compaction** — long-running agents auto-summarize old turns instead of hitting context limits
- **Streaming** — partial output to dashboard while the agent works
- **Parallel tool execution** — Claude can request multiple tool calls in a single turn; SDK fans them out
- **Built-in MCP client** — any MCP server becomes a tool with zero glue code
- **Prompt caching on tool definitions** — handled automatically

### What stays the same
Our existing Python tool implementations (search blog DB, check CallRail, post to WordPress, etc.) plug in as tool callbacks. The business logic is unchanged.

### Bonus: Claude Managed Agents (launched April 8, 2026)
For workflows that run long (overnight SEO audits, multi-blog regeneration campaigns), Managed Agents offloads the infrastructure entirely — Anthropic hosts the agent, we poll for completion. Good fit for scheduled jobs. Probably not worth it for per-request features like the chatbot.

### Migration path
1. Keep `agent_service.py` working.
2. Build `app/services/agent_service_v2.py` using the SDK for a single low-stakes flow (e.g., the "analyze client content" background job).
3. Measure latency + cost + reliability for 2 weeks.
4. Migrate the rest flow-by-flow.

### Effort: 1 week for first migration, then ~2 days per additional flow.
### Risk: Medium — SDK is newer, but well-documented; fallback to v1 is trivial.

---

## 4. Wrap Our Integrations as MCP Servers

### Current state
WordPress posting, CallRail lead lookup, SendGrid notifications, Twilio SMS — each is a bespoke Python service called directly from features that need it. When the chatbot needs to look up a caller and the blog agent needs to publish a post, they use totally different code paths.

### MCP proposal
Package each integration as an MCP server. These become reusable across:
- Chatbot tool calls (`call_callrail_lookup`, `search_client_blogs`)
- Blog agent operations (`publish_to_wordpress`, `schedule_post`)
- Claude Code / Agent SDK workflows (us, internally, managing clients)
- External Claude Desktop usage — Rohit could point Claude Desktop at these servers to run client ops conversationally

### Suggested servers to build first

| Server | Tools | Consumers |
|---|---|---|
| `mcp-wordpress` | create_post, update_post, list_posts, upload_media | blog agent, dashboard automations |
| `mcp-callrail` | lookup_call, list_calls, transcript_fetch | chatbot, lead-triage |
| `mcp-clients-db` | list_clients, get_client, get_blog, list_leads | every agentic flow |
| `mcp-notifications` | send_email, send_sms | lead pipeline, scheduled reports |

### Why now
MCP crossed ~10,000 public servers this year and is adopted by OpenAI and Google, so the protocol is not going anywhere. Anthropic's Agent SDK speaks it natively. Once these are MCP servers, the "build a new agentic workflow" cost drops dramatically — you're composing tools, not writing integration code.

### Effort: 2-3 days per server. Start with `mcp-clients-db` (smallest surface, highest reuse).
### Risk: Low — MCP servers are plain HTTP/stdio processes; can coexist with existing direct calls.

---

## 5. Extended Thinking — Targeted, Gated Use

### What it is
Extended thinking lets Claude reason internally (hidden thought tokens) before producing its visible answer. Better on complex reasoning, multi-constraint content, and fact-checking. Costs more (thinking tokens billed as output).

### Where it helps
- **Fact-check pipeline** (`fact_check_service.py`) — catches subtle factual errors current model misses
- **"Premium" blog tier** — longer, research-heavy posts; clients paying for higher quality SKU
- **Compliance-sensitive industries** (legal, medical clients) — where hallucination cost is high

### Where NOT to use it
- Chatbot — latency hit is noticeable, content doesn't need it
- Short-form generation (meta descriptions, title tags)
- Anything already behaving well

### Implementation
Add a `thinking_mode` flag to blog generation config. Default off. Dashboard exposes it as a per-client or per-request toggle. Log thinking token counts separately in `token_tracker.py` for cost visibility.

### Effort: 1-2 days (the API change is tiny; most of the work is UI + cost accounting).
### Risk: Low if gated; high if always-on (cost blow-up).

---

## Suggested Sequencing

**Week 1:** Prompt caching on blog + chatbot system prompts. Instrument cache_read/create tokens in `token_tracker.py`. Ship.
**Week 2:** Batch API for scheduled blog jobs. Dashboard "economy" toggle.
**Week 3-4:** First MCP server (`mcp-clients-db`), consumed by a new Agent SDK prototype for the content-analysis flow.
**Month 2:** Migrate the biggest `agent_service.py` flow to Agent SDK. Build `mcp-wordpress`.
**Month 2-3:** Extended thinking for fact-check + premium blog tier, gated per-client.

---

## What I'd leave alone (for now)

- **Computer use** — not a fit for any current feature; adds attack surface.
- **Full rewrite of `blog_ai_single.py`** — prompt caching captures most of the gain without touching the logic.
- **Switching to Opus as default** — 5x the cost of Sonnet; reserve for extended-thinking premium tier only.
- **Multi-agent orchestration (sub-agents spawning sub-agents)** — real but operationally heavy; revisit once the single-agent Agent SDK migration is solid.

---

## Expected cost impact

Rough order-of-magnitude, assuming current spend profile (majority blog generation, secondary chatbot):

| Change | Input cost | Output cost | Total monthly impact |
|---|---|---|---|
| Prompt caching | -40% | 0% | **~-25%** |
| Batch API (scheduled only) | -50% on batched | -50% on batched | **~-10% additional** |
| Extended thinking (premium tier only) | 0% baseline | +15-30% on opted-in clients | net-neutral to slight increase if priced correctly |
| Agent SDK migration | -5% (caching on tool defs) | 0% | **-3%** |

Combined realistic estimate: **~30-40% reduction in overall Anthropic spend** with no quality loss, plus a platform that's easier to extend.
