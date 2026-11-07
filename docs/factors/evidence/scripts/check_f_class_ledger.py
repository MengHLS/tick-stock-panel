#!/usr/bin/env python
"""F-class registration ledger self-check (read-only).

Reads:
  docs/factors/evidence/f_class_registry.json           (machine-readable ledger)
  docs/architecture/archive/FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md
                                                        (section 7.1 - frozen authority)
  docs/architecture/FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md
                                                        (section 7.1 - READ SOURCE ONLY: the
                                                         version number is not binding; check
                                                         [4] reads this file's 7.1 block and
                                                         matches it against the registered
                                                         block hash)
  docs/factors/F_CLASS_REGISTRATION_20261107.md         (human ledger)

Prints one line per check with its violation count, plus a per-factor table,
then compares the computed counts with the numbers recorded in the JSON
`self_check` block. Exits 1 if any violation or any recorded/computed mismatch.

Binding (v5.9): the judgment object is the SECTION 7.1 BLOCK, not the whole version file.
Both contracts must carry a 7.1 block whose sha256 equals the registered constant in BOTH
calibers -- LF-normalized (2,514 chars / 6d3db013...) and raw CRLF (2,541 chars / a8e88134...).
Binding a whole-file hash let a rewrite of 7.1 inside any numbered revision pass silently;
binding the block does not. The version number is provenance, never a judgment input.

Run from anywhere (paths are resolved from this file):
    python docs/factors/evidence/scripts/check_f_class_ledger.py

Output is intentionally ASCII-only so it survives every console codepage.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

# Line-ending bytes, spelled without escapes so no tool layer can mangle them.
CRLF = bytes((13, 10))
LF = bytes((10,))

REPO = Path(__file__).resolve().parents[4]
REGISTRY = REPO / "docs" / "factors" / "evidence" / "f_class_registry.json"
LEDGER = REPO / "docs" / "factors" / "F_CLASS_REGISTRATION_20261107.md"

# --- registered section 7.1 block hash (v5.9) ------------------------------
# Binding object = the section 7.1 BLOCK, not the whole version file. The block is the same
# text in the frozen v0.3 archive and in every numbered revision (v0.4 .. v0.12), so its hash
# is the stable object while the version number is only provenance. Two calibers, BOTH must
# match:
#   1) LF normalized  (CRLF collapsed to LF)   2,514 chars / 6d3db013...
#   2) raw CRLF kept  (original line endings)  2,541 chars / a8e88134...
# They differ by exactly 27 characters = one CR per line of the 27-line block; the text is
# identical. A citation must name its caliber: the two digests are different, so "the 7.1
# hash" with no caliber is ambiguous.
S71_LF_CHARS = 2514
S71_LF_SHA256 = "6d3db0139a45f54c9e7399e19239929b21d0c37f660ceafaf52f707835b449d8"
S71_CRLF_CHARS = 2541
S71_CRLF_SHA256 = "a8e88134f60b504c5bb7e6280e419e05b1c05afc13ae5abc1fd028dd1db737ef"

# Dual binding, kept: (1) the immutable frozen archive, (2) one current revision used only as
# a READ SOURCE. Neither file's whole-file hash is a judgment input any more -- only the 7.1
# block hash is (S71_*). So moving this pointer to a later revision cannot flip a result by
# itself, and rewriting 7.1 inside any revision can no longer pass silently.
CONTRACT = (
    REPO
    / "docs"
    / "architecture"
    / "archive"
    / "FACTOR_ENGINE_CONTRACTS_20261107_v0.3_FROZEN.md"
)
CONTRACT_LIVE = (
    REPO
    / "docs"
    / "architecture"
    / "FACTOR_ENGINE_CONTRACTS_20261107_v0.12.md"
)

# research_name, uf_ id, warmup_bars -- fixed by the contract F-A1 and the task brief.
EXPECTED = [
    ("vol60", "uf_vol60", 61),
    ("ma120", "uf_ma120", 121),
    ("ma200", "uf_ma200", 201),
    ("prior_high_20", "uf_prior_high_20", 21),
    ("prior_high_55", "uf_prior_high_55", 56),
    ("prior_high_250", "uf_prior_high_250", 251),
    ("prior_low_10", "uf_prior_low_10", 11),
    ("prior_vol_20", "uf_prior_vol_20", 21),
]

ID_RE = re.compile(r"^uf_[a-z0-9_]{1,40}$")
# | `vol60` | `ts_std(...)` | **61** | `{close}` | ...
CONTRACT_ROW_RE = re.compile(
    r"^\|\s*`([a-z0-9_]+)`\s*\|\s*`([^`]+)`\s*\|\s*\*\*(\d+)\*\*\s*\|\s*`([^`]+)`\s*\|"
)

REQUIRED_FIELDS = [
    "research_name",
    "id",
    "canonical_id",
    "aliases",
    "superseded_by",
    "canonical_reason",
    "label",
    "group",
    "formula_text",
    "window",
    "warmup_bars",
    "dependencies",
    "semantics",
    "shift",
    "price_basis",
    "unit",
    "scale_free",
    "direction",
    "status",
    "version",
    "strategy_usable",
    "replaces",
    "replaced_by",
    "relation_note",
    "serves_strategies",
    "research_source",
]


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def lf_normalized_sha256(path: Path) -> str:
    """sha256 over the file bytes with CRLF collapsed to LF.

    Fingerprints bind on this hash, not on raw bytes: these files are not in git and other
    writers have flipped their line endings, which would otherwise invalidate every recorded
    hash without changing one character of content. Line endings are LF-only by policy.
    """
    return hashlib.sha256(path.read_bytes().replace(CRLF, LF)).hexdigest()


def rel(path: Path) -> str:
    """Repo-relative label when the file is inside the repo, absolute path otherwise.

    Both bound contracts normally live in the repo, but a negative test may point at a copy
    outside it. That case must print a usable label and FAIL on the block hash -- never raise
    ValueError from relative_to() and turn a negative test into a traceback with no verdict.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def fingerprint(label: str, path: Path) -> str:
    """One report line: LF-normalized sha256 plus size / line / CRLF counts."""
    raw = path.read_bytes()
    size, lines, crlf = len(raw), raw.count(LF), raw.count(CRLF)
    return (
        f"  {label:<9}: sha256 {lf_normalized_sha256(path)}"
        f"  size {size} B  lines {lines}  crlf {crlf}"
    )


