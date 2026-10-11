# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

There is no code yet, so no build, lint or test commands exist. The brief is in `problem_statement.md` (Domain 5A: Context-Aware Application Agent).

## Goal

Build an assistant that understands a whole no-code business application, including its navigation hierarchy, pages, widgets, data views, filters and charts. Users operate and analyse the app through natural language. The agent must:

1. Work out what the user intends.
2. Act on the app: go to the right page and set filters, date ranges, sorting and other UI state.
3. Retrieve data and combine it.
4. Reason analytically about trends, period-to-period comparisons and likely causes.
5. Present the answer in the context of the app.

It is meant to be more than a chatbot.

## Intended architecture (from the brief)

- **Data and metadata layer:** a store of application metadata, plus a knowledge graph linking pages, widgets and filters. Add a vector index over component descriptions (FAISS, Milvus or pgvector) and connectors to the no-code platform's APIs.
- **Modelling and AI:** LLM intent understanding and planning, using an agent framework with tool calling (LangChain or LlamaIndex). Use RAG to retrieve pages and data views, generate queries from text, and reason over multiple steps for analysis.
- **Orchestration:** an agent controller whose tools navigate routes, set filters, dates and sorts, and read component data. Use Playwright when no direct API exists. Add guardrails, and require confirmation before changing state.
- **UX:** a conversational companion embedded in the app. It renders charts, summary cards and comparisons on the fly, links straight to pages, supports human review, and explains the actions it took.

## Expected inputs

- **Application metadata:** the navigation tree, catalogues of pages and widgets, and schemas for data views, grids, charts and filters.
- **UI-state definitions:** the filters, date ranges and sort options available on each page, plus the routing and deep-link map.
- **Business data:** the revenue, sales and operational tables behind the reports. Use synthetic or sample tenants where production data is sensitive.
- **Labelled utterances:** user requests annotated with the target page, report or grid and the required UI state (intents and slots).
- **Public surrogates:** UI and screen-understanding corpora, text-to-SQL datasets and RAG evaluation sets.

## KPIs to design and evaluate against

- Intent-to-destination accuracy: the share of requests routed to the correct page.
- UI-state correctness: whether filters, date ranges and sorts are set correctly.
- Task success on multi-step requests, with the average number of steps and the latency.
- Analytical correctness, and faithfulness: every answer must trace back to the supporting views.
- Retrieval quality over hundreds of pages and components: precision, recall and MRR.
- Action hallucination near zero, plus error and recovery rate and response latency.
