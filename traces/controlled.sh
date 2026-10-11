#!/bin/bash
cd /home/dheeraj/Agentic_Hackathon
source r1.env
export WWI_URL=http://10.9.0.105:8017
.venv/bin/python -m eval.run_v2 --split dev --what chains --workers 2 --plan-mode slots --out evidence/ctl_slots_r1.json > traces/ctl_slots.log 2>&1
.venv/bin/python -m eval.run_v2 --split dev --what chains --workers 2 --plan-mode llm --out evidence/ctl_llm_r1.json > traces/ctl_llm.log 2>&1
