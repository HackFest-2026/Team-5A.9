# Plan: context-aware follow-ups in the in-app VACP chat

Status: plan only, written 2026-10-11 by agent CTX. No code was changed. Audience: the hackathon team; pick tasks from section 7.
Scope: the ERPNext Desk bridge first (`VACP/packages/examples/erpnext-bridge`), then the parts that are shared (debug-ui chat module, `agent-client`) and the Metasfresh and WWI apps.

Paths are relative to `VACP/packages/` unless they start with `/`. Short names: **chat** = `lib/tooling/debug-ui/src/overlay/modules/chat`, **client** = `lib/transports/agent-client/src`, **erp** = `examples/erpnext-bridge/src`.

## 0. Recommendation in 3 lines

1. Keep the full message history and fresh `vacp_state` (cheapest, already works for simple ellipsis), but add one new thing: a **code-built `ConversationContext` block**, injected ephemerally into the last user message on every send. It holds the fresh screen, what the user changed by hand since the agent last acted, and a compact record of the last queries (normalised params, headline figures, ranked names).
2. Replace blind 1200-char truncation of old tool results with an **app-supplied digest**, and stop making the model re-read `vacp_capabilities` on every follow-up (the context block carries a compact action list).
3. Harden the query layer first (unknown params must be an error, echo the params actually used, add a `scope_hash`), and **measure** with a multi-turn extension of the KPI harness (28 conversations, section 6) before and after every step. Defer query rewriting and history retrieval.

## 1. What the model has on a follow-up turn today

| Question | Today (code) |
|---|---|
| **System prompt** | Static, built once per runtime. `client/instructions.ts:3-23` (generic "VACP protocol assistant") plus the interaction-policy sentences `:39-45`. The chat passes **no app instructions** (`chat/configured-chat.tsx:210-220` calls `createVacpChatRuntime` without `instructions`). Policy: at least 2 tool calls per turn, and "verify with vacp_state before the final answer" (`configured-chat.tsx:32-36`). The ERPNext `guidance` array is **not** in the prompt; it only reaches the model inside the `vacp_state` summary (`erp/bridge.ts:1088-1095`), so the model sees it only if it calls `vacp_state`. |
| **Tools** | Three generic tools: `vacp_capabilities`, `vacp_state`, `vacp_execute` (`client/vacp-tools.ts:162-243`). Every `erpnext.*` action is called through `vacp_execute(name, params)`. |
| **History sent** | Every UI message of the thread, including tool calls and results, after compaction (`client/context-compaction.ts:210-250`, wired at `client/create-vacp-agent.ts:104-112`). Defaults `:7-14`: `maxTurns 8`, `preserveFullToolPayloadTurns 2`, `maxTextCharsPerPart 1600`, `maxToolJsonCharsPerPart 1200`. |
| **What compaction does** | Only the **last 2 assistant messages** keep tool payloads whole (`:177-179`, applied `:138`). Every older tool part becomes one text line `Tool x \| state \| callId \| input=<json> \| output=<json>` with each JSON string **cut at 1200 characters** (`:49-67`, `toJsonPreview :29-37`; the cut is mid-JSON and appends `...`). Text is cut at 1600. Reasoning is kept for the last turn only (`:126-130`). `maxTurns` does **not drop** old messages: beyond 8 user turns it only strips reasoning and non-text parts (`:153-160`, `:146`). There is no token counting anywhere (grep: no `contextWindow`/trim logic); the only hard cap is 200 stored messages per thread (`chat/chat-store.ts:12,262`). |
| **App state** | Not injected. The model must call `vacp_state`; each call runs the bridge `getState`/`getSummary` fresh (`gateway/.../create-runtime-bridge.ts:114-119,375-377`; ERPNext reads the screen at most every 2.5 s, `erp/bridge.ts:1003-1050`). So state is fresh **when asked for**, but nothing forces the model to ask before reasoning from memory. The system prompt tells it to use `since` tokens / deltas (`instructions.ts:10`); a delta against a token whose baseline was compacted away is hard to read. |
| **Human changes between turns** | The runtime records observed changes in its history (`create-runtime-bridge.ts:377`, source `system`), and the ERPNext bridge refreshes on pushState/popstate (`erp/bridge.ts:1101-1115`). **None of this reaches the model.** It learns of a manual change only if it calls `vacp_state` and notices the difference from its memory. |
| **Step and output limits** | Agent loop stops at `stepCountIs(maxSteps)`: default 8 (`create-vacp-agent.ts:9,88`), seeded to 10 for ERPNext (`erp/bridge.ts:1140`, only when no chat config is stored, `:1132`). Temperature 0.2. `maxOutputTokens` 4096 (seeded). |
| **Thread persistence** | Zustand + `localStorage` key `vacp:debug:chat:history:v1`, up to 30 scopes x 20 threads x 200 messages, tool payloads included (`chat-store.ts:9-13,387-402`). The thread id is keyed by `scopeId`, which contains the URL unless the app pins `window.__VACP_CHAT_SCOPE_KEY` (`chat/chat-scope.ts:14-21,46-50`). ERPNext (`erp/bridge.ts:786`) and Metasfresh (`metasfresh-webui-bridge/src/bridge.ts:297`, dashboard `main.tsx:29`) pin it, so the thread survives SPA navigation and reloads **on the same origin** (localStorage is per origin: `10.9.0.108:8081` and `100.71.58.43:8081` are different threads and different LLM configs). **The WWI dashboard does not pin it** (grep: no `__VACP_CHAT_SCOPE_KEY` in `wwi-dashboard/src`), and its state lives in the URL hash, so by code reading each agent action that changes the hash opens a fresh empty thread. To verify in a browser; if confirmed, in-app follow-ups in WWI are broken by construction (the WWI harness does not test the in-app chat, so it never saw this). |
| **Regenerate / clear** | "Regenerate last answer" (`configured-chat.tsx:557-563`) and `clearThread` (`chat-store.ts:301-327`, bumps `sessionRevision`) change the history but nothing app-side knows. Any bridge-side memory must follow them (risk R2). |