def contract_section_71(path: Path) -> tuple[list[str], int, int]:
    """Return (lines, start_index, end_index) of the section 7.1 block of one contract file."""
    if not path.exists():
        raise SystemExit(f"FATAL: missing bound contract file {path}")
    text = path.read_text(encoding="utf-8").splitlines()
    start = end = None
    for idx, line in enumerate(text):
        if line.startswith("### 7.1"):
            start = idx
        elif start is not None and line.startswith("### 7.2"):
            end = idx
            break
    if start is None or end is None:
        raise SystemExit(f"FATAL: cannot locate contract section 7.1 .. 7.2 in {path}")
    return text, start, end


def section_71_block(path: Path) -> dict:
    """Section 7.1 of one contract file, hashed in BOTH registered calibers.

    The block includes its trailing newline. Both calibers are returned because both are
    registered constants and both must match: LF-normalized (2,514 chars) and raw CRLF
    (2,541 chars). They hash differently on purpose -- same text, different line endings.
    """
    text, start, end = contract_section_71(path)
    lines = text[start:end]
    nl = chr(10)
    lf = nl.join(lines) + nl
    crlf = (chr(13) + nl).join(lines) + chr(13) + nl
    return {
        "path": path,
        "text": lf,
        "n_lines": len(lines),
        "lf_chars": len(lf),
        "lf_sha256": hashlib.sha256(lf.encode("utf-8")).hexdigest(),
        "crlf_chars": len(crlf),
        "crlf_sha256": hashlib.sha256(crlf.encode("utf-8")).hexdigest(),
    }

def parse_contract_rows(block: str) -> dict[str, dict]:
    """Extract the 8 rows of one section 7.1 block (name -> formula/warmup/deps)."""
    rows: dict[str, dict] = {}
    for line in block.splitlines():
        m = CONTRACT_ROW_RE.match(line)
        if m:
            name, formula, warmup, deps = m.groups()
            rows[name] = {"formula": formula, "warmup": int(warmup), "deps": deps}
    return rows


