# Submission Sections 1 and 2 (slide content)

As of 2026-10-05. Drafts submission sections **1. Proposed Solution and Objectives** and **2. Innovation and Existing Alternatives**, one slide each. Content is drawn from `07_Consolidated_Solution.md` §5 (gap-to-method mapping), §6 (borrowed versus ours) and §2 (the evidence base), with the Mind2Web feasibility finding from §7.1.

**Written for a reviewer who has not read our other reports.** Every term is explained where it first appears. The logical chain runs: the field already tested whether agents can click their way through real applications → they mostly cannot, and we know why → so we built the thing that removes that failure.

**Evidence boundary for both slides.** Nothing is built or measured by us yet. Every figure quoted is the cited authors' own, read from abstracts only (report 05). On stage, say "published results report", never "we achieved".

---

## Slide 1 — Proposed Solution and Objectives

**Title:** One Contract, Three Consumers

**The idea, in one line**

> An in-app companion that operates and analyses a whole business application from a single declared **Application Contract** — one machine-readable file that the app renders from, the agent acts through, and the evaluator scores against.

**Why a contract, in plain terms**

A business application shows itself to an AI as **pixels and prose**. Pixels can be clicked but not checked — the agent cannot tell whether a filter actually applied. Prose describes what a page looks like but not what it means — the agent cannot tell orders from order lines, or cartons from units.

So we stop describing the app and start **declaring** it. One file states every page, filter and measure by name, what each one means, which combinations are legal, and how every number is computed. The app is built from that file, the agent may only act through it, and the scoring is written in its terms. Three readers, one source — so none of them can disagree with the others.

**Core features**

| # | Feature | What it guarantees |
|---|---|---|
| 1 | **The Application Contract** — pages, routes, widgets, filters and measures, each with its meaning: grain, unit, synonyms, legal values, provenance | The app cannot drift from its own description |
| 2 | **Acting by one typed state change** — the whole view lives in the URL, so navigating and filtering is a single checked call, never a chain of clicks | There is nothing to locate on screen, so the usual failure cannot happen |
| 3 | **Validate before, read back after** — illegal calls are refused; the state the app actually applied is compared with the state requested; on a mismatch, retry once, then undo and say so | A filter that silently failed can never be reported as success |
| 4 | **Routing by capability, with abstention** — only pages whose grain and filters can accept the request are considered | "No view answers that" is a valid, expected answer |
| 5 | **Named measures with evidence IDs** — the agent never writes SQL; it calls the same query the screen renders from, and every result is tagged | Every number traces back to a view; fact, calculation and inference are labelled apart |
| 6 | **Scoring the final state** — a task file, a trace log of every call, and KPIs computed from it | The result is provable, not merely demonstrable |

**Key objectives — each is a KPI from the brief**

| Objective | How it is measured |
|---|---|
| Send every request to the right page | Intent-to-destination accuracy, top-1, reported per split |
| Set filters, dates and sorts correctly, and verify them | Exact match of the final view state; F1 per filter |
| Answer analytical questions traceably | Values within tolerance; share of numbers carrying evidence (target: all of them) |
| Never invent an action | Invented-action rate on requests nothing can answer; completion under policy |
| Stay fast enough to live inside the app | One state change per view; median and 95th-percentile latency |

**Intended benefits**

- **For the user:** answers without having to know how the app is organised. In one enterprise study, human testers new to an application completed only **61.2%** of tasks — the app itself is the obstacle, which is precisely what an assistant that knows the app removes.
- **For trust:** every figure links to the view it came from, and observed, calculated and inferred statements are labelled differently.
- **For safety:** the agent can only do what the contract declares legal, and the single write action is confirmed against the exact pending change.
- **For speed:** one state change replaces a chain of clicks — published comparisons report **950 ms against 3,404 ms** for browser automation.
- **For the reviewer:** KPIs computed from a trace log, including a run with the validator switched off to show how much of the reliability is actually ours.

*Speaker note:* lead with the contract, not the chatbot. The sentence to land is "the app, the agent and the scoring all read the same file, so none of them can disagree."

---

## Slide 2 — Innovation and Existing Alternatives

**Title:** The Experiment Has Already Been Run

### The connection a reviewer needs first

**Mind2Web** is the standard public test of whether an AI can operate real applications the way a person does: 2,350 everyday tasks across 137 real websites, where the agent must find and click the right thing on pages holding roughly 1,100 elements each.

**The published result: agents finished 2–7% of whole tasks.** On enterprise software specifically, a later benchmark found **9–19%** on multi-step workflows — against 67–85% on single button-clicks. The cliff is in stringing actions together.

**And we know why.** A follow-up study removed the hard part by hand, telling the model exactly which element to click. Success rose to **51.1%**. The agents were not failing to *decide what to do*. They were failing to *find the thing to act on* — a problem the field calls **grounding**.

> **That one finding is why our solution looks the way it does.** If locating things on a screen is what breaks, remove the locating. In our design the app declares every page, filter and measure by name, and the agent calls them by name. There is nothing to find, nothing to click, nothing to guess.

Everything below follows from that.

### Existing approaches and what limits them

