# Sapience: project context (written 11 Oct 2026)

Read this file first. It says what the project is, what state it is in, the rules to follow, and which other file answers which question.

## What the project is
KLE Tech Hackfest 2026, Domain 5A: a **Context-Aware Application Agent** (brief: `/home/dheeraj/Agentic_Hackathon/problem_statement.md`, summary in `CLAUDE.md`). Team name: **Sapience** (not "Sapiens"; older decks still say Sapiens).
The agent works with a whole business application: it understands the user's intent, goes to the right page, sets filters and dates, retrieves and combines data, reasons over periods and causes, and answers with sources.

**Our solution in one line:** one agent with two channels. The **API** is for *knowing* (exact figures from governed endpoints); **VACP** (an in-page action/state bridge) is for *doing and showing* (operating the real app screen). Each covers the other's gap. See `03_STORY_AND_DESIGN.md`.

## Rules from the user (always follow)
- **Never read or touch `Do_not_open/`.** It is private context. If you already read it, disregard it.
- **Do not create claude.ai artifacts.** Make files.
- **Deck font size: 15 pt or larger everywhere.**
- **Prefix every shell command with `wsrun --student 01fe23bcs197`** (that exact flag, one dash pair).
- **Secrets stay out of files and chat:** the LLM API key lives in `/home/dheeraj/llm/api_key.txt` (and `CONNECT.md` there); ERPNext passwords are install defaults, listed in `data/TRANSFER.md`. Do not copy them elsewhere.
- Do not guess: mark results as verified, recorded, or not measured (the convention used in all these files).
- Don't worry about what is happening on GPU 0; the local DeepSeek model runs on GPU 1.

## State in five lines (11 Oct)
1. **Data:** WWI (Wide World Importers) sample, v2 package with an independent answer key. **ERPNext 15** holds the same data through **24 Feb 2016**, reconciled 8 of 8 against the key. Running here and on nova2.
2. **API agent:** built and **embedded** in a redesigned WWI console with an in-app assistant panel and a "ledger" infographic. Dev-set results only; the held-out run has not been done.
3. **VACP:** a bridge on ERPNext's Desk exists on nova2 (202 of 203 of its own checks pass) and a separate prototype of mine passed 23 of 23. **It is not yet joined to the agent** (on hold at the user's request).
4. **Analytics are read-only; the console now has a separate workspace for CRUD** (create/edit/delete, review step, audit log; never changes the source or any analytics figure). The agent does not write. **Chart builder built (12 Oct)**: page #/charts, 4 chart types plus a number card, saved definitions (requests, not data) in the workspace store, 28 of 28 browser/API checks (`eval/chart_test.py`). The assistant's "how I got this answer" view now shows the real steps of each question (12 Oct session).
5. **Deck:** a 13-slide v4 deck exists; another conversation is updating it from `PPT_UPDATE_CONTEXT_2026-10-11.md`.

## Where to look
| Question | File |
|---|---|
| What exists, where, and how sure are we? | `01_STATE_AND_EVIDENCE.md` |
| Why were things decided that way? | `02_DECISIONS.md` |
| What is the story, and what do the papers contribute? | `03_STORY_AND_DESIGN.md` |
| What can ERPNext vs our console do (CRUD, charts)? | `04_FEATURES_AND_LIMITS.md` |
| How do I start, stop, reach and fix things? | `05_OPERATIONS.md` |
| What is left to do, in what order? | `06_OPEN_WORK.md` |
| What happened, in order? | `07_TIMELINE.md` |
| What did nova2 add to the VACP repo (context persistence etc.)? | `08_VACP_ADDITIONS.md` |

Related files outside this folder: `PPT_UPDATE_CONTEXT_2026-10-11.md` (for the deck), `research/00_SYNTHESIS_PLAN.md` and `research/01_API_AGENT_BUILD_PLAN.md` (the plan), `data/TRANSFER.md` (moving to another machine), and on nova2 `API_BASED_AGENT/PLAN01_RECOMMENDATIONS_2026-10-11.md`.