def trailing_window(formula: str) -> int | None:
    """Last integer argument of the formula, i.e. the window N."""
    nums = re.findall(r"\b(\d+)\b", formula)
    return int(nums[-1]) if nums else None


def main() -> int:
    if not REGISTRY.exists():
        raise SystemExit(f"FATAL: missing {REGISTRY}")
    data = load_json(REGISTRY)
    factors = data["factors"]
    s71_arch = section_71_block(CONTRACT)
    s71_live = section_71_block(CONTRACT_LIVE)
    contract = parse_contract_rows(s71_arch["text"])
    contract_live = parse_contract_rows(s71_live["text"])
    ledger_text = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""

    checks: list[dict] = []

    def add(check_id: str, rule: str, violations: list[str]) -> None:
        checks.append({"id": check_id, "rule": rule, "violations": violations})

    # --- 1. research name <-> uf_ id bijection -------------------------------
    v: list[str] = []
    names = [f.get("research_name") for f in factors]
    ids = [f.get("id") for f in factors]
    for name in sorted({n for n in names if names.count(n) > 1}):
        v.append(f"research_name duplicated: {name}")
    for fid in sorted({i for i in ids if ids.count(i) > 1}):
        v.append(f"id duplicated: {fid}")
    for f in factors:
        if not ID_RE.match(str(f.get("id", ""))):
            v.append(f"id fails ^uf_[a-z0-9_]{{1,40}}$: {f.get('id')!r}")
        if not f.get("research_name"):
            v.append(f"missing research_name for id {f.get('id')!r}")
    if len(names) != len(set(names)) or len(ids) != len(set(ids)):
        v.append("mapping is not 1:1")
    add(
        "research_name_id_bijection",
        "research_name <-> uf_ id is 1:1, ids match ^uf_[a-z0-9_]{1,40}$, no duplicates",
        v,
    )

    # --- 2. prior_* shift == 1 and warmup >= N + 1 -------------------------
    v = []
    for f in factors:
        name = str(f.get("research_name", ""))
        if not name.startswith("prior_"):
            continue
        window = f.get("window")
        warmup = f.get("warmup_bars")
        shift = f.get("shift")
        if shift != 1:
            v.append(f"{name}: shift={shift!r}, expected 1")
        if f.get("semantics") != "prior":
            v.append(f"{name}: semantics={f.get('semantics')!r}, expected 'prior'")
        if not isinstance(window, int) or not isinstance(warmup, int):
            v.append(f"{name}: window/warmup not int ({window!r}/{warmup!r})")
        elif warmup < window + 1:
            v.append(f"{name}: warmup {warmup} < window {window} + 1")
        n_formula = trailing_window(str(f.get("formula_text", "")))
        if n_formula is not None and n_formula != window:
            v.append(f"{name}: window field {window} != trailing formula arg {n_formula}")
    for f in factors:
        if str(f.get("research_name", "")).startswith("prior_"):
            continue
        if f.get("shift") != 0:
            v.append(f"{f.get('research_name')}: non-prior shift={f.get('shift')!r}, expected 0")
        if f.get("semantics") != "incl_today_close":
            v.append(
                f"{f.get('research_name')}: semantics={f.get('semantics')!r}, "
                "expected 'incl_today_close'"
            )
    add(
        "prior_shift_and_warmup",
        "all prior_* have shift==1, semantics=='prior', warmup_bars >= N+1; "
        "non-prior rows have shift==0, semantics=='incl_today_close'",
        v,
    )

    # --- 3. expected id set and warmup order -------------------------------
    v = []
    got = [(f.get("research_name"), f.get("id"), f.get("warmup_bars")) for f in factors]
    if len(got) != len(EXPECTED):
        v.append(f"factor count {len(got)} != expected {len(EXPECTED)}")
    for exp, actual in zip(EXPECTED, got):
        if exp != actual:
            v.append(f"row mismatch: expected {exp}, got {actual}")
    add(
        "expected_id_set_and_warmup_order",
        "ids/set and warmup order equal 61/121/201/21/56/251/11/21 for the fixed 8 ids",
        v,
    )

    # --- 4. formula_text verbatim vs contract section 7.1 -----------------
    v = []
    # Block-hash binding (v5.9). Judgment inputs: the section 7.1 BLOCK of each bound file,
    # in BOTH registered calibers. Whole-file hashes and version numbers are NOT judged, so a
    # 7.1 rewrite inside any numbered revision trips this check instead of passing silently.
    registered = {
        "LF": (S71_LF_CHARS, S71_LF_SHA256),
        "CRLF": (S71_CRLF_CHARS, S71_CRLF_SHA256),
    }
    for label, blk in (("archive", s71_arch), ("contract", s71_live)):
        where = rel(blk["path"])
        for caliber, (chars, digest) in registered.items():
            got_chars = blk["lf_chars"] if caliber == "LF" else blk["crlf_chars"]
            got_digest = blk["lf_sha256"] if caliber == "LF" else blk["crlf_sha256"]
            if got_chars != chars:
                v.append(
                    f"{label} ({where}): section 7.1 {caliber} {got_chars} chars "
                    f"!= registered constant {chars} chars"
                )
            if got_digest != digest:
                v.append(
                    f"{label} ({where}): section 7.1 {caliber} sha256 {got_digest} "
                    f"!= registered constant {digest}"
                )
    if s71_arch["lf_sha256"] != s71_live["lf_sha256"]:
        v.append(
            "section 7.1 LF sha256 differs between the two bound files: "
            f"archive {s71_arch['lf_sha256']} ({s71_arch['lf_chars']} chars) vs "
            f"contract {s71_live['lf_sha256']} ({s71_live['lf_chars']} chars)"
        )
    if s71_arch["crlf_sha256"] != s71_live["crlf_sha256"]:
        v.append(
            "section 7.1 CRLF sha256 differs between the two bound files: "
            f"archive {s71_arch['crlf_sha256']} ({s71_arch['crlf_chars']} chars) vs "
            f"contract {s71_live['crlf_sha256']} ({s71_live['crlf_chars']} chars)"
        )
    for label, rows in (("frozen v0.3 archive", contract), ("current revision", contract_live)):
        if len(rows) != len(EXPECTED):
            v.append(f"{label}: parsed {len(rows)} rows from 7.1, expected {len(EXPECTED)}")
        for f in factors:
            name = str(f.get("research_name", ""))
            ref = rows.get(name)
            if ref is None:
                v.append(f"{name}: not found in {label} 7.1 table")
                continue
            if f.get("formula_text") != ref["formula"]:
                v.append(
                    f"{name}: formula_text differs from {label}\n"
                    f"      ledger  : {f.get('formula_text')!r}\n"
                    f"      contract: {ref['formula']!r}"
                )
            if f.get("warmup_bars") != ref["warmup"]:
                v.append(f"{name}: warmup {f.get('warmup_bars')} != {label} {ref['warmup']}")
            deps = "{" + ",".join(f.get("dependencies") or []) + "}"
            if deps != ref["deps"]:
                v.append(f"{name}: dependencies {deps} != {label} {ref['deps']}")
    add(
        "formula_verbatim_vs_contract",
        "formula_text/warmup_bars/dependencies are identical to section 7.1 of BOTH bound "
        "contracts (frozen v0.3 archive + one current revision, read source only); each file's "
        "7.1 BLOCK hash must equal the registered constant in BOTH calibers (LF 2,514 chars / "
        "6d3db013... and raw CRLF 2,541 chars / a8e88134...), and the two blocks must be equal "
        "in both calibers; the contract VERSION NUMBER is not a judgment input, but any block "
        "rewrite -> FAIL with both hashes printed",
        v,
    )

    # --- 5. markdown ledger consistency -----------------------------------
    v = []
    if not ledger_text:
        v.append(f"ledger not found: {LEDGER}")
    for f in factors:
        fid = str(f.get("id"))
        formula = str(f.get("formula_text"))
        warmup = f.get("warmup_bars")
        if fid not in ledger_text:
            v.append(f"{fid}: id missing from markdown ledger")
            continue
        if formula not in ledger_text:
            v.append(f"{fid}: formula_text missing from markdown ledger")
        rows = [ln for ln in ledger_text.splitlines() if fid in ln]
        if not any(formula in ln and f"| {warmup} |" in ln for ln in rows):
            v.append(f"{fid}: no single table row holds both formula and warmup {warmup}")
    add(
        "md_ledger_consistency",
        "markdown ledger contains every id, every verbatim formula, and a row carrying the warmup",
        v,
    )

    # --- 6. required fields present ---------------------------------------
    v = []
    for f in factors:
        for key in REQUIRED_FIELDS:
            if key not in f:
                v.append(f"{f.get('id')}: missing field '{key}'")
                continue
            value = f[key]
            if isinstance(value, str) and not value.strip():
                v.append(f"{f.get('id')}: empty field '{key}'")
            if key in ("dependencies", "serves_strategies", "aliases") and value == []:
                v.append(f"{f.get('id')}: empty list '{key}'")
            if key in ("replaces", "replaced_by", "superseded_by") and value is None:
                v.append(f"{f.get('id')}: null list '{key}'")
    add(
        "required_fields_present",
        "every row carries all ledger fields (research name, id, formula, warmup, deps, "
        "semantics, shift, price_basis, unit, scale_free, strategy_usable, replaces/replaced_by, "
        "canonical_id, aliases, superseded_by, canonical_reason, ...)",
        v,
    )

    # --- 7. canonical / alias / superseded_by rules (contract 7.8.2 A-1) ---
    v = []
    canon_ids = {str(f.get("id")) for f in factors}
    alias_map: dict[str, str] = {}
    for f in factors:
        fid = str(f.get("id"))
        cid = f.get("canonical_id")
        if cid != fid:
            v.append(f"{fid}: canonical_id {cid!r} != own id (canonical must be the uf_ id)")
        if not ID_RE.match(str(cid or "")):
            v.append(f"{fid}: canonical_id fails ^uf_[a-z0-9_]{{1,40}}$: {cid!r}")
        aliases = f.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            v.append(f"{fid}: aliases must be a non-empty list, got {aliases!r}")
            aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                v.append(f"{fid}: alias entry is not a non-empty string: {alias!r}")
                continue
            if alias == fid:
                v.append(f"{fid}: alias equals the canonical id")
            if alias in canon_ids:
                v.append(f"{fid}: alias {alias!r} shadows another canonical id")
            alias_map[alias] = fid
        if f.get("research_name") not in aliases:
            v.append(f"{fid}: research_name {f.get('research_name')!r} missing from aliases[]")
        if f.get("alias_of") is not None:
            v.append(f"{fid}: canonical row must not carry alias_of ({f.get('alias_of')!r})")
        sb = f.get("superseded_by")
        if not isinstance(sb, list):
            v.append(f"{fid}: superseded_by must be a list, got {sb!r}")
        elif sb:
            v.append(f"{fid}: canonical row has non-empty superseded_by {sb!r}; nothing may supersede it")
        if not str(f.get("canonical_reason") or "").strip():
            v.append(f"{fid}: empty canonical_reason")
    for f in factors:
        rb = f.get("replaced_by")
        if not isinstance(rb, list):
            v.append(f"{f.get('id')}: replaced_by must be a list, got {rb!r}")
            continue
        for target in rb:
            if target in alias_map:
                v.append(
                    f"{f.get('id')}: replaced_by carries alias {target!r}; replaced_by is "
                    "cross-caliber only, aliases belong in aliases[]/alias_of"
                )
    add(
        "canonical_alias_rules",
        "canonical_id == own uf_ id; aliases[] non-empty and never shadow a canonical id; alias_of "
        "empty and superseded_by=[] on canonical rows; replaced_by never carries an alias "
        "(contract 7.8.2 A-1/A-2)",
        v,
    )

    # --- 8. the 8 dual-id groups are declared and in sync with the rows -----
    v = []
    ruling = data.get("id_canonical_ruling") or {}
    groups = ruling.get("dual_id_groups") or []
    by_id = {str(f.get("id")): f for f in factors}
    if len(groups) != len(EXPECTED):
        v.append(f"dual_id_groups count {len(groups)} != expected {len(EXPECTED)}")
    seen: set[str] = set()
    for g in groups:
        cid = g.get("canonical_id")
        if cid not in by_id:
            v.append(f"group {g.get('n')}: canonical_id {cid!r} is not one of the 8 factor rows")
            continue
        seen.add(str(cid))
        f = by_id[cid]
        if g.get("aliases") != f.get("aliases"):
            v.append(f"{cid}: group aliases {g.get('aliases')!r} != row aliases {f.get('aliases')!r}")
        if g.get("alias") not in (f.get("aliases") or []):
            v.append(f"{cid}: group alias {g.get('alias')!r} not in row aliases")
        if g.get("superseded_by") != []:
            v.append(f"{cid}: group superseded_by must be [], got {g.get('superseded_by')!r}")
        if not str(g.get("canonical_reason") or "").strip():
            v.append(f"{cid}: group canonical_reason empty")
        side = g.get("alias_side") or {}
        if side.get("alias_of") != cid:
            v.append(f"{cid}: alias_side.alias_of {side.get('alias_of')!r} != canonical id")
        if side.get("strategy_usable") is not False:
            v.append(f"{cid}: alias_side.strategy_usable must be exactly False ({side.get('strategy_usable')!r})")
        if side.get("superseded_by") != [cid]:
            v.append(f"{cid}: alias_side.superseded_by must be [{cid!r}]")
    if seen != set(by_id):
        v.append(f"groups do not cover exactly the 8 canonical ids; missing {sorted(set(by_id) - seen)}")
    pa = data.get("prior_amount_20_registered_fact") or {}
    if pa.get("canonical_id") != "prior_amount_20":
        v.append(f"prior_amount_20: canonical_id must be the research name, got {pa.get('canonical_id')!r}")
    if pa.get("aliases") != []:
        v.append(f"prior_amount_20: aliases must be [], got {pa.get('aliases')!r}")
    if pa.get("superseded_by") != []:
        v.append(f"prior_amount_20: superseded_by must be [], got {pa.get('superseded_by')!r}")
    if not str(pa.get("canonical_reason") or "").strip():
        v.append("prior_amount_20: empty canonical_reason")
    if "uf_prior_amount_20" in by_id:
        v.append("uf_prior_amount_20 must not exist as a row (it would create a new dual id)")
    exc = [e for e in (ruling.get("single_sided_exceptions") or []) if e.get("canonical_id") == "prior_amount_20"]
    if not exc:
        v.append("id_canonical_ruling.single_sided_exceptions lacks the prior_amount_20 row")
    elif not str(exc[0].get("canonical_reason") or "").strip():
        v.append("single_sided_exceptions[prior_amount_20]: empty canonical_reason")
    add(
        "dual_id_group_coverage",
        "id_canonical_ruling.dual_id_groups covers exactly the 8 canonical ids, stays in sync with the "
        "factor rows, records alias_side (alias_of + strategy_usable=false + superseded_by=[canonical]), "
        "and keeps prior_amount_20 as the declared single-id exception",
        v,
    )

    # --- 9. markdown ledger carries the three columns, one row per group ----
    v = []
    md_lines = ledger_text.splitlines()
    header = next((ln for ln in md_lines if ln.startswith("| # | `canonical_id`")), None)
    table: list[str] = []
    if header is None:
        v.append("markdown ledger has no canonical/alias table header (| # | `canonical_id` | ...)")
    else:
        for key in ("`canonical_id`", "`aliases[]`", "`superseded_by[]`", "`alias_of`", "`strategy_usable`"):
            if key not in header:
                v.append(f"canonical/alias table header lacks column {key}")
        start = md_lines.index(header)
        for ln in md_lines[start + 2:]:
            if not ln.startswith("|"):
                break
            table.append(ln)
    for f in factors:
        cid = str(f.get("id"))
        aliases = [a for a in (f.get("aliases") or []) if isinstance(a, str)]
        rows = [ln for ln in table if f"`{cid}`" in ln]
        if len(rows) != 1:
            v.append(f"{cid}: expected exactly 1 row in the canonical/alias table, found {len(rows)}")
            continue
        row = rows[0]
        for alias in aliases:
            if f"`{alias}`" not in row:
                v.append(f"{cid}: row does not show alias `{alias}`")
        if f"alias_of = {cid}" not in row:
            v.append(f"{cid}: row does not show alias_of = {cid}")
        if "false" not in row:
            v.append(f"{cid}: row does not show alias-side strategy_usable = false")
        if f"[`{cid}`]" not in row:
            v.append(f"{cid}: row does not show alias-side superseded_by = [{cid}]")
    if not any("`prior_amount_20`" in ln and "单侧例外" in ln for ln in table):
        v.append("canonical/alias table lacks the prior_amount_20 single-id exception row")
    add(
        "md_canonical_columns",
        "markdown ledger table carries canonical_id / aliases[] / superseded_by[] / alias_of / "
        "strategy_usable=false for every group plus the single-id exception (md <-> json sync)",
        v,
    )

    # --- 10. freeze declaration names the version it froze ------------------
    # The declaration says which version is frozen. Nothing read it before v5.8, so a status
    # cell left at v5.6 beside "version": "5.7" passed every check silently.
    v = []
    meta = data.get("meta") or {}
    version = str(meta.get("version") or "").strip()
    freeze = meta.get("freeze_declaration") or {}
    status = str(freeze.get("status") or "").strip()
    expected_status = f"FROZEN at v{version}"
    if status != expected_status:
        v.append(
            f"freeze_declaration.status is {status!r}, expected {expected_status!r} "
            f"(meta.version is {version!r})"
        )
    status_line = next(
        (ln for ln in ledger_text.splitlines() if ln.startswith("\u72b6\u6001\uff1a")), None
    )
    if status_line is None:
        v.append("markdown ledger has no line starting with the status marker")
    else:
        m = re.search("\u53f0\u8d26 v([0-9][0-9.]*)", status_line)
        if m is None:
            v.append(
                "markdown status line carries no 'ledger v<version>' marker: "
                f"{status_line[:60]!r}"
            )
        elif m.group(1) != version:
            v.append(
                f"markdown status line says v{m.group(1)} but meta.version is v{version}"
            )
    add(
        "freeze_declaration_version_agree",
        "freeze_declaration.status == 'FROZEN at v<version>' with <version> == meta.version, "
        "and the markdown status line (the line that starts with the status marker) names the "
        "same ledger version; any disagreement -> FAIL",
        v,
    )

    # --- 11. section 0.1 registry fingerprint is the one on disk ------------
    # Section 0.1 is the published fingerprint table. A stale sha there makes the freeze
    # declaration's own verifiability clause false while every other check still passes.
    v = []
    computed_sha = lf_normalized_sha256(REGISTRY)
    md_row = next(
        (
            ln
            for ln in ledger_text.splitlines()
            if ln.startswith("|") and "f_class_registry.json" in ln
        ),
        None,
    )
    if md_row is None:
        v.append("markdown ledger has no table row for evidence/f_class_registry.json")
    else:
        shas = re.findall("[0-9a-f]{64}", md_row)
        if not shas:
            v.append(f"registry row carries no 64-hex sha256: {md_row[:120]!r}")
        elif shas[0] != computed_sha:
            v.append(
                "markdown section 0.1 registry sha256 is stale: "
                f"md {shas[0]} vs computed {computed_sha}"
            )
    add(
        "md_fingerprint_matches_registry",
        "the sha256 listed for docs/factors/evidence/f_class_registry.json in markdown "
        "section 0.1 equals the LF-normalized sha256 computed from that file now; a stale "
        "fingerprint -> FAIL",
        v,
    )

    # --- report -----------------------------------------------------------
    print("F-class ledger self-check (read-only)")
    print(f"  registry : {REGISTRY.relative_to(REPO)}")
    print(f"  ledger   : {LEDGER.relative_to(REPO)}")
    print(f"  contract : {CONTRACT.relative_to(REPO)}  (frozen v0.3 archive, read-only)")
    print(f"  contract2: {rel(CONTRACT_LIVE)}  (current revision, read source only)")
    print("  s7.1 binding: BLOCK hash, not the whole-file hash; version number not judged")
    print(f"  s7.1 archive LF/CRLF: {s71_arch['lf_chars']}/{s71_arch['crlf_chars']} chars  "
          f"sha256 {s71_arch['lf_sha256'][:8]}... / {s71_arch['crlf_sha256'][:8]}...")
    print(f"  s7.1 contract LF/CRLF: {s71_live['lf_chars']}/{s71_live['crlf_chars']} chars  "
          f"sha256 {s71_live['lf_sha256'][:8]}... / {s71_live['crlf_sha256'][:8]}...")
    print(f"  s7.1 registered: LF {S71_LF_CHARS} chars / {S71_LF_SHA256[:8]}...  "
          f"CRLF {S71_CRLF_CHARS} chars / {S71_CRLF_SHA256[:8]}...  (both must match)")
    print(f"  factors  : {len(factors)}   contract rows parsed: {len(contract)} / {len(contract_live)}")
    print()
    print("per-factor:")
    for f in factors:
        n = trailing_window(str(f.get("formula_text", "")))
        need = (n + 1) if f.get("semantics") == "prior" and n is not None else "-"
        print(
            f"  {f.get('id'):<20} window={f.get('window'):<4} shift={f.get('shift'):<2} "
            f"warmup={f.get('warmup_bars'):<4} min_warmup={need!s:<4} "
            f"formula={f.get('formula_text')}"
        )
    print()
    total = 0
    for idx, c in enumerate(checks, 1):
        total += len(c["violations"])
        print(f"[{idx}] {c['id']}")
        print(f"    rule      : {c['rule']}")
        print(f"    violations: {len(c['violations'])}")
        for detail in c["violations"]:
            print(f"      - {detail}")
    print()
    print(f"TOTAL VIOLATIONS: {total}")

    # --- recorded vs computed --------------------------------------------
    recorded = {c["id"]: c.get("violations") for c in data.get("self_check", {}).get("checks", [])}
    computed = {c["id"]: len(c["violations"]) for c in checks}
    mismatch = 0
    for cid, count in computed.items():
        if cid not in recorded:
            print(f"RECORD MISMATCH: check '{cid}' is not recorded in the JSON self_check block")
            mismatch += 1
        elif recorded[cid] != count:
            print(f"RECORD MISMATCH: '{cid}' recorded {recorded[cid]}, computed {count}")
            mismatch += 1
    for cid in recorded:
        if cid not in computed:
            print(f"RECORD MISMATCH: recorded check '{cid}' has no implementation")
            mismatch += 1
    print(f"RECORD MISMATCHES: {mismatch}")

    # --- binding ---------------------------------------------------------
    # Two kinds of line, never mixed up:
    #   registry / ledger  : whole-file LF-normalized sha256 (housekeeping fingerprint)
    #   archive / contract : section 7.1 BLOCK sha256 in both registered calibers (the judgment)
    print("BINDING")
    print("  whole files (LF-normalized sha256 = sha256 over bytes with CRLF collapsed to LF;")
    print("               immune to line-ending rewrites, LF-only by policy):")
    for label, path in (("registry", REGISTRY), ("ledger", LEDGER)):
        if path.exists():
            print(fingerprint(label, path))
        else:
            print(f"  {label:<9}: MISSING {path}")
    print("  section 7.1 block (the binding object; the contract version number is NOT binding):")
    for label, blk in (("archive", s71_arch), ("contract", s71_live)):
        print(f"  {label:<9}: {rel(blk['path'])}")
        print(f"             LF   sha256 {blk['lf_sha256']}  ({blk['lf_chars']} chars)")
        print(f"             CRLF sha256 {blk['crlf_sha256']}  ({blk['crlf_chars']} chars)")
    ok_lf = all(blk["lf_chars"] == S71_LF_CHARS and blk["lf_sha256"] == S71_LF_SHA256
                for blk in (s71_arch, s71_live))
    ok_crlf = all(blk["crlf_chars"] == S71_CRLF_CHARS and blk["crlf_sha256"] == S71_CRLF_SHA256
                  for blk in (s71_arch, s71_live))
    print(f"  caliber LF  : {S71_LF_CHARS} chars / {S71_LF_SHA256}"
          f"  == registered constant, both files: {ok_lf}")
    print(f"  caliber CRLF: {S71_CRLF_CHARS} chars / {S71_CRLF_SHA256}"
          f"  == registered constant, both files: {ok_crlf}")
    print()

    ok = total == 0 and mismatch == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
