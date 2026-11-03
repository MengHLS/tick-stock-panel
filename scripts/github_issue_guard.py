"""Create GitHub issues only for ``MengHLS/tick-stock-panel``.

The target repository is intentionally not configurable. The script validates
the local ``origin`` remote, verifies the GitHub repository before writing, and
checks the returned issue URL after writing. Any mismatch fails closed.

Usage:
    python scripts/github_issue_guard.py \
        --title "Issue title" \
        --body-file .artifacts/issue.md

    python scripts/github_issue_guard.py \
        --title "Issue title" \
        --body-file .artifacts/issue.md \
        --dry-run

Token resolution order: ``GITHUB_ISSUE_TOKEN``, ``GH_TOKEN``,
``GITHUB_TOKEN``, then the existing Git credential helper for github.com.
The token is never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET_OWNER = "MengHLS"
TARGET_REPO = "MengHLS/tick-stock-panel"
TARGET_HTML = f"https://github.com/{TARGET_REPO}"
TARGET_API = f"https://api.github.com/repos/{TARGET_REPO}"
BLOCKED_REPOS = frozenset({"shy3130/tick-stock-panel"})
API_BASE = "https://api.github.com"
MAX_TITLE_LENGTH = 256


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def _normalize_remote(url: str) -> str:
    value = url.strip().removesuffix("/").removesuffix(".git")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    if value.startswith("ssh://git@github.com/"):
        value = "https://github.com/" + value.removeprefix("ssh://git@github.com/")
    return value.rstrip("/")


def verify_origin() -> None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        _fail("无法读取 origin remote；拒绝创建 Issue")
    actual = _normalize_remote(result.stdout)
    expected = f"https://github.com/{TARGET_REPO}"
    if actual != expected:
        _fail(f"origin 不是允许的目标仓库: 期望 {expected}，实际 {actual}")


def _load_token() -> str:
    for name in ("GITHUB_ISSUE_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    credential = "protocol=https\nhost=github.com\n\n"
    result = subprocess.run(
        ["git", "credential", "fill"],
        input=credential,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        _fail("没有可用的 GitHub Token，且 Git credential helper 不可用")
    for line in result.stdout.splitlines():
        if line.startswith("password="):
            token = line.removeprefix("password=").strip()
            if token:
                return token
    _fail("Git credential helper 未返回 password；拒绝创建 Issue")
    raise AssertionError("unreachable")


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tick-stock-panel-issue-guard",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        _fail(f"GitHub API {method} {path} 失败: HTTP {exc.code} {detail}")
    except OSError as exc:
        _fail(f"GitHub API {method} {path} 网络失败: {exc}")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        _fail(f"GitHub API {method} {path} 返回非 JSON")
    if not isinstance(result, dict):
        _fail(f"GitHub API {method} {path} 返回结构不是对象")
    return result


def verify_repository() -> dict[str, Any]:
    if TARGET_REPO in BLOCKED_REPOS:
        _fail("目标仓库被 blocklist 禁止")
    repo = _request("GET", f"/repos/{TARGET_REPO}")
    full_name = str(repo.get("full_name") or "")
    owner = str((repo.get("owner") or {}).get("login") or "")
    if full_name != TARGET_REPO or owner != TARGET_OWNER:
        _fail(f"写前仓库校验失败: full_name={full_name!r}, owner={owner!r}")
    if not repo.get("has_issues"):
        _fail("目标仓库未开启 Issues")
    return repo


def verify_created_issue(issue: dict[str, Any]) -> None:
    repository_url = str(issue.get("repository_url") or "").rstrip("/")
    html_url = str(issue.get("html_url") or "").rstrip("/")
    number = issue.get("number")
    if repository_url != TARGET_API:
        _fail(f"写后仓库校验失败: repository_url={repository_url!r}")
    if not html_url.startswith(f"{TARGET_HTML}/issues/"):
        _fail(f"写后 Issue URL 校验失败: html_url={html_url!r}")
    if not isinstance(number, int) or number < 1:
        _fail(f"写后 Issue 编号校验失败: number={number!r}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Issue 标题")
    parser.add_argument("--body-file", required=True, type=Path, help="Markdown 正文文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不创建 Issue")
    args = parser.parse_args()

    title = args.title.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        _fail(f"Issue 标题必须为 1..{MAX_TITLE_LENGTH} 个字符")
    body_path = args.body_file.resolve()
    if not body_path.is_file():
        _fail(f"正文文件不存在: {body_path}")
    body = body_path.read_text(encoding="utf-8").strip()
    if not body:
        _fail("Issue 正文不能为空")

    verify_origin()
    verify_repository()
    if args.dry_run:
        print(f"DRY RUN OK: target={TARGET_REPO}, title={title!r}, body_chars={len(body)}")
        return 0

    issue = _request(
        "POST",
        f"/repos/{TARGET_REPO}/issues",
        token=_load_token(),
        payload={"title": title, "body": body},
    )
    verify_created_issue(issue)
    print(f"created issue #{issue['number']}: {issue['html_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
