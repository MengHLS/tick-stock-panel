import sys
from pathlib import Path
REPO=Path(r"C:/work/sourcecode/tick-stock-panel"); sys.path.insert(0,str(REPO/"backend"))
from app.factors import gate
from app.factors.dsl import BASE_COLUMNS
from app.strategy.custom_signals import ALLOWED_FIELDS
u=gate._column_universe()
print("universe", len(u))
print("ALLOWED_FIELDS", len(ALLOWED_FIELDS))
print("AF - U (in AF, not in universe):", sorted(ALLOWED_FIELDS-u))
print("count", len(ALLOWED_FIELDS-u))
print("U - AF count", len(u-ALLOWED_FIELDS))
print("U - AF sorted:", sorted(u-ALLOWED_FIELDS))
print("BASE_COLUMNS", len(BASE_COLUMNS), sorted(BASE_COLUMNS))