| Approach | Representative work | Published limitation |
|---|---|---|
| **Click-driven browser and GUI agents** | Playwright scripts, BrowserOS, vision-based GUI models | **2–7%** of whole tasks on real websites; **9–19%** on enterprise workflows |
| **Grounding-first multimodal agents** | SeeAct | **51.1%** only when the element to click was supplied by hand — the bottleneck is finding, not thinking |
| **Embedded app agents** (closest to us) | EmbeWebAgent, VACP | They declare the app's *state and functions*, but not its *business meaning*, and the numbers they return carry no trace back to a view |
| **Typed-action proposals** | "Web verbs" position paper, Vector | The right direction — typed calls, risk-based routing — but a position paper and a routing study, with no business-application prototype and no measured KPIs |
| **Text-to-SQL and chat-BI** | TA-SQL and similar | Valid SQL with the wrong meaning; figures that contradict the chart sitting next to them |
| **Classic RPA** | ECLAIR case studies | **12–18 months** to set up, **60%** accuracy at the start, heavy ongoing maintenance |
| **Long agent chains, generally** | — | Success decays **geometrically** with each added step; and agents' *completion under policy* — finishing the task **and** breaking no rule on the way — is under **two-thirds** of their headline success rate |

**What we concluded from the table:** stop competing on clicking better. Remove clicking from the critical path, and spend the effort on what nobody above has done — declaring what the app's numbers *mean* and proving where each one came from.

### How we actually fix it, problem by problem

This is the solution. Each row is a failure we identified in the reference stack, the concrete mechanism we build against it, and the published method that mechanism comes from. The ★ rows are the five to keep if the slide runs short; the full 28-failure version is report 07 §5.

| The problem | What we actually build | Method taken from |
|---|---|---|
| ★ The agent finds the right-*looking* page and misreads it — orders instead of order lines, cartons instead of units | The contract declares every widget's **grain and unit**, plus "use this page, not that one" notes. The router keeps only pages whose grain can accept the request, then picks from a shortlist that always offers **"none of these"** | Mind2Web's own shortlist-then-choose (MindAct, recall@50 85–89%); VACP |
| The exported metadata is simply wrong | Each description carries a provenance tag, and the riskiest become **SQL assertions run on every build**. A description that fails its check is marked unverified and kept out of the index | CLAIRE (deterministic validation stage) |
| ★ The agent invents a filter, value or date that does not exist | The contract lists every filter's type, allowed values, dependencies and setting order. A **validator refuses any call that breaks them, before it runs** | Typed "web verbs" (preconditions); CLAIRE — removing validation halved success under stress |
| ★ A filter silently fails to apply, and success is reported anyway | `configure_view` changes one URL, then **reads back the state the app actually applied** and compares it with what was asked. On a mismatch it retries once, then restores the previous URL and says so | Hybrid World-Model Planning (gate the agent's claimed state against a real check) |
| Click chains are slow and break on layout changes | The entire view — page, filters, dates, sort, selection — **lives in the URL**, so changing it is one typed call. Playwright is kept only to drift-check the app against the contract | Beyond Browsing (+24 points over browsing); Unbrowse (950 ms vs 3,404 ms) |
| ★ Agent-written SQL joins wrongly, and its numbers contradict the chart beside them | The agent **never writes SQL**. It names a widget or measure and passes filters; the contract holds one parameterised query per measure — **the same query the screen renders from**. Read-only login, with a guarded single-SELECT fallback labelled "not on screen" | VACP; headless-BI practice (one definition serves screen and API) |
| ★ Unsupported "likely causes", and figures nobody can trace | Every tool result carries an **evidence ID**. A figure matching no ID **blocks the answer** until redrafted. Statements are labelled observed, calculated or inferred, and "cause" is permitted only with a linking record on screen — otherwise "accounts for" | AD-Bench (scores answer *and* trajectory); DAComp (rubric-graded analysis) |
| "This item" and "same period" lose their meaning on the next turn | Current page, filters and selection travel with every message; investigation state carries view, selection and evidence across turns; an ambiguous name returns options instead of a guess | MT-Mind2Web / Self-MAP (multi-turn memory) |
| An unsafe write slips through a generic "are you sure?" | Two tiers: reads and view changes just run. The one write action shows a card **built from the exact pending action, not from model text**, and is re-verified at the moment of saving | Verifiable Action Card; Commit-Time Authorization — 207 of 216 runs committed after the approving path had lapsed |
| None of it can be proved afterwards | A task file giving expected page, final state, values, evidence and policies; a trace log of every call; **the final state scored, with alternative action orders accepted**; completion under policy, step count, and a validator on/off run | EntWorld (SQL verification); WebCanvas (key intermediate states); ST-WebAgentBench (completion under policy) |

**Read the table as the argument:** the left column is why click-driven and chat-BI approaches fail, the middle column is our system, and the right column shows every mechanism is already validated in published work. We assembled it; we did not invent it.

### The whitespace, in one line

> **1,506** papers cite that standard benchmark. About **40** touch enterprise applications or analytics. Exactly **1** mentions no-code platforms.

The mechanisms we need are therefore published and validated — we borrow rather than invent. The *combination*, applied to a metadata-defined business application with declared meaning and traceable numbers, is unoccupied.

### Honest positioning — say this out loud

> We do not claim that embedding an agent in an app is new. EmbeWebAgent and VACP already do that. What we add is business meaning in the contract, verified state changes, and analysis traced to evidence — and we back the claim by switching the validator off and showing what breaks.

*Speaker note:* if asked "then why not just use Mind2Web to evaluate this?", the answer is report 07 §7.1 — it runs on cached copies of pages, scores the exact element clicked, gives one instruction up front with no follow-ups, and contains no questions that require an answer to be reported. Those four exclusions are the four things this product is for. We use it for one narrow purpose: a retrieval stress test, picking the right component out of hundreds.
