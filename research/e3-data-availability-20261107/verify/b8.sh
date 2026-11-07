# 逐条确认「没有退市字段」
grep -rn "delist\|退市" backend/app --include=*.py
