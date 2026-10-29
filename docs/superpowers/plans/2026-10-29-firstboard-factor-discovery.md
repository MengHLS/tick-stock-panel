# First-Board Factor Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only extension page that automatically finds existing T-1/T-close factors distinguishing first-board events with strong future maximum returns.

**Architecture:** A new backend extension package loads the enriched panel through `BacktestEngine`, computes T+1-based 20-day outcome labels and factor values through existing materialization paths, selects explainable factor rules on a chronological training split, and exposes report/event endpoints. A new frontend source extension renders the report, rules, sample accounting, warnings, and paginated event details without modifying core routes or APIs.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Polars, NumPy, pytest; React 18, TypeScript, TanStack Query, Tailwind CSS, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-29-firstboard-factor-discovery-design.md`

## Global Constraints

- Primary label: `mfe_20d = max(high[T+1..T+20]) / open[T+1] - 1`; `strong = mfe_20d >= 0.20`.
- Auxiliary outcomes: 20-day close return, 20-day MAE, and `mae_20d <= -0.08`.
- Features may only use T-1 or T-close data; the action price is T+1 open.
- Selection uses the chronological first 70% of event dates; validation uses the final 30%.
- Daily features and samples are never randomly shuffled.
- Backend must reuse `BacktestEngine`, the factor registry, and existing factor materialization; no duplicate indicator implementation.
- Exclude right-censored, entry-unavailable, entry-limit-locked, and suspected scale-break events from automatic discovery.
- Historical first-board identity remains platform-defined and uncertified.
- Do not add SciPy, scikit-learn, or another model/statistics dependency.
- Do not modify `backend/app/main.py`, core mining runtime, core router, `frontend/src/lib/api.ts`, or `frontend/src/lib/queryKeys.ts`.
- Do not commit, push, merge, delete user data, or rewrite existing uncommitted changes.

## Review Focus

- **T+1 execution leakage:** a T-close signal must never use T+1 open or later values as a feature.
- **Right-censored outcomes:** events near the data edge must be excluded from training, not given partial labels.
- **Entry unavailable or limit-locked:** a nominal T+1 open must not be treated as tradable.
- **Validation contamination:** factor selection, threshold choice, and rule ranking may use training data only.
- **Unreliable historical inputs:** current-share turnover, empty fundamentals, and snapshot-only extension factors must not silently enter discovery.

---

### Task 1: Event Outcome Builder

**Files:**
- Create: `backend/app/custom/firstboard_discovery/__init__.py`
- Create: `backend/app/custom/firstboard_discovery/outcomes.py`
- Create: `backend/tests/test_firstboard_discovery.py`

**Interfaces:**
- Consumes: a sorted or unsorted Polars panel with `symbol`, `date`, `open`, `high`, `low`, `close`, `raw_open`, `raw_close`, `consecutive_limit_ups`; optional `limit_up_price`, `name`.
- Produces:
  - `build_event_samples(panel: pl.DataFrame, *, horizon: int = 20, strong_threshold: float = 0.20) -> pl.DataFrame`
  - Output columns: `event_id, symbol, name, date, row_index, entry_date, entry_open, sessions_observed, right_censored, entry_unavailable, entry_limit_locked, scale_break_suspected, mfe_20d, close_return_20d, mae_20d, stop_touched, strong`

- [ ] **Step 1: Write failing outcome tests**

Add tests using small synthetic Polars panels:

```python
def test_outcomes_use_next_open_and_twenty_observed_sessions():
    ...
    assert row["entry_date"] == date(2026, 1, 6)
    assert row["mfe_20d"] == pytest.approx(0.20)
    assert row["close_return_20d"] == pytest.approx(0.10)
    assert row["mae_20d"] == pytest.approx(-0.05)
    assert row["strong"] is True
```

Also pin:

```python
def test_right_censored_event_is_not_labeled():
    assert row["right_censored"] is True
    assert row["strong"] is None

def test_limit_locked_entry_is_excluded():
    assert row["entry_limit_locked"] is True
    assert row["strong"] is None

def test_future_rows_do_not_change_an_earlier_event():
    assert before.equals(after)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
cd backend
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: FAIL because `build_event_samples` does not exist.

- [ ] **Step 3: Implement `build_event_samples`**

Sort by `symbol,date`, locate `consecutive_limit_ups == 1`, use the next row per symbol as T+1, slice exactly the next `horizon` rows for outcomes, and return one record per event. Compute returns from adjusted prices; compare T+1 `raw_open` with `limit_up_price` for `entry_limit_locked`. Mark `scale_break_suspected` when `close/raw_close` differs from the event-day ratio by more than `0.001` inside the outcome window. Set `strong` only when the event is eligible and not right-censored.