### Probe evidence (text-only, relay `nemotron-3-super`, about 38 single model calls, no key sent)
Fixtures are synthetic but shaped like the real `erpnext.query` envelope (`{callId, ok, result:{... desk_view}}`), and I re-implemented the old-turn summarising from `context-compaction.ts:49-67`. n=1 per cell, temperature 0.2: anecdotal, to be replaced by the harness. Scripts: scratchpad `probe.py`, `loop.py`, `loop2.py`, `p3.py` (not kept in the repo).

| # | Probe | What happened |
|---|---|---|
| 1 | Full history, April-2016 summary then "and for May?", "how does that compare to last year?", "no, I meant April 2015" | Correct `erpnext.query` params on the first step in 3/3 (right kind, correct month or year). So the plain (i) design already handles simple ellipsis, corrections and comparison. |
| 2 | Old turn compacted, "same for 2014 please" after two unrelated turns | Correct (`top_customers`, 2014, `by amount`, limit 10) with and without a context block: the compacted line still shows the `input=` JSON. |
| 3 | Same, but "what was the 10th customer's value in 2015?" (1200-char cut leaves 8 of 10 rows in my fixture) | Without context: it **re-queried** (correct, faithful, but one more slow call; the docs measure about 5 s for a one-year group-by). With a context block holding the ranked rows: it answered from turn 1 and wrote "(from turn 1)". Fast, but this is exactly the reuse of an earlier number that the answer gate must be able to police. |
| 4 | Compacted history, 11 runs | The first tool call was `vacp_capabilities` in **6 of 11** (the action list was cut away by compaction); 0 of 1 with full history. Each is one extra step on every follow-up. |
| 5 | "same but only completed ones" | The model sent `{"kind":"summary","start":...,"filters":{"status":"Completed"}}`. `filters` is not an `erpnext.query` parameter. `erpQuery` runs it anyway and only lists the key in `ignored_params` (`erp/query.ts:580,604,649`): the answer would be the **unfiltered** April count. A silent wrong-scope risk that context alone cannot fix. |
| 6 | Desk changed by hand (filters now `status=Completed`), history says "Sales Invoice list, April 2016"; "what filters are on right now?" (3 variants, with and without a context block that says "may be stale") | The model called `vacp_state` first in all 3 and reported the new filters. Explicit screen questions are fine; the untested, riskier case is an **implicit** dependence ("how many are there?"), which is conversation C26 below. |
| 7 | "what about revenue?" | First step was `vacp_state`; no clarification seen yet (single step, inconclusive). |

Two earlier runs (an ellipsis after two unrelated turns, with a context block that named the wrong "last query") were badly designed on my side (the fake tool returned one fixture for every call) and are discarded.

## 2. Follow-up types to support (ERPNext data)

Figures are from `examples/erpnext-bridge/docs/doctype-map.md` (submitted documents). Period defaults: omitted dates mean all dates; the dataset ends 2016-05-31 and invoices end 2016-02-24.

| Type | Example conversation | Expected agent behaviour | Today |
|---|---|---|---|
| **(a) Ellipsis / refinement** | U1 "How many sales orders in April 2016, and what do they add up to?" -> A1 1,951 / USD 5,437,763.60. U2 "and for May?" -> 2,048 / 5,898,846.49. U3 "same but only completed ones". U4 "same top-5 list but by number of orders" | Inherit `kind`, `source`, filters and the way of showing it; change only what was named. Re-query for every new scope; never carry numbers. Put the answer on screen (`show_in_desk`). Say which parameters were inherited. | Simple cases work (probe 1). "only completed" put `status` into a bogus `filters` key (probe 5). Switching source into an empty range (invoices after 2016-02-24) needs a coverage note. |
| **(b) Reference resolution** | "Top 5 customers in 2015" -> "open the first one" -> "how many orders do they have in 2015?" | Resolve "first", "they", "that customer" against the **last ranked list or opened record**, passing the exact name (`Knut Svensson`), then `open_record`/query. If the antecedent is not unique ("open that customer" after a 5-row list) ask which one (rank or name). | Works while the row is still visible (probe 2); ranks 9-10 are lost after compaction; `open_record` entity casing was `Customer` vs the enum `customer` (probe, one run). |
| **(c) UI-state-relative** | "filter this list by customer Knut Svensson" / "remove only that filter" / "go back" / "what am I looking at?" / "what filters are on?" | Act on the **current** list (read fresh), report the real filters and `total_rows` from the screen (not from memory). "Go back" returns to the previous screen **with its filters and page**. Removing one filter keeps the others. | `set_filters` and `set_period` act on the current list (`bridge.ts:844-881`). **No `back` action; `clear_filters` has no parameters** (`:883-891`), so "remove only X" is not expressible. `erpnext.navigate` silently drops the user's filters (`openList` resets them, `bridge.ts:483`). |
| **(d) Corrections** | "Top 5 customers in 2014" -> "no, I meant 2015" -> "and the month after"? (see C17) | Redo with the corrected slot, drop the wrong result, and **propagate the correction** to later relative references ("the month after" is relative to the corrected period). | Works for the immediate case (probe 1); propagation untested. |
| **(e) Comparison with the previous answer** | "How many orders in April 2016?" -> "how does that compare to last year?" | Reuse the earlier figure only for the identical scope, else re-query; query April 2015; compute the difference and percent in code or cite the formula; label both periods and the source. | Works (probe 1) but the delta arithmetic is done by the model. A `compare` query kind would remove that (task T2.4). |
| **(f) Ask, do not guess** | "How many orders last month?" (today 2026-10, data ends 2016-05). "What was our revenue in April 2016?" (ERPNext has `grand_total` incl. tax and `net_total`, no "revenue"). "Show Tailspin Toys' orders" (many branches: `Tailspin Toys (Tolna, ND)` ...) | One short question with 2-3 concrete options and the default stated, or an explicit stated assumption in the first line. Never act on a guess that changes the screen. After the user answers, finish the original request. | Not enforced anywhere (no prompt rule, probe 7 inconclusive). The WWI/ERPNext guidance never says when to ask. |
| **(g) Topic switch / reset** | "Top 5 customers in 2015" -> "forget that, how many suppliers do we have?" -> "and items?" | New question, no inherited period/filters (13 suppliers, 228 items, no 2015). "And items?" follows the **latest** topic. If an inheritance is ambiguous, state what was carried over. | Model-dependent. Risk is "context bleed" (a 2015 period leaking into a list that has no date). Needs a test and a prompt rule. |
| **(h) User changed the Desk by hand** | Agent shows April 2016 orders; the user clicks status = To Deliver and Bill; U2 "how many are there?" | Notice that the screen differs from the end of the last agent action, say so ("I see you filtered to To Deliver and Bill"), answer for what is **on screen now**, never the remembered 1,951. If the request conflicts with the screen ("and for May?" while the user moved the period to 2015) say which year it assumes or ask. | Only if the model happens to call `vacp_state` and compare (probe 6). Nothing tells it a change happened. |

