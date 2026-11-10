"""Acceptance ① (part 2): byte-level diff proof that the change set is ONE line.

pre  = the pre-patch snapshot (3449 B / 61c237c6…) — the read-only baseline copy
post = the live production file
Asserts:
  * unified diff has exactly 1 removed + 1 added line
  * every other line is byte-identical (line count unchanged)
  * reverting the single line reproduces the pre-patch bytes exactly (roundtrip)
  * no BOM, same CRLF line ending count
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = Path(os.environ.get("PRE_FILE", HERE / "strategies_prepatch" / "custom" / "custom_mw7fvp17.py"))
POST = Path(os.environ.get("POST_FILE", r"D:\TSP\data\strategies\custom\custom_mw7fvp17.py"))
RES = HERE / "results"

OLD = b"        cross_down = fast < slow"
NEW = b"        cross_down = (fast < slow) & (prev_fast >= prev_slow)"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    a, b = PRE.read_bytes(), POST.read_bytes()
    la, lb = a.splitlines(keepends=True), b.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        [x.decode("utf-8") for x in la], [x.decode("utf-8") for x in lb],
        fromfile=PRE.name + ".before", tofile=POST.name + ".after", n=2))
    removed = [ln for ln in diff if ln.startswith("-") and not ln.startswith("---")]
    added = [ln for ln in diff if ln.startswith("+") and not ln.startswith("+++")]

    same_len = len(la) == len(lb)
    changed = [i + 1 for i, (x, y) in enumerate(zip(la, lb)) if x != y]
    roundtrip = a == b.replace(NEW, OLD) if NEW in b else False

    rep = {
        "pre": {"path": str(PRE), "size": len(a), "sha256": sha(a)},
        "post": {"path": str(POST), "size": len(b), "sha256": sha(b),
                 "mtime": __import__("datetime").datetime.fromtimestamp(POST.stat().st_mtime).isoformat()},
        "byte_delta": len(b) - len(a),
        "lines": [len(la), len(lb)],
        "line_count_unchanged": same_len,
        "changed_line_numbers": changed,
        "removed_lines": [ln.rstrip("\r\n") for ln in removed],
        "added_lines": [ln.rstrip("\r\n") for ln in added],
        "changed_line_pairs": [len(removed), len(added)],
        "roundtrip_restores_pre_bytes": roundtrip,
        "bom_pre": a[:3] == b"\xef\xbb\xbf", "bom_post": b[:3] == b"\xef\xbb\xbf",
        "crlf_pre": a.count(b"\r\n"), "crlf_post": b.count(b"\r\n"),
    }
    ok = (same_len and len(removed) == 1 and len(added) == 1 and changed == [changed[0]] if changed else False)
    ok = ok and roundtrip and rep["crlf_pre"] == rep["crlf_post"]
    rep["VERDICT"] = "ONE_LINE_ONLY" if ok else "UNEXPECTED_DIFF"

    (RES / "byte_diff.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (RES / "byte_diff.txt").write_text(
        "".join(ln if ln.endswith("\n") else ln + "\n" for ln in diff)
        + f"\n--- changed_line_numbers={changed} byte_delta={len(b) - len(a)} "
          f"roundtrip={roundtrip} VERDICT={rep['VERDICT']}\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in (
        "byte_delta", "lines", "changed_line_numbers", "changed_line_pairs",
        "roundtrip_restores_pre_bytes", "crlf_pre", "crlf_post", "VERDICT")}, ensure_ascii=False))
    print("".join(diff))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