- [ ] **Step 4: Run outcome tests**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: PASS.

---

### Task 2: Discovery Statistics and Rule Search

**Files:**
- Create: `backend/app/custom/firstboard_discovery/discovery.py`
- Modify: `backend/tests/test_firstboard_discovery.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class FactorScore:
    factor_id: str
    snapshot: str
    direction: str | None
    auc: float | None
    p_value: float | None
    q_value: float | None
    coverage: float
    train_count: int

def score_factor(factor_id: str, snapshot: str, values: Sequence[float | None], labels: Sequence[bool | None]) -> FactorScore
def search_rules(events: pl.DataFrame, factor_columns: Sequence[tuple[str, str]], *, train_end: date, base_rate: float) -> list[dict]
```

`events` contains one row per event, `strong`, `date`, and columns named
`f"{snapshot}__{factor_id}"`. `search_rules` consumes that interface.

- [ ] **Step 1: Write failing AUC tests**

Pin perfect separation, inverse direction, ties, missing values, and BH-FDR:

```python
assert score_factor("f", "D_close", [1, 2, 3, 4], [False, False, True, True]).auc == 1.0
assert score_factor("f", "D_close", [1, 2, None, 4], [False, False, True, True]).direction == "high"
assert bh_fdr_qvalues([0.01, 0.04, None]) == pytest.approx([0.02, 0.04, None], nan_ok=True)
```

- [ ] **Step 2: Write failing rule-search tests**

Create events where one factor has a clear training-period threshold. Assert:

- only training dates select the rule;
- changing validation feature values does not change selected conditions;
- rules with fewer than 30 training hits or 15 validation hits are not eligible;
- outputs contain `conditions`, `train_strong_rate`, `validation_strong_rate`, `lift`, and `validation_lift`.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: FAIL because the statistics helpers do not exist.

- [ ] **Step 4: Implement statistics and bounded rule search**

Use NumPy rank-based AUC with tie-aware Mann-Whitney p-values and the existing
`bh_fdr_qvalues` from `app.backtest.stats_v2`. Rank at most eight factors by
training `abs(auc - 0.5)`. Search:

- 1D threshold quantiles at 0.2/0.4/0.6/0.8;
- 2D tercile cells for all pairs among the top four factors;
- 3D tercile cells for the top three factors only when training events >= 600.

Select and rank rules using training data only. Record validation metrics after
selection.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: PASS.

---

### Task 3: Discovery Service and Snapshot Cache

**Files:**
- Create: `backend/app/custom/firstboard_discovery/service.py`
- Modify: `backend/tests/test_firstboard_discovery.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class DiscoveryParams:
    start: date
    end: date
    horizon: int = 20
    strong_threshold: float = 0.20
    snapshot_mode: Literal["D_minus_1", "D_close", "both"] = "both"

class FirstboardDiscoveryService:
    def __init__(self, repository: Any, engine: Any | None = None) -> None: ...
    def report(self, params: DiscoveryParams) -> dict: ...
    def events(self, params: DiscoveryParams, *, rule_id: str | None = None, page: int = 1, page_size: int = 100) -> dict: ...
```

- [ ] **Step 1: Write failing service tests**

Use a fake engine returning a fixed panel. Pin:

