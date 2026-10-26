#!/usr/bin/env python3
"""Resolve review-memory paths outside the distributable Skill bundle."""

from __future__ import annotations

import os
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def default_memory_root() -> Path:
    configured = os.environ.get("VIDEO_REVIEW_MEMORY_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "video-review-memory").resolve()
    return (Path.home() / ".codex" / "video-review-memory").resolve()


def memory_root(value: Path | str | None = None) -> Path:
    if value is None:
        return default_memory_root()
    return Path(value).expanduser().resolve()


def issue_ledger(root: Path | str | None = None) -> Path:
    return memory_root(root) / "issue-ledger.jsonl"


def rule_registry(root: Path | str | None = None) -> Path:
    return memory_root(root) / "rule-registry.jsonl"
