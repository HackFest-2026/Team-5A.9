# What nova2 added to the VACP repository (checked 12 Oct against git, in /home/nova2/hackathon/VACP)

Method: the repo is a git checkout (HEAD = upstream, last commit "fix: keep arena state traces complete"); `git status` and `git diff` show exactly what differs. Git does not record authorship (the changes are uncommitted); these are the team's changes on nova2. I read the code; I did **not** re-run the tests. Counts below come from nova2's own notes (`CONTEXT_AWARE_PLAN.md` section 9 and the READMEs).

## Changes to VACP's own packages (uncommitted edits)
- `agent-client/src/page-context.ts` (new, 137 lines) + test: per-turn **page context** hook `window.__VACP_CHAT_CONTEXT`, appended to the last user message only and never stored in the thread; 1.5 s timeout, 1,500-character cap, delimiter stripping.
- `agent-client/src/context-compaction.ts`: **digest** support. A tool result that carries a `digest` string is kept as that digest (cap 1,600) instead of the 1,200-character mid-JSON cut; with no digest the output is byte-identical to before. About 97 added test lines.
- `create-vacp-agent.ts`: the page-context wrapper sits inside the compaction wrapper; `repairActionToolCall` reroutes a model that calls `erpnext_open_record` directly through `vacp_execute`. `instructions.ts`, `types.ts`, `index.ts`: wiring.
- debug-ui chat: `__VACP_CHAT_SCOPE_KEY` (pin one thread per app so agent navigation does not start an empty thread), `__VACP_CHAT_STARTERS` (page-aware starter prompts; new `starters.ts`, `page-suggestions.tsx`), layout fixes (composer always visible), tool activity no longer force-opens the panel.
- Upstream already had: thread saved in localStorage, compaction (1,200-character cut), `vacp_state` tokens and deltas, scoped capabilities, undo history.

## New example packages (untracked)
- `erpnext-bridge` (bridge.ts about 1,660 lines plus modules): read-only `erpnext.*` actions on the stock Desk, injected by an nginx sub_filter. `erpnext.query` runs server-side aggregates and **shows the answer in the Desk** with `desk_view.matches_query`; page awareness (`read_page`), chart reading, and a rule that refuses workspaces with Report-type charts (they would flip a report to background mode). 203 SQL-checked tests (202 pass per notes).
- **Conversation context (the "newer persistence state")**: `conversation-context.ts` (723 lines) + `conversation-context-wire.ts`.
  - Last 5 queries with `params_used`, `scope_hash`, `queried_at`, headline figures and ranked names; last ranked list and opened record.
  - A screen signature (route, document, filters, grouping, page, sort) diffed against the screen the agent left, confirmed by a second read, so the model can be told "the user changed the Desk".
  - Figure-reuse rule: same scope hash and under 10 minutes, otherwise re-query.
  - Memory **reconciled with the visible thread** at every send: a cleared thread, a regenerated answer, a reload or a second tab are handled, and the memory is rebuilt from the tool results in the thread. The baseline snapshot lives in per-tab sessionStorage.
  - Strict queries (unknown parameters are errors), `erpnext.back`, `clear_filters{fields}`, and a refusal to drop filters the user set unless `confirm_discard`.
- `metasfresh-webui-bridge`, `metasfresh-dashboard`, `wwi-dashboard`: bridges and dashboards for the other apps, with KPI harnesses and RESULTS (WWI: 19 tasks, 53 to 76 percent task success across models; a model-versus-integration experiment).
- Evaluation: a 28-conversation multi-turn harness with ablation arms A0 to A3 (flags in `window.__VACP_CTX_FLAGS`), a SQL oracle and a scorer (20 offline tests); ERPNext KPI task selection (10 WebArena-style tasks); a retrieval eval over about 677 components. **Status: the harness is built; one conversation (C16, arm A2) has run, 1 of 1. The A0 to A3 comparison has not run, so no gain is claimed.**

## Where it went into the deck
`Sapience_Hackfest_Deck_v9.pptx` (built by `deck/build_v9.py` from `Sapience_Hackfest_Deck_v5.pptx`): slides 8, 11, 12, new 13, 14, 15, 21.
