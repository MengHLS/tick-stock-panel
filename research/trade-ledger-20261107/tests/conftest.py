import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 用户提供的券商交割单（GBK，1055 行）。缺失时相关用例自动跳过。
SAMPLE_CSV = Path(r"C:\Users\A\.openmausbot\attachments\1d005b5c-74e7-4130-87ec-bb9d6a9d8236.csv")
BASELINE = ROOT.parent / "jiaogedan-review-20261107" / "data"


@pytest.fixture(scope="session")
def sample_csv() -> Path:
    if not SAMPLE_CSV.exists():
        pytest.skip(f"样例交割单不存在: {SAMPLE_CSV}")
    return SAMPLE_CSV


@pytest.fixture(scope="session")
def baseline_dir() -> Path:
    if not BASELINE.exists():
        pytest.skip(f"基准目录不存在: {BASELINE}")
    return BASELINE
