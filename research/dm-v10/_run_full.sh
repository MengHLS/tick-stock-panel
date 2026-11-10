#!/usr/bin/env bash
cd /c/work/sourcecode/tick-stock-panel/backend || exit 9
OUT=/c/work/sourcecode/tick-stock-panel/research/dm-v10/full_suite_A.log
{ echo "START $(date -Iseconds)"; echo "PY $(./.venv/Scripts/python.exe -V 2>&1)"; echo "PYTEST $(PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest --version 2>&1)"; } > "$OUT"
PYTHONUTF8=1 ./.venv/Scripts/python.exe -m pytest tests/ -q >> "$OUT" 2>&1
echo "PYTEST_EXIT=$?" >> "$OUT"
echo "END $(date -Iseconds)" >> "$OUT"