## 3. Design options

| Option | Cost per turn | Latency | Failure modes | Interaction with the answer gate / faithfulness | Verdict |
|---|---|---|---|---|---|
| **(i) History + fresh `vacp_state`** (today) | none | 0 | Model must remember to read state; compaction cuts rows and the action list (probes 3, 4); no signal for manual changes; unknown params pass silently | Old numbers are in history as truncated text; the gate cannot verify a citation of a cut result | Keep as the base; fix its two defects (digest, no capabilities re-read) |
| **(ii) Structured `ConversationContext`**, built by code, injected each send (and optionally readable as `erpnext.context`) | +300-600 tokens; one bounded screen read at send time | +0.2-1.5 s (screen read, timeout 1.5 s), no extra LLM call | Over-trust of the block (probe 3, with-context case); block can diverge from the thread after regenerate/clear (R2); stale screen if the read times out | Fits: every figure in the block carries `from_turn`, `call_id`, `scope_hash`, so the gate can accept a reuse only for an identical scope and a fresh revision, and reject the rest | **Primary** |
| **(iii) Rewrite follow-up into a standalone question** (extra LLM call) | +1 call | +1.3 s (gpt-oss alone) to +11-15 s (Nemotron / DeepSeek under the shared deployment, RESULTS.md) | The rewrite itself can invent a slot (a year), and then the agent loops on an utterance the user never wrote; it blocks clarification (the agent can no longer see the original ambiguity); doubles the failure surface | The rewritten text would enter the gate's "numbers in the prompt are allowed" pool: a fabricated year becomes "grounded" | **Defer**; only as a fallback if (ii) measures badly |
| **(iv) Retrieval over graph / history** | embeddings + index | +0.3-1 s | Over-engineering for threads of at most 8-10 turns; the app graph has 4 nodes and 8 actions | Neutral | **Defer** (needed only for the "hundreds of components" retrieval KPI, FUTURE_FIXES #15) |

**Why (ii).** Probe 1 shows the model already resolves most ellipsis from history; what history does not give it is (1) a reliable view of the screen **as of this send**, (2) knowledge that the user changed it, (3) a lossless record of the last queries, (4) the action list without a re-read, and (5) a rule for when to ask. All five are facts the bridge knows and the model can only infer. Building them in code costs no LLM call, keeps the prompt prefix stable (the block is appended to the last user message, not the system prompt, so provider prompt caching of the long prefix still works), and gives the answer gate structured provenance to check, which a free-text summary written by the model would not.

## 4. Design details

### 4.1 Where each piece lives

| Piece | File / package | Shared or app-specific |
|---|---|---|
| Context hook: `window.__VACP_CHAT_CONTEXT = async ({turnIndex, previousSendAt}) => ({text, data})`, called on each send; the text is appended as one extra text part of the **last user message** in the copy sent to the model (never stored in the thread) | `client/context-compaction.ts` (the wrapper `sendMessages`, `:222-249`) takes an optional `contextProvider`; `chat/configured-chat.tsx:210-220` passes `() => window.__VACP_CHAT_CONTEXT?.(...)` | **Shared**, feature-flag: no global set -> no behaviour change for other apps |
| Digest hook: `window.__VACP_CHAT_DIGEST = (toolName, input, output) => string \| undefined` used by `summarizeToolPart` (`:49-67`) for tool parts older than the last 2 assistant messages; fall back to today's truncation when it returns nothing | `client/context-compaction.ts` | Shared mechanism, app-specific digests |
| App instructions: `window.__VACP_CHAT_INSTRUCTIONS` appended to `buildVacpAgentInstructions` (`instructions.ts:48-55`) for the follow-up rules (4.4); today the chat can pass none | `client/instructions.ts`, `configured-chat.tsx` | Shared hook, app text |
| Relax the forced "at least 2 tool calls" when the context says the answer is in the previous turn ("summarise that", "why?") | `configured-chat.tsx:32-36` | Shared (small) |
| `ConversationMemory` + `buildContext()` + digests + `scope_hash` | **new** `erp/context.ts`; wrap each `erpnext.*` handler (`erp/bridge.ts:798-982`) in a `recorded()` helper; register the three window globals in `install()` next to `:779-786` | ERPNext-specific; Metasfresh/WWI copy the ~150-line file with their own screens |
| Screen signature + user-change detection | `erp/context.ts`: `signature = hash(route, doctype, filters, page, docname)` taken at the **end of every agent action**; at send time compare with the live signature (reuse `screenState`, `bridge.ts:1004-1050`). No Frappe event hooks needed | ERPNext-specific. A generic version can later diff `runtime.history` entries not sourced `agent` (`create-runtime-bridge.ts:317,377`) |
| Query hardening: unknown params -> `ok:false`; echo `params_used`; add `scope_hash` | `erp/query.ts:580,604-652` | ERPNext query layer; same idea for `metasfresh.query` and `wwi.query` |
| New actions: `erpnext.back` (screen stack of route+filters+period+page, depth 10), `erpnext.clear_filters {fields?}`, read-only `erpnext.context` for MCP clients (no chat injection there) | `erp/bridge.ts` | ERPNext-specific |
| Follow-up suggestion chips after an answer, from the last query (deterministic, no LLM): "Same for 2014", "Only Completed", "Open #1" | `chat/chat-messages.tsx:15-19` today only has empty-state starters; add `window.__VACP_CHAT_FOLLOWUPS` | Shared hook, app content |
| WWI: pin `__VACP_CHAT_SCOPE_KEY` | `wwi-dashboard/src/main.tsx` | WWI |

### 4.2 Data shapes (`ChatContext v1`, JSON, cap about 600 tokens)

```jsonc
{
  "v": 1, "as_of": "2026-10-11T09:14:02Z", "turn": 4,
  "today": "2026-10-11", "data_range": {"first": "2013-01-01", "last": "2016-05-31", "invoices_last": "2016-02-24"},
  "screen_now": {                       // read at send time, 1.5 s timeout, else {"unavailable":"timeout"}
    "kind": "list", "doctype": "Sales Order", "url": "/app/sales-order?...",
    "filters": [{"field":"transaction_date","op":"Between","value":["2016-04-01","2016-04-30"]},{"field":"status","op":"=","value":"To Deliver and Bill"}],
    "period": {"start":"2016-04-01","end":"2016-04-30"}, "total_rows": 372, "page": 1, "signature": "s_9f2c"
  },
  "user_changed_screen_since_last_agent_action": {
    "changed": true, "diff": ["filter added: status = To Deliver and Bill"], "last_agent_signature": "s_41aa"
  },
  "last_queries": [                      // newest first, max 5; params are the NORMALISED ones the bridge actually ran
    {"id":"q3","turn":3,"call_id":"c7","age_s":41,
     "params_used":{"kind":"summary","start":"2016-05-01","end":"2016-05-31","source":"orders","docstatus":"submitted"},
     "scope_hash":"h_55e0",
     "headline":{"sales_orders":{"count":2048,"grand_total":5898846.49}},
     "ranked":null, "shown_in_desk":{"shown":true,"matches_query":true,"view":"List Sales Order"}}
  ],
  "entities": {"customer":"Knut Svensson","item":null,"record":{"entity":"sales_order","name":"SAL-ORD-2026-00001"},
               "last_ranked":[{"rank":1,"name":"Knut Svensson","value":173306.72},{"rank":2,"name":"..."}]},
  "actions": ["erpnext.navigate{view}", "erpnext.set_filters{filters}", "erpnext.query{kind,start,end,customer,item,status,by,source,limit,...}", "..."],
  "defaults": {"period":"all dates","docstatus":"submitted","currency":"USD","amount_field":"grand_total (incl. 15% tax)"},
  "rules": ["Numbers in last_queries are from earlier turns: restate one only if the new question has the same scope_hash and age_s < 600, and say 'from turn N'; otherwise re-query.",
            "If user_changed_screen... is true, start from screen_now, not from your memory of the screen; say what you saw changed.",
            "screen_now is as of the start of this turn; after any action read the screen again."]
}
```

`scope_hash` = stable hash of `{kind, period, source, filters, docstatus, by, limit}`; `params_used` is added to the `erpnext.query` result so the digest, the gate and the harness all read the same normalised params. `pending_clarification` is deliberately **not** in v1: the unanswered question is the last assistant message and is always kept verbatim (text cut is 1600 chars). It is logged by the harness instead.

### 4.3 Token budget and truncation rules
- Context block: hard cap 600 tokens (about 2,400 chars). Drop order when over: `entities.last_ranked` beyond 10 rows, then queries older than the 3 newest, then `actions` (replaced by "see vacp_capabilities").
- Old tool results (older than the last 2 assistant messages) become digests, not 1200-char cuts. Digest for `erpnext.query`: `params_used` + `scope_hash` + `call_id` + headline + ranked rows `rank,name,value` (max 25 rows x about 14 tokens) + `desk_view.{shown,matches_query,view}`; **drop** `desk_view.visible_rows`, notes and the `source` line. Target at most 500 chars for headline queries, 1,500 for rankings. `vacp_capabilities` outputs older than the last turn become "(action list: names only)". `vacp_state` outputs older than the last turn become one line (`screen`, `filters`, `total_rows`).
- Add a rough character budget in the wrapper (about 4 chars/token) with a configurable window (default 24k tokens for 32k models): when over, shrink oldest digests first, never the last 2 turns, never a result referenced by `last_queries`. Also read `usage.inputTokens` from the previous step (the metadata exists, `create-vacp-agent.ts:48-75`) and warn the user near 80% (FUTURE_FIXES #8).
- Keep full results out of the model's view but **in a side store** (`result_store[call_id]` in the bridge, and in the harness) so the gate verifies citations against the full result even when the model only sees the digest. This avoids the "evidence stripping" failure seen with the gate (RESULTS.md finding 4): if a claim cites `c7.rows[0].grand_total` the field must be recoverable.

### 4.4 Prompt rules to add (via `__VACP_CHAT_INSTRUCTIONS`, about 10 lines)
Resolve "it/same/those/the Nth one/they" against `last_queries` and `entities`; change only the slot the user named and list the inherited ones in the answer; ask once, with 2-3 options and a default, when a period, a measure ("revenue": ERPNext has `grand_total` and `net_total` only) or an entity is ambiguous, and do not act in that turn; start a fresh scope on an explicit topic switch ("forget that", a new entity type) and say what, if anything, is carried over; do not call `vacp_capabilities` again (the action list is in the context); never put filters in a made-up parameter (use the parameters listed in the action).

### 4.5 Guardrails
- **No stale numbers as fresh:** a number may be restated only from a `last_queries` entry with identical `scope_hash`, `age_s` under 10 min and the label "from turn N"; everything else is re-queried. The harness measures this (`stale_reuse`), and the gate (when ported, FUTURE_FIXES #12, and after the hybrid-gate fix #4) treats a context-sourced number as citable only under the same rule, using `call_id` + `scope_hash`, plus the revision stamp from FUTURE_FIXES #7.
- **Re-query when the Desk was changed by the user:** if `user_changed_screen_since_last_agent_action.changed`, any screen-relative question ("how many are there", "filter this list", "next page") must start from a fresh `vacp_state`/action outcome and cite it; queries about a named scope ("orders in May") are unaffected.
- **Read-only and confirm before overwriting:** the bridge stays read-only. Navigation and filters are reversible and need no confirmation, but an action that would **discard the user's manual filters** (`navigate`, `clear_filters`, `set_period` on a list the user filtered by hand) must say so in its outcome (`replaced_user_filters`) and the prompt rule is "name what will be dropped"; whether to ask first is open question Q3.
- **Unknown parameters are errors** (`ok:false`, message lists the valid parameters), never `ignored_params`.
- **Context can be wrong, the screen cannot:** `screen_now` is labelled "as of the start of this turn"; the rules require re-reading after any action. The context block is advisory; actions still validate everything themselves.

## 5. What differs for the other apps

| App | Chat scope | Screen read | Query tool | Work needed |
|---|---|---|---|---|
| **Metasfresh WebUI bridge** | pinned (`bridge.ts:297`) | `getState` reads the WebUI view, cached 2.5 s per URL (`:456-475`) | `metasfresh.query` over the dashboard SQL service (needs :5185) | Same `context.ts`; period is a single `periodRef`; two currencies, so `scope_hash` must include currency; no filters beyond the period, so the user-change signature is URL+period+page |
| **WWI dashboard** | **not pinned** (see section 1) | `getState` from the zustand store (`wwi-dashboard/src/vacp.ts:329-348`), always fresh | `wwi.query` | Pin the scope key; context from the store (`period`, `filters`, `scenario`, `scope`); `wwi.*` results already return applied scope and 5-row previews, so digests are short. The answer gate already exists in the harness (`eval/answer_gate.py`) |

The shared hooks (4.1) make each app a ~150-line provider; nothing app-specific goes into `debug-ui` or `agent-client`.

## 6. Evaluation

### 6.1 Harness
Extend `examples/metasfresh-webui-bridge/eval/run_kpi_eval.py` style into `examples/erpnext-bridge/eval/run_multiturn_eval.py` (no ERPNext eval exists yet; the Metasfresh harness is the template: SQL oracle through `docker exec`, Playwright final-state check, tools from `getCapabilities` plus `vacp_state`, `--resume`, `--rescore`, `--only`). Two lanes:
- **Lane A (fast, many models/arms):** a conversation is a list of user turns plus optional `human` events between turns. The harness carries the message list across turns, applies a Python port of the real compaction (`context-compaction.ts`, 60 lines) and the same context/digest providers (call the bridge globals through `page.evaluate`, so the harness and the product use the same code), and uses the **in-app tool shape** (`vacp_capabilities/state/execute`), not the per-action tools the current harness exposes. The system prompt is the in-app one, not the harness's own.
- **Lane B (product smoke, 8 conversations):** Playwright types into `#vacp-chat-input`, waits on `[data-vacp-chat-status]` = Ready, reads the answer from the DOM and the tool events from `localStorage['vacp:debug:chat:history:v1']`. Slower and flakier, but it tests the real thread store, persistence, compaction and injection. Also covers reload mid-conversation (R3).
`human` events are performed by the harness through the real Desk UI (set a filter via the list's filter area, navigate with the sidebar), not through bridge actions, so the bridge sees a genuine manual change.

Arms (run one model at a time, 3 repeats each, because task-level noise was about +-3 of 38 in RESULTS.md): **A0** today; **A1** + query hardening + digests; **A2** + context block + app instructions; **A3** + `back`/`clear_filters{fields}`/compare. Models: `nemotron-3-super` (in-app default), `gpt-oss:120b`. DeepSeek is out (text protocol cannot drive the in-app chat, CLAUDE.md).

### 6.2 Conversations (28, types a-h)
Oracle shorthand (MariaDB, run at test time; `docstatus=1`): `SO(a,b[,x])` = `count(*), sum(grand_total)` from `tabSales Order` where `transaction_date between a and b`; `SI` likewise with `posting_date`; `TOPC(a,b,by)` = group by `customer`, order as `query.ts` does (`amount|n desc, other desc, name asc`); `TOPI(a,b,by)` = `tabSales Order Item` joined to the parent. Known values from `docs/doctype-map.md` are written out; the rest are computed. `[H]` = human action performed by the harness between turns. "Screen" = final-state check on the live Desk (route, filters, `db.count`, page).

| ID | Type | Turns | Expected (oracle) |
|---|---|---|---|
| C01 | a | 1 "orders in April 2016, and total?" 2 "and for May?" 3 "and March?" | 1,951 / 5,437,763.60; 2,048 / 5,898,846.49; 1,969 / 5,516,385.27. Screen: SO list or report, period March 2016. T2 must not contain 1,951 as the answer |
| C02 | a | 1 "top 5 customers in 2015 by order value" 2 "same but by number of orders" 3 "now for 2014" | `TOPC(2015,by amount)`, then by orders (Knut Svensson 55, Tailspin Toys (Vassalboro, ME) 55, ...), then 2014. Screen: period 2014 |
| C03 | a | 1 "3 items sold the most units in April 2016" 2 "same by value" 3 "and in May?" | `TOPI(Apr,qty)`, `TOPI(Apr,amount)`, `TOPI(May,amount)`; the agent must say amount means line amount excl. tax |
| C04 | a/c | 1 "show sales orders for April 2016" 2 "only completed ones" 3 "page 2" | Screen: SO list, period April, `status=Completed`, page 2; `total_rows` = `count` with status Completed in April (differs from turn 1). No `filters` key in any query call |
| C05 | a | 1 "how many purchase orders in 2015?" 2 "and sales orders?" 3 "and invoices?" | `PO(2015)`, `SO(2015)` = 23,329, `SI(2015)`; period inherited, source switched, each answer names its document type |
| C06 | a/f | 1 "invoices in May 2016?" 2 "and February 2016?" | 0 with a coverage note (invoices end 2016-02-24); then `SI(Feb 2016)`, noting the month is partial |
| C07 | b | 1 "top 5 customers in 2015" 2 "open the first one" 3 "how many orders do they have in 2015?" | Screen after T2: Customer form `Knut Svensson`; T3 = `SO(2015, customer=Knut Svensson)` = 55 / 173,306.72 |
| C08 | b | 1 "which customer has the most orders overall?" 2 "show their orders for 2016" 3 "open the largest one" | Tailspin Toys (Tolna, ND) 150; T2 screen: SO list, that customer, 2016, rows = oracle; T3 screen: form of `max(grand_total)` order of that scope |
| C09 | b | 1 "top 3 items by units in April 2016" 2 "who buys the second one most?" | `TOPC(Apr 2016, item = rank-2 item)`; the agent must name the item it used |
| C10 | b | 1 "open SAL-ORD-2026-00001" 2 "which customer is that for?" 3 "show all their orders" | Customer from the record; T3 screen: SO list filtered to that customer, rows = oracle |
| C11 | b/f | 1 "top 5 customers in 2015" 2 "open that customer" | Asks which one (rank or name); **no** `open_record` call; then 3 "the third" -> opens rank 3 |
| C12 | c | `[H]` list SO, period Jan 2016, status Completed. 1 "what am I looking at?" 2 "what filters are on?" | Both answers list exactly the screen's filters and `total_rows` = oracle count; no remembered values |
| C13 | c | 1 "show April 2016 sales orders" 2 "filter this list to customer Knut Svensson" 3 "remove just the customer filter" | After T3: period April kept, customer filter gone, rows = `SO(Apr)`. Needs `clear_filters{fields}` (today inexpressible) |
| C14 | c | 1 "show sales orders for April 2016" 2 "open the first one" 3 "go back" | After T3: route = SO list **with April still applied** and the same page. Needs `erpnext.back` |
| C15 | c | 1 "show items" 2 "only the Toys group" 3 "how many are there?" | Screen: Item list, `item_group=Toys`, 3 rows; T3 = 3 |
| C16 | d | 1 "top 5 customers in 2014" 2 "no, I meant 2015" | T2 = `TOPC(2015)`; answer contains no 2014 name or value; screen period 2015 |
| C17 | d | 1 "orders in April 2016?" 2 "sorry, April 2015" 3 "and the month after" | `SO(Apr 2015)`, then `SO(May 2015)` (relative to the corrected period, not 2016) |
| C18 | e | 1 "orders in April 2016?" 2 "how does that compare to last year?" | 1,951 vs `SO(Apr 2015)`; difference and percent correct to 0.1; both periods named; no "revenue" |
| C19 | e | 1 "total order value in 2015" 2 "and 2014? which is higher?" | Both `sum(grand_total)` (USD, incl. tax) and the right direction |
| C20 | e | 1 "monthly order counts for 2016" 2 "which month was highest and by how much over the lowest?" | May 2,048 vs Feb 1,706, difference 342. Reuse from turn 1 allowed only if cited as turn 1 (tests the legitimate-reuse path) |
| C21 | f | 1 "how many orders last month?" 2 "May 2016" | T1: asks, or states the assumption "data ends May 2016" in its first line; T2 = 2,048 |
| C22 | f | 1 "what was our revenue in April 2016?" 2 "net" | T1: asks "order value incl. tax (grand total) or net?" or gives both labelled and does not use the word revenue as a fact; T2 = `net_total` 4,739,058.60 |
| C23 | f | 1 "show Tailspin Toys' orders" 2 "the one in Tolna" | T1: asks (many `Tailspin Toys (...)`), no filter set to the first match; T2 screen: customer `Tailspin Toys (Tolna, ND)`, rows = oracle |
| C24 | g | 1 "top 5 customers in 2015" 2 "forget that, how many suppliers do we have?" 3 "and items?" | 13; then 228; neither answer mentions 2015; screens have no date filter |
| C25 | g | 1 "SO list April 2016, Completed" 2 "now purchase orders" | The agent states what it carried (period yes/no, status yes/no) and the screen matches its statement (consistency check, not a fixed expectation) |
| C26 | h | 1 "show sales orders for April 2016" `[H]` filter status = To Deliver and Bill. 2 "how many are there?" | Answer = oracle count with that status (not 1,951) and mentions the filter in force |
| C27 | h | 1 "top 5 customers in 2015" `[H]` user opens the Items list. 2 "open the first one" 3 "filter this list to the Toys group" | T2 opens customer rank 1 (resolved from the answer, not the screen). T3 acts on the list now open (Customers after T2): it says that "Toys group" is not a Customer filter, or navigates to items first and says so; no wrong filter applied |
| C28 | h/f | 1 "show sales orders for 2016" `[H]` user sets the period to 2015. 2 "and for May?" | Either asks which year or states the year it used in its first line; the answer and the screen agree with the stated year |

### 6.3 Scoring (per turn, then per conversation)
| Check | Rule | KPI |
|---|---|---|
| `numbers` | every oracle number appears (same tolerances as `close()` in the Metasfresh harness) | analytical correctness |
| `screen` | final route/filters/period/page/row count match the oracle, read from the live Desk (as `final_state` does) | UI-state correctness, intent-to-destination |
| `no_stale_reuse` | a number in the answer that equals one from an earlier turn but is not an oracle value for this turn fails; reuse is allowed only when the tool log shows no new query **and** the scope hash is identical **and** the answer says "from turn N" (C20) | faithfulness |
| `grounded` | `ungrounded()` over the pool of this conversation's tool results (full results from the side store) | faithfulness |
| `re_read_after_human` | for `[H]` conversations: a `vacp_state` or action outcome after the event and before the answer, and the answer matches the post-event oracle | UI-state correctness |
| `asked_when_needed` | on "ask" turns: final text ends in a question with at least 2 options and **no** state-changing or query call in that turn (read-only `vacp_state` allowed); on "must-act" turns: no question | UX, near-zero action hallucination |
| `no_bad_action` | zero calls with unknown actions or parameters, zero `ignored_params`, no write-like intent accepted | action hallucination, recovery |
| `statement_screen_consistency` | what the answer says it filtered/carried equals the final screen (C25, C28) | UI-state correctness, explanation faithfulness |
| `cost` | steps, tool calls, `vacp_capabilities` re-reads, input tokens and seconds per turn, per follow-up turn vs first turn | multi-step success, steps and latency, UX |
| Conversation success | all flagged checks pass in every turn | multi-step task success |

Report: turn success and conversation success by type (a-h), follow-up turns vs first turns ("context gain"), per arm, with 3 repeats; written up as a new section in `eval_results/RESULTS.md` (and `compare_runs.py` groups). Held-out data rules from CLAUDE.md are unchanged: these conversations were written for this harness; the `holdout_tasks.jsonl` file is not read. Success targets to agree with the team (Q6): A2 at least +15 points conversation success over A0 on types b, c, h; zero stale reuse; clarification precision at least 80% on C11, C21-C23, C28.

## 7. Task list

Effort: S under half a day, M about a day, L 2+ days. Areas: **chat** (debug-ui / agent-client), **bridge** (erp), **query** (erp/query.ts), **tests** (harness).

| ID | Task | Area | Effort | Depends on |
|---|---|---|---|---|
| **Phase 0: measure and stop the silent errors** | | | | |
| T0.1 | Make unknown `erpnext.query` params an error; add `params_used` and `scope_hash` to the result; update `docs/check_query.mjs` and `test_erpnext_vacp.py` expectations | query | S | none |
| T0.2 | `run_multiturn_eval.py` skeleton (conversation spec, carry history, compaction port, in-app tool shape, `[H]` events, SQL oracle helpers) with C01, C04, C16, C26 | tests | M | none |
| T0.3 | Baseline arm A0 on `nemotron-3-super`, 3 repeats, on the first 8 conversations | tests | S | T0.2 |
| T0.4 | Browser checks (a person, not a script run by the planner): WWI thread reset on hash change; reload mid-turn (is a tool part left without output and does `compaction.ts:238-246` then break the thread?); localStorage quota with large tool payloads; two origins | chat | S | none |
| **Phase 1: shared mechanisms (feature-flagged, default off)** | | | | |
| T1.1 | `contextProvider` option in the compaction wrapper plus `window.__VACP_CHAT_CONTEXT` wiring in `configured-chat.tsx`; unit tests in `client/../test/context-compaction.test.ts` (injected into the sent copy, not stored, survives `sanitizeUiMessages`) | chat | M | none |
| T1.2 | `window.__VACP_CHAT_DIGEST` in `summarizeToolPart`; character budget with drop order (4.3); tests | chat | M | T1.1 |
| T1.3 | `window.__VACP_CHAT_INSTRUCTIONS` appended to the agent instructions; relax the forced 2-tool-call policy when the answer is in the previous turn | chat | S | none |
| T1.4 | Follow-up chips hook `window.__VACP_CHAT_FOLLOWUPS` | chat | S | T1.1 |
| **Phase 2: ERPNext bridge** | | | | |
| T2.1 | `erp/context.ts`: `ConversationMemory`, `recorded()` wrapper on all handlers, `buildContext()` (4.2), digests for `erpnext.*`, reset on `clearThread`/regenerate (use the chat's `sessionRevision` and message count) | bridge | L | T0.1, T1.1, T1.2 |
| T2.2 | Screen signature at end of each agent action and `user_changed_screen_since_last_agent_action` diff | bridge | M | T2.1 |
| T2.3 | `erpnext.back` (screen stack) and `erpnext.clear_filters{fields}`; `replaced_user_filters` in outcomes of navigate / clear / set_period | bridge | M | none |
| T2.4 | `compare` query kind (two periods or a period and its prior year, deltas in code) | query | M | T0.1 |
| T2.5 | App instructions text (4.4) and a read-only `erpnext.context` action | bridge | S | T2.1, T1.3 |
| T2.6 | Starter prompts that are 2-3 turn chains, and the follow-up chips content | bridge | S | T1.4, T2.1 |
| **Phase 3: evaluate, then spread** | | | | |
| T3.1 | Write conversations C01-C28 with oracles; arms A1-A3; 3 repeats x 2 models; results into `RESULTS.md` | tests | L | T0.2, T2.x |
| T3.2 | Lane B Playwright smoke (8 conversations) incl. reload mid-conversation | tests | M | T2.1 |
| T3.3 | Port the provider to Metasfresh (and add `params_used` to `metasfresh.query`) | bridge | M | T2.1 |
| T3.4 | WWI: pin scope key, provider from the store, add C-style conversations to `wwi-dashboard/eval` | bridge + tests | M | T0.4, T2.1 |
| T3.5 | Gate integration: conversation-level evidence (`call_id` + `scope_hash` + turn), reuse rule; depends on the hybrid gate (FUTURE_FIXES #4) and the TypeScript port (#12) | chat + tests | L | T2.1, FUTURE_FIXES #4, #12 |
| T3.6 | Optional: "what I remember" chip row in the chat (period, source, filters; click to change) | chat | M | T2.1 |

### First 3 things to do tomorrow
1. **T0.1** (about 2 h): hard error on unknown query params plus `params_used`/`scope_hash`. It removes a silent wrong-number path found in probe 5, and every later step reads these fields.
2. **T0.2 + T0.3**: build the multi-turn harness with four conversations (C01, C04, C16, C26) and get the A0 baseline numbers, so every later change has a before/after.
3. **T1.1 spike** (half a day): wire a hard-coded `__VACP_CHAT_CONTEXT` string end to end in the debug-ui build, confirm in a browser that it reaches the last user message of the model request and is **not** saved in `localStorage`. Only then write `context.ts`. In parallel, someone does T0.4.

## 8. Risks and open questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | The model over-trusts the context block and reuses numbers (probe 3, with-context case) | Provenance (`from_turn`, `scope_hash`, `age_s`) plus the `no_stale_reuse` score and, later, the gate; keep numbers in the block to the minimum a follow-up needs |
| R2 | Bridge memory diverges from the thread (regenerate, clear, delete thread, second tab) | Key entries by thread id + message count; rebuild from the thread's own tool results (they hold `params_used`) when the counts disagree; reset on `sessionRevision` change |
| R3 | A reload or stop in the middle of a turn leaves a tool part without output and breaks the next prompt (`compaction.ts:238-246` only rethrows with a message) | T0.4 to confirm; if real, drop incomplete tool parts in the wrapper |
| R4 | Shared-module changes affect Metasfresh/WWI and other examples | Everything behind window globals, default off; run the existing agent-client tests and `test_metasfresh_webui_bridge.py` by someone other than the planner |
| R5 | Screen read at send time is slow on the 73k-row lists | 1.5 s timeout -> `screen_now: {unavailable}` and the rule "call vacp_state"; reuse the 2.5 s cache |
| R6 | Digest drops a field the gate or a later question needs | Side store of full results; digests list the `call_id` so the model can re-run, never rely on the cut text |
| R7 | Results are noisy (19-conversation-sized runs were +-3 tasks) | 3 repeats, two models, report turn and conversation level; do not claim gains under about 10 points |
| R8 | localStorage quota: full tool payloads are persisted (up to 12,000 chars per string, 500 array items, `sanitize-tool-payload.ts:1-6`) | Check in T0.4; store digests for tool parts older than N turns |
| R9 | Hard-failing unknown params may break prompts that worked by luck | Return the valid parameter list in the error; the harness measures recovery |

Open questions for the team:
- **Q1** Is a context block visible to the user (a "what I remember" chip row) a goal? It helps traceability and UX but is an L-size UI task (T3.6).
- **Q2** Reuse window: 10 minutes for identical scopes, or never reuse (always re-query)? The dataset is frozen, a live ERP is not.
- **Q3** Must the agent **ask before** discarding the user's manual filters (`navigate`, `clear_filters`)? The brief says "confirmation before state changes"; today navigation never asks.
- **Q4** "Last month" / "this year": relative to today (2026-10) or to the end of the data (2016-05-31)? Proposed: ask or state the assumption; decide the default.
- **Q5** In-app model: only native-tool models (Nemotron, gpt-oss) are supported by the chat; is that acceptable for the final demo?
- **Q6** Success targets for section 6.3, and whether to port the C-set to the WWI harness before the held-out run.

## Summary
1. Today the model gets the whole thread, but old tool results are cut to 1,200 characters mid-JSON, the action list is lost (6 of 11 probe runs re-read capabilities), and nothing tells it the user changed the Desk.
2. Simple ellipsis, correction and comparison already work with full history (3/3 probes); the real defects are silent wrong scope (`filters` accepted and ignored), truncated references, and manual changes.
3. Primary design: a code-built `ConversationContext` appended ephemerally to the last user message, plus app-supplied tool-result digests and follow-up rules; defer query rewriting and history retrieval.
4. Evidence first: a multi-turn extension of the KPI harness with 28 SQL-checked conversations (types a-h), scored on final screen, numbers, stale reuse, clarification and cost, run as arms A0-A3.
5. Tomorrow: query hardening (T0.1), harness plus baseline (T0.2/T0.3), and a one-string injection spike (T1.1); top risks are over-trust of the context block, memory drift on regenerate/clear, and a possible broken thread after a mid-turn reload.