```python
def test_report_excludes_ineligible_events_and_returns_sample_accounting():
    ...
    assert report["sample"]["eligible_events"] == 4
    assert report["sample"]["excluded"]["right_censored"] == 1
    assert report["split"]["train_end"] < report["split"]["validation_start"]

def test_events_endpoint_paginates_and_filters_by_rule():
    ...
    assert payload["page_size"] == 2
    assert all(rule_id in row["rule_ids"] for row in payload["rows"])

def test_validation_values_do_not_change_selected_rules():
    ...
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: FAIL because `FirstboardDiscoveryService` does not exist.

- [ ] **Step 3: Implement panel loading and factor materialization**

Load stock enriched rows through `engine.load_panel` with only required physical
columns. Add the T+1 limit price through `compute_limit_signals`, using
`repository.get_instruments_asset("stock")` and historical shares. Build event
samples first, then materialize candidate factors with
`FactorBacktestService._compute_missing_factors`, and join T-1/T-close values to
the event rows.

Exclude the factor groups specified in the design. Capture
`engine.data_generation("stock")` before loading and assert it remains unchanged
after materialization.

- [ ] **Step 4: Implement report, split, and event projection**

Produce the report schema from the spec, including `elapsed_ms`, warnings,
sample accounting, factor rows, rule rows, and `algorithm_version`. Cache up to
four immutable report/event snapshots using a key containing generation,
params, factor ids/versions, and algorithm version. Protect only cache
read/write with a lock.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: PASS.

---

### Task 4: Backend Extension Registration and API

**Files:**
- Modify: `backend/app/custom/firstboard_discovery/__init__.py`
- Modify: `backend/tests/test_firstboard_discovery.py`

**Interfaces:**

```text
GET /api/custom/firstboard-discovery/report
GET /api/custom/firstboard-discovery/events
```

Query parameters: `start`, `end`, `horizon=20`, `strong_threshold=0.20`,
`snapshot_mode`, `page=1`, `page_size=100`, optional `rule_id`.

- [ ] **Step 1: Write failing API tests**

Use a fake `ExtensionContext` repository and monkeypatch the module-level
service factory. Assert:

```python
assert client.get("/api/custom/firstboard-discovery/report", params=valid).status_code == 200
assert client.get("/api/custom/firstboard-discovery/report", params=invalid).status_code == 400
assert client.get("/api/custom/firstboard-discovery/events", params={**valid, "page_size": 201}).status_code == 422
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py -q
```

Expected: FAIL because the routes are not registered.

- [ ] **Step 3: Implement extension setup and startup**

Define `EXTENSION_ID = "official.firstboard-discovery"` and
`EXTENSION_API_VERSION`. In `startup(context)`, construct the service from the
stable repository context. In `setup(registrar)`, register a router whose
handlers fail closed with `503` until startup completes. Convert generation
changes to `409` with a retry message and invalid requests to `400`.

- [ ] **Step 4: Run tests and the custom extension loader tests**

Run:

```bash
uv run --frozen pytest tests/test_firstboard_discovery.py tests/test_backend_extensions.py -q
```

Expected: PASS.

---

### Task 5: Frontend Extension Page

**Files:**
- Create: `frontend/src/custom/firstboard-discovery/extension.tsx`
- Create: `frontend/src/custom/firstboard-discovery/extension.test.tsx`

**Interfaces:**
- Backend report/event schemas from Task 4.
- Route: `/firstboard-discovery`
- Navigation label: `首板因子区分`

- [ ] **Step 1: Write failing frontend tests**

Test the exported extension descriptor and pure helpers:

```ts
expect(extension.routes?.[0]?.path).toBe('/firstboard-discovery')
expect(extension.navigation?.[0]?.label).toBe('首板因子区分')
expect(ruleMatches(event, rule)).toBe(true)
expect(formatQualityFlags({ right_censored: true })).toContain('20日未走完')
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
cd frontend
pnpm exec vitest run src/custom/firstboard-discovery/extension.test.tsx
```

Expected: FAIL because the extension does not exist.

- [ ] **Step 3: Implement the extension**

Build a responsive page with date controls, snapshot selector, sample accounting,
factor and rule tables, rule filtering, paginated events, loading/empty/error/
insufficient states, and the fixed warnings from the spec. Keep request URLs in
one namespaced client function inside the extension file.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
pnpm exec vitest run src/custom/firstboard-discovery/extension.test.tsx
```

Expected: PASS.

---

### Task 6: Full Verification and Diff Audit

**Files:**
- Review: all files changed by Tasks 1-5

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
uv run --frozen pytest tests/test_firstboard_discovery.py tests/test_backend_extensions.py tests/test_factor_registry.py tests/test_first_board_event_chain.py -q
```

Expected: PASS.

- [ ] **Step 2: Run backend lint**

Run:

```bash
uv run --frozen ruff check app/custom/firstboard_discovery tests/test_firstboard_discovery.py
```

Expected: no warnings or errors.

- [ ] **Step 3: Run frontend build and tests**

Run:

```bash
cd ../frontend
pnpm exec vitest run src/custom/firstboard-discovery/extension.test.tsx
pnpm build
```

Expected: both commands pass.

- [ ] **Step 4: Check diff hygiene**

Run:

```bash
cd ..
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors, no generated data, and only task-related files
plus the design/plan documents.

- [ ] **Step 5: Report verification and residual risk**

Report exact commands and results, distinguish tests not run, and list the
remaining limits: historical board identity, threshold choice, overlapping
outcome windows, and the absence of live trading validation.
