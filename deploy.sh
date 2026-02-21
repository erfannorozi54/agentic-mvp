#!/bin/bash
cd "$(dirname "$0")"

pkill -9 -f "chainlit run app.py" 2>/dev/null
sleep 3

rm -f logs/*.log
rm -rf __pycache__

mkdir -p logs uploads

~/.virtualenvs/agentic-mvp/bin/chainlit run app.py --host 0.0.0.0 -h > logs/chainlit_run.log 2>&1 &
echo "Started (PID: $!)"
sleep 5
cat logs/chainlit_run.log
