"""Print why steps failed in a run file: python -m eval.show_fail evidence/run.json [--utt]"""
import json, sys
d = json.load(open(sys.argv[1]))
if "--utt" in sys.argv:
    for u in d["utterances"]:
        if not u["pass"]:
            print(u["id"], "|", u["utterance"][:90], "|", "; ".join(u["why"])[:400])
else:
    for run in d["chains"][:1]:
        for ch in run:
            for s in ch["steps"]:
                if not s["pass"]:
                    print(ch["task_id"], s["step"], "|", s["utterance"][:80], "|", "; ".join(s["why"])[:500])
