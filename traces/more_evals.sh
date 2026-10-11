#!/bin/bash
# Extra evaluations on the dev split with the final configuration (R1-32B slots mode, R1-written answers).
cd /home/dheeraj/Agentic_Hackathon
source r1.env
export WWI_URL=http://10.9.0.105:8017
PY=.venv/bin/python
$PY -m eval.run_v2 --split dev --what utterances --workers 2 --plan-mode slots --out evidence/dev_utts_r1.json > traces/dev_utts.log 2>&1
$PY -m eval.run_v2 --split dev --what chains --workers 2 --plan-mode slots --k 3 --out evidence/passk3_r1.json > traces/passk3.log 2>&1
echo done > traces/more_evals.done
