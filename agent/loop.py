"""The agent loop:  understand -> resolve -> plan -> execute (gated) -> finish gate -> answer.

LLM work: step [1] intent (schema-constrained), step [3-4] tool calls (native tool calling), step [6] wording.
Everything else (date maths, context carry-over, id grounding, validation, arithmetic, number tracing) is code."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .adapters.base import Backend, BackendError
from .answer import compose, notes_for
from .config import Config
from .contract import DIM_FILTER, Contract, RESOLVE_TYPE_FILTER
from .docs import PageIndex
from .chart_proposal import propose_chart, wants_chart
from .facts import derive
from .finish import Expectation, finish_checks
from .gates import Gates
from .llm import LLM, LLMError
from .session import Call, Session, jdump
from .slots import State, build_intent_model, fallback_periods, merge_state
from .tools import ToolBox, tool_specs
from .trace import Trace
from .understand import understand

ENTITY_FILTER = {
    "customer": "customer_id", "stock_item": "stock_item_id", "supplier": "supplier_id", "order": "order_id",
    "purchase_order": "purchase_order_id", "salesperson": "salesperson_id",
}
RECORDS_PAGE_PRECEDENCE = [("purchase_order_id", "purchase"), ("order_id", "order"), ("customer_id", "customer"),
                           ("stock_item_id", "item"), ("supplier_id", "supplier")]
PLANNER_SYSTEM = """You operate a business analytics app through tools. The user's request has already been understood; the SLOTS below are authoritative, and names are already resolved to ids by code.
Rules:
- Make the tool call that carries out the request, copying the slot values exactly. Do not add filters, dates or breakdowns that are not in the slots.
- One call is usually enough. If PLAYBOOK steps are given, follow them in order and take ids and group names from the previous result.
- Never invent ids: use only ids from the slots or from tool results.
- If a tool returns an error, fix the call using the error text.
- When the work is done, reply with the single word DONE."""


@dataclass
class AgentResult:
    status: str                      # answered | clarify | refuse | abstain | error
    text: str
    op: str = ""                     # primary operation, for evaluation
    deep_link: str | None = None
    notes: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    applied: dict | None = None
    resolutions: list[dict] = field(default_factory=list)
    intent: dict | None = None
    expectation: dict | None = None
    attempts: int = 0
    llm_calls: int = 0
    latency: float = 0.0
    answer_source: str = ""
    events: list[dict] = field(default_factory=list)
    trace_path: str | None = None
    proposal: dict | None = None      # a chart the user may save (see chart_proposal.py)

    def render(self) -> str:
        out = [self.text]
        for n in self.notes:
            out.append(f"Note: {n}")
        if self.deep_link:
            out.append(f"Open in app: {self.deep_link}")
        if self.actions:
            out.append("Actions taken:")
            out += [f"  - {a['summary']}" for a in self.actions]
        return "\n".join(out)


def _summ(call: Call) -> str:
    a = {k: v for k, v in call.args.items() if v not in (None, {}, "")}
    s = f"{call.name}({jdump(a, 220)})"
    return s if call.ok else s + f" -> ERROR: {call.error}"


class Agent:
    def __init__(self, cfg: Config, backend: Backend, llm: LLM, pages: PageIndex | None = None):
        self.cfg, self.backend, self.llm, self.pages = cfg, backend, llm, pages
        self.c = Contract(backend.contract(), cfg.data_min, cfg.data_max)
        self.Intent, _, _ = build_intent_model(self.c)
        self.specs = tool_specs(self.c)
        self.ref_date = date.fromisoformat(self.c.reference_date)
        self.data_max = date.fromisoformat(cfg.data_max)

    def new_session(self) -> Session:
        return Session()

    # ======================================================================== turn
    def turn(self, text: str, session: Session | None = None, trace: Trace | None = None) -> AgentResult:
        session = session or Session()
        tr = trace or Trace(self.cfg.trace_dir)
        t0 = time.time()
        llm_before = self.llm.calls
        tr.event("turn", text=text)
        # a reply to our clarifying question is understood together with the request it answers
        u_text = f"{session.pending_text} (asked to clarify; the user now says: {text})" if session.pending_text else text
        try:
            res = self._turn(text, session, tr, u_text)
        except (BackendError, LLMError) as e:
            tr.event("error", error=str(e))
            res = AgentResult("error", f"I couldn't complete that because a component failed: {e}", op="error")
        except Exception as e:  # noqa: BLE001 - a turn must never take the whole session down
            tr.event("error", error=f"{type(e).__name__}: {e}")
            res = AgentResult("error", f"Something unexpected went wrong ({type(e).__name__}); nothing was changed.", op="error")
        session.pending_text = u_text if res.status == "clarify" else None
        res.latency = time.time() - t0
        # counted from this turn's own trace so it stays correct when turns run concurrently
        res.llm_calls = sum(1 + e.get("retries", 0) for e in tr.events if e["kind"] == "understand") \
            + tr.count("llm_plan") + tr.count("answer_draft")
        res.attempts = tr.count("tool_call") + tr.count("gate_reject")
        res.events = list(tr.events)
        res.trace_path = str(tr.path) if tr.path else None
        res.actions = [{"name": c.name, "args": c.args, "ok": c.ok, "error": c.error, "summary": _summ(c)} for c in res.calls]
        tr.event("result", status=res.status, op=res.op, link=res.deep_link, latency=round(res.latency, 2), llm_calls=res.llm_calls)
        session.turns += 1
        return res

    @staticmethod
    def sanitize(intent: Any, text: str) -> list[str]:
        """Drop optional slots the user's own words do not support (the model likes to add them)."""
        dropped = []
        t = text.lower()
        if intent.status and intent.action == "analyze" and not re.search(r"picking[ -]?(is |was )?(not )?(complete|incomplete|finished)|fully picked|partially picked", t):
            dropped.append(f"status={intent.status}")
            intent.status = None
        if (intent.group_by and intent.action == "analyze" and intent.group_by != "none"
                and not re.search(r"\b(by|per|each|split|break|breakdown|which|who|whose|across|rank|top|most|least|biggest|largest|share|compare)\b|trend|over time|monthly|\bmix\b", t)):
            dropped.append(f"group_by={intent.group_by}")
            intent.group_by = None
        if intent.sort and not re.search(r"top|bottom|most|least|biggest|largest|smallest|fell|fall|declin|drop|decreas|highest|lowest|first|ascending|descending|rank|worst|best|alphabet|order by|sorted", t):
            dropped.append(f"sort={intent.sort}")
            intent.sort = None
        if intent.top_n and not re.search(r"\d|top|bottom|first|best|worst|biggest|largest", t):
            dropped.append(f"top_n={intent.top_n}")
            intent.top_n = None
        return dropped

    def _turn(self, text: str, s: Session, tr: Trace, u_text: str | None = None) -> AgentResult:
        c, cfg = self.c, self.cfg
        u_text = u_text or text
        s.registry.add_user_text(text)
        calls: list[Call] = []
        gates = Gates(c, s, cfg.step_budget, enabled=cfg.gates)
        tb = ToolBox(self.backend, c, s, self.pages)

        # [1] Understand
        intent, meta = understand(self.llm, c, self.Intent, u_text, s)
        tr.event("understand", intent=meta.get("raw"), latency=round(meta["latency"], 2), retries=meta["retries"])
        dropped = self.sanitize(intent, u_text)
        if intent.action in ("analyze", "records"):
            cur, base = fallback_periods(u_text)
            if cur is not None and intent.period is None:
                intent.period = cur
                dropped.append(f"period filled from text: {cur.model_dump(exclude_none=True)}")
            if base is not None and intent.compare_period is None and intent.compare in (None, "explicit", "none"):
                # two months named: the later one is the current period, the earlier one the baseline
                intent.period, intent.compare, intent.compare_period = cur, "explicit", base
                dropped.append(f"comparison filled from text: {base.model_dump(exclude_none=True)}")
        if dropped:
            tr.event("sanitize", dropped=dropped)
        # grounding of the model's own slots: an id the user never typed and no result showed is dropped
        if cfg.gates and intent.ids:
            from .session import FILTER_KIND
            keep = [r for r in intent.ids if s.registry.has(FILTER_KIND.get(r.filter, r.filter), r.value)]
            dropped = [r.model_dump() for r in intent.ids if r not in keep]
            if dropped:
                tr.event("gate_reject", tool="understand", gate="grounding", messages=[f"dropped ungrounded ids {dropped}"])
            intent.ids = keep
        idict = intent.model_dump(exclude_none=True)

        # glossary exits: ambiguous word -> ask; unsupported -> say so honestly
        if intent.action in ("clarify", "refuse"):
            return self._glossary_exit(intent, idict, c)

        # [2] Resolve names (code calls resolve; ambiguous -> ask, none -> abstain)
        resolved: dict[str, Any] = {}
        resolutions: list[dict] = []
        for nm in intent.names:
            out = self._resolve_name(nm, tb, gates, calls, tr, s)
            resolutions.append(out["record"])
            if out.get("exit"):
                res = out["exit"]
                res.calls, res.resolutions, res.intent = calls, resolutions, idict
                return res
            resolved[out["filter"]] = out["value"]

        # entity / row references
        row_ref = None
        if intent.use_row is not None:
            f = DIM_FILTER.get(s.last_group_by)
            rows = [r for r in s.last_rows if not r.get("is_other")]
            if not f or intent.use_row > len(rows):
                return AgentResult("clarify", "I don't have a previous list to point at. Which one do you mean?", op="clarify",
                                   calls=calls, resolutions=resolutions, intent=idict)
            row_ref = (f, rows[intent.use_row - 1]["key"])
            kind = f.removesuffix("_id")
            s.registry.add(kind, row_ref[1], "row-ref")
        try:
            new = merge_state(s.state, intent, resolved, row_ref, c, self.ref_date, self.data_max)
        except (ValueError, OverflowError) as e:
            tr.event("period_error", error=str(e))
            return AgentResult("clarify", "Which period do you mean? Please give a month, quarter or year, for example 'May 2016'.",
                               op="clarify", calls=calls, resolutions=resolutions, intent=idict)

        # expectation
        exp = self._expectation(intent, new, s, resolved, row_ref)
        if isinstance(exp, AgentResult):
            exp.calls, exp.resolutions, exp.intent = calls, resolutions, idict
            return exp
        tr.event("expectation", **exp.describe())

        # pre-flight: an impossible combination is refused before any call is made
        if exp.action == "analyze" and cfg.gates:
            norm, errs = c.validate_analyze(exp.request)  # type: ignore[arg-type]
            if errs:
                tr.event("preflight_refuse", errors=errs)
                if any(("period" in e or "start" in e or "end" in e) and "cannot" not in e for e in errs):
                    # a missing or malformed period is a gap in the request, not an impossible combination
                    return AgentResult("clarify", "Which period do you mean? (" + "; ".join(errs) + ")", op="clarify",
                                       calls=calls, resolutions=resolutions, intent=idict, expectation=exp.describe())
                msg = "That combination is not valid in this app: " + "; ".join(errs)
                return AgentResult("refuse", msg, op="refuse", calls=calls, resolutions=resolutions, intent=idict,
                                   expectation=exp.describe())

        # [3-5] plan, execute, finish gate
        playbook = intent.playbook if intent.playbook in c.playbooks else None
        ok, why = self._execute(text, exp, playbook, calls, gates, tb, tr, s)
        attempts = len([e for e in tr.events if e["kind"] == "tool_call"])
        if not ok:
            last_err = next((x.error for x in reversed(calls) if not x.ok and x.error), None)
            msg = f"I couldn't complete this reliably: {why}"
            if last_err:
                msg += f" (last error: {last_err})"
            return AgentResult("abstain", msg, op="abstain", calls=calls, resolutions=resolutions, intent=idict,
                               expectation=exp.describe(), attempts=attempts)

        # state carries forward only after a verified success
        self._commit(s, new, exp, calls)

        # [6] Answer
        link = self._destination(exp, calls, tb)
        facts_text, source, events = compose(self.llm if cfg.llm_answer else None, text, exp, calls, c, tb)
        for ev in events:
            tr.event("answer_draft", **ev)
        notes = notes_for(calls, c, intent.glossary_term if intent.action == "analyze" else None)
        applied = (calls and next((x.applied for x in reversed(calls) if x.ok and x.name == exp.action), None)) or None
        proposal = None
        if exp.action == "analyze" and wants_chart(text):
            proposal = propose_chart(text, exp.describe().get("request"))
        return AgentResult("answered", facts_text, op=exp.action, deep_link=link, notes=notes, calls=calls, applied=applied,
                           resolutions=resolutions, intent=idict, expectation=exp.describe(), attempts=attempts,
                           answer_source=source, proposal=proposal)

    # ------------------------------------------------------------------ pieces
    def _glossary_exit(self, intent: Any, idict: dict, c: Contract) -> AgentResult:
        g = next((x for x in c.glossary if x["term"] == intent.glossary_term), None)
        if intent.action == "clarify":
            q = (g or {}).get("clarify_question") or "Which measure do you mean: orders, units to pick, incoming supply, sales or profit?"
            return AgentResult("clarify", q, op="clarify", intent=idict)
        r = (g or {}).get("unsupported_reply") or "That isn't something this data can support. I can show orders, unpicked units, incoming supply, sales or recorded gross profit."
        return AgentResult("refuse", r, op="refuse", intent=idict)

    def _resolve_name(self, nm: Any, tb: ToolBox, gates: Gates, calls: list[Call], tr: Trace, s: Session) -> dict:
        c = self.c
        typ, name = nm.type, nm.text.strip()
        if typ == "sales_territory":
            hit = next((t for t in c.territories if t.lower() == name.lower()), None)
            if hit:
                s.registry.add("sales_territory", hit, "user")
                return {"filter": "sales_territory", "value": hit,
                        "record": {"text": name, "type": typ, "status": "unique", "id": hit}}
        args = {"kind": typ, "name": name}
        call = None
        for kind in (typ, None):
            a = {"kind": kind, "name": name} if kind else None
            if a is None:  # second try: search every type
                r = self.backend.resolve(name, None, 5)
                call = Call("resolve", {"kind": "any", "name": name}, r.get("completed") is not False, r, r.get("error"),
                            applied={"kind": "any", "name": name})
                for cand in r.get("candidates", []):
                    s.registry.add(cand["type"], cand["id"], "resolve")
            else:
                v = gates.check("resolve", a, calls, 0)
                if not v.ok:
                    tr.event("gate_reject", tool="resolve", gate=v.gate, messages=v.messages)
                    continue
                call = tb.execute("resolve", a)
            calls.append(call)
            tr.event("tool_call", tool="resolve", args=call.args, ok=call.ok, status=call.data.get("status"))
            if call.ok and call.data.get("status") != "none":
                break
        status = call.data.get("status") if call and call.ok else "none"
        cands = (call.data.get("candidates") if call else None) or []
        rec = {"text": name, "type": typ, "status": status, "id": None, "candidates": cands[:5]}
        if status == "unique":
            cand = cands[0]
            rec["id"], rec["type"] = cand["id"], cand["type"]
            s.remember_entity(name, cand["type"], cand["id"], cand["name"])
            f = RESOLVE_TYPE_FILTER.get(cand["type"])
            if cand["type"] == "sales_territory":
                return {"filter": "sales_territory", "value": cand["name"], "record": rec}
            if f:
                return {"filter": f, "value": cand["id"], "record": rec}
        if status == "ambiguous":
            opts = "; ".join(f"{x['name']} ({x['type'].replace('_', ' ')} {x['id']})" for x in cands[:5])
            ask = (call.data.get("ask") if call else None) or f'Several records match "{name}".'
            return {"record": rec, "exit": AgentResult("clarify", f"{ask} Options: {opts}. Which one do you mean?", op="clarify")}
        hint = ""
        if cands:
            hint = " Did you mean: " + "; ".join(x["name"] for x in cands[:3]) + "?"
        return {"record": rec, "exit": AgentResult("abstain", f'I couldn\'t find a {typ.replace("_", " ")} called "{name}".{hint}', op="abstain")}

    def _expectation(self, intent: Any, new: State, s: Session, resolved: dict, row_ref: Any) -> Expectation | AgentResult:
        c = self.c
        a = intent.action
        if a == "analyze":
            if not new.measure_id:
                g = next((x for x in c.glossary if x["term"] == "performance"), None)
                q = (g or {}).get("clarify_question") or "Which measure: orders, units to pick, incoming supply, sales or profit?"
                return AgentResult("clarify", q, op="clarify")
            return Expectation("analyze", request=new.to_request())
        if a == "records":
            view = intent.records_view or ("orders" if new.measure_id in (None, "M01", "M02", "M03", "M13") else "purchase_lines")
            req = {"filters": dict(new.filters), "start": new.start, "end": new.end}
            return Expectation("records", request=req, records_view=view)
        if a == "related":
            typ = intent.related_type
            if typ is None:
                return AgentResult("clarify", "Which customer, item, supplier, order or salesperson do you want context for?", op="clarify")
            f = ENTITY_FILTER[typ]
            ident = None
            if row_ref and row_ref[0] == f:
                ident = row_ref[1]
            elif f in resolved:
                ident = resolved[f]
            else:
                ident = next((i.value for i in intent.ids if i.filter == f), None) or new.filters.get(f)
            if ident is None and s.last_related:
                # "Who supplies it?": follow the link recorded in the previous related() result
                col = {"supplier": "SupplierID", "customer": "CustomerID", "stock_item": "StockItemID",
                       "salesperson": "SalespersonPersonID"}.get(typ)
                ident = (s.last_related.get("entity") or {}).get(col) if col else None
            if ident is None and s.last_entity and s.last_entity[0] == typ:
                ident = s.last_entity[1]
            if ident is None:
                return AgentResult("clarify", f"Which {typ.replace('_', ' ')} do you mean? Give me a name or an id.", op="clarify")
            return Expectation("related", entity=(typ, ident))
        if a == "navigate":
            return Expectation("navigate", page=intent.page or "overview", scenario_id=intent.scenario_id or new.scenario_id)
        return AgentResult("clarify", "I'm not sure what you'd like me to do. Could you rephrase?", op="clarify")

    # ------------------------------------------------------------------ execution
    def _plan_slots(self, exp: Expectation) -> list[tuple[str, dict]]:
        if exp.action == "analyze":
            return [("analyze", exp.request or {})]
        if exp.action == "records":
            r = exp.request or {}
            args: dict[str, Any] = {"view": exp.records_view, "filters": r.get("filters") or {}}
            for k in ("start", "end"):
                if r.get(k):
                    args[k] = r[k]
            return [("records", args)]
        if exp.action == "related":
            return [("related", {"entity_type": exp.entity[0], "entity_id": exp.entity[1]})]  # type: ignore[index]
        args = {"page": exp.page or "overview"}
        if exp.scenario_id and exp.scenario_id != "base":
            args["scenario_id"] = exp.scenario_id
        return [("open_page", args)]

    def _first_specs(self, exp: Expectation) -> list[dict]:
        """First planner turn: only the target tool, and every key present in the slots is required, so the model
        cannot skip the period or filters (optional fields get skipped by constrained decoding)."""
        from copy import deepcopy
        name, args = self._plan_slots(exp)[0]
        spec = deepcopy(next(s for s in self.specs if s["function"]["name"] == name))
        params = spec["function"]["parameters"]
        keep = {k for k, v in args.items() if k in params["properties"] and v not in (None, {})}
        params["required"] = sorted(set(params.get("required", [])) | keep)
        return [spec]

    def _slots_message(self, text: str, exp: Expectation, playbook: str | None) -> str:
        name, args = self._plan_slots(exp)[0]
        lines = [f"USER REQUEST: {text}", f"ACTION: {name}", f"SLOTS (call {name} with exactly these arguments): {jdump(args)}",
                 f"PROPOSED FIRST CALL (emit it as is unless a slot is clearly wrong): {jdump({'tool': name, 'arguments': args})}"]
        if playbook:
            pb = self.c.playbooks[playbook]
            steps = [f"{st['step']}. {st['operation']} {jdump(st['request'], 200)} -> {st['use_output']}" for st in pb["steps"]]
            lines.append(f"PLAYBOOK {playbook} (answer style: {pb['answer_style']}):\n" + "\n".join(steps))
        return "\n".join(lines)

    def _execute(self, text: str, exp: Expectation, playbook: str | None, calls: list[Call], gates: Gates, tb: ToolBox,
                 tr: Trace, s: Session) -> tuple[bool, str]:
        cfg = self.cfg
        attempts = 0
        repairs = 0
        any_match = playbook is not None
        if cfg.plan_mode == "slots":
            for name, args in self._plan_slots(exp):
                v = gates.check(name, args, calls, attempts)
                attempts += 1
                if not v.ok:
                    tr.event("gate_reject", tool=name, gate=v.gate, messages=v.messages)
                    return False, v.hint()
                call = tb.execute(name, v.args or args)
                calls.append(call)
                tr.event("tool_call", tool=name, args=call.args, ok=call.ok, error=call.error, latency=round(call.latency, 3))
                if not call.ok:
                    return False, call.error or "tool error"
            rep = finish_checks(exp, calls, self.c, attempts, cfg.step_budget) if cfg.gates else None
            tr.event("finish_check", ok=(rep.ok if rep else True), violations=[v.message for v in rep.violations] if rep else [])
            return (True, "") if (rep is None or rep.ok) else (False, rep.hint())

        msgs: list[dict] = [{"role": "system", "content": PLANNER_SYSTEM + "\n\n" + self.c.prompt_summary()},
                            {"role": "user", "content": self._slots_message(text, exp, playbook)}]
        reason = "step budget used"
        while attempts < cfg.step_budget:
            use_specs = self._first_specs(exp) if not calls and playbook is None else self.specs
            reply = self.llm.chat(msgs, tools=use_specs, max_tokens=700)
            tr.event("llm_plan", content=reply.content[:200], tool_calls=reply.tool_calls, latency=round(reply.latency, 2))
            if reply.tool_calls:
                tc_msgs, tool_msgs = [], []
                for i, tc in enumerate(reply.tool_calls[:3]):
                    cid = f"call_{attempts}_{i}"
                    name, args = tc["name"], tc["arguments"]
                    tc_msgs.append({"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}})
                    attempts += 1
                    v = gates.check(name, args, calls, attempts - 1)
                    if not v.ok:
                        repairs += 1
                        tr.event("gate_reject", tool=name, args=args, gate=v.gate, messages=v.messages)
                        tool_msgs.append({"role": "tool", "tool_call_id": cid, "content": v.hint()})
                        continue
                    call = tb.execute(name, v.args or args)
                    calls.append(call)
                    tr.event("tool_call", tool=name, args=call.args, ok=call.ok, error=call.error, latency=round(call.latency, 3))
                    if not call.ok:
                        repairs += 1
                        content = jdump({"error": call.error, "hint": "fix the arguments using this error and call again"})
                    else:
                        content = jdump(tb.view(call), 3500)
                    tool_msgs.append({"role": "tool", "tool_call_id": cid, "content": content})
                msgs.append({"role": "assistant", "content": reply.content or "", "tool_calls": tc_msgs})
                msgs += tool_msgs
                if repairs > cfg.max_repairs and cfg.gates:
                    return False, "too many rejected or failed calls"
                if cfg.gates and playbook is None:
                    # single-step request: stop as soon as the finish gate is satisfied (saves a model round)
                    rep = finish_checks(exp, calls, self.c, attempts, cfg.step_budget)
                    if rep.ok:
                        tr.event("finish_check", ok=True, violations=[], early=True)
                        return True, ""
                continue
            # the model believes it is done: finish gate
            msgs.append({"role": "assistant", "content": reply.content or "DONE"})
            if not cfg.gates:
                return (True, "") if any(x.ok for x in calls) else (False, "no successful call")
            rep = finish_checks(exp, calls, self.c, attempts, cfg.step_budget)
            if any_match and rep.violations and all(v.code == "state_mismatch" for v in rep.violations):
                if self._any_analyze_matches(exp, calls):
                    rep.violations = []
            tr.event("finish_check", ok=rep.ok, violations=[v.message for v in rep.violations])
            if rep.ok:
                return True, ""
            repairs += 1
            reason = rep.hint()
            if repairs > cfg.max_repairs:
                return False, reason
            msgs.append({"role": "user", "content": rep.hint()})
        return False, reason

    def _any_analyze_matches(self, exp: Expectation, calls: list[Call]) -> bool:
        from .slots import diff_requests
        return any(x.ok and x.name == "analyze" and not diff_requests(exp.request or {}, x.applied or {}, self.c) for x in calls)

    # ------------------------------------------------------------------ results
    def _commit(self, s: Session, new: State, exp: Expectation, calls: list[Call]) -> None:
        if exp.action in ("analyze", "records"):
            s.state = new
        if exp.action == "analyze":
            call = next((x for x in reversed(calls) if x.ok and x.name == "analyze"), None)
            if call:
                gb = (call.applied or {}).get("group_by", "none")
                s.last_group_by = gb
                s.last_rows = call.data.get("rows") or []
        elif exp.action == "related" and exp.entity:
            typ, ident = exp.entity
            s.last_entity = exp.entity
            rel = next((x for x in reversed(calls) if x.ok and x.name == "related"), None)
            s.last_related = rel.data if rel else None
            f = ENTITY_FILTER.get(typ)
            if f:
                s.state.filters[f] = ident
        elif exp.action == "navigate":
            if exp.scenario_id and exp.scenario_id != s.state.scenario_id:
                s.state = State(scenario_id=exp.scenario_id)
                s.last_rows, s.last_group_by, s.last_entity = [], "none", None

    def _destination(self, exp: Expectation, calls: list[Call], tb: ToolBox) -> str | None:
        if exp.action == "analyze":
            call = next((x for x in reversed(calls) if x.ok and x.name == "analyze"), None)
            return call.deep_link if call else None
        if exp.action == "related":
            return self.backend.route_for(exp.entity[0], exp.entity[1]) if exp.entity else None
        if exp.action == "records":
            flt = (exp.request or {}).get("filters") or {}
            for fname, page in RECORDS_PAGE_PRECEDENCE:
                if flt.get(fname) is not None:
                    return self.backend.route_for({"item": "stock_item", "purchase": "purchase_order"}.get(page, page), flt[fname])
            return "#/overview"
        call = next((x for x in reversed(calls) if x.ok and x.name == "open_page"), None)
        return call.deep_link if call else None
