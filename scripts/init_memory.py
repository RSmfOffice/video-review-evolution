#!/usr/bin/env python3
"""Initialize portable review memory outside the Skill installation."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from memory_paths import SKILL_ROOT, default_memory_root


PROCESS_RULE_IDS = {
    "VR-001",
    "VR-002",
    "VR-005",
    "VR-006",
    "VR-007",
    "VR-008",
    "VR-010",
    "VR-011",
    "VR-012",
    "VR-013",
}


def portable_path(
    value: str,
    project_roots: list[Path],
    external_prefix: str,
) -> str:
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        for root in project_roots:
            try:
                relative = path.resolve().relative_to(root.resolve())
                return relative.as_posix()
            except (OSError, ValueError):
                continue
        return f"{external_prefix.rstrip('/')}/{path.name}"
    return normalized


def normalize_record(
    record: dict[str, Any],
    project_roots: list[Path],
    external_prefix: str,
) -> dict[str, Any]:
    if record.get("record_kind") == "rule":
        record.setdefault(
            "rule_kind",
            (
                "process-invariant"
                if record.get("rule_id") in PROCESS_RULE_IDS
                else "quality-heuristic"
            ),
        )
    media = record.get("media")
    if isinstance(media, dict) and isinstance(media.get("path"), str):
        media["path"] = portable_path(
            media["path"],
            project_roots,
            external_prefix,
        )
    evidence = record.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                item["path"] = portable_path(
                    item["path"],
                    project_roots,
                    external_prefix,
                )
    return record


def copy_records(
    source: Path,
    destination: Path,
    project_roots: list[Path],
    external_prefix: str,
) -> None:
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{source}:{line_number}: record must be an object")
        records.append(
            normalize_record(value, project_roots, external_prefix)
        )
    destination.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def initialize(
    root: Path,
    issue_source: Path | None,
    rule_source: Path | None,
    project_roots: list[Path],
    external_prefix: str,
) -> dict[str, Any]:
    issue_target = root / "issue-ledger.jsonl"
    rule_target = root / "rule-registry.jsonl"
    existing = [path for path in (issue_target, rule_target) if path.exists()]
    if existing:
        raise ValueError(
            "memory files already exist: "
            + ", ".join(str(path) for path in existing)
        )

    root.mkdir(parents=True, exist_ok=True)
    if issue_source:
        copy_records(
            issue_source,
            issue_target,
            project_roots,
            external_prefix,
        )
    else:
        shutil.copy2(
            SKILL_ROOT / "references" / "issue-ledger.template.jsonl",
            issue_target,
        )
    if rule_source:
        copy_records(
            rule_source,
            rule_target,
            project_roots,
            external_prefix,
        )
    else:
        shutil.copy2(
            SKILL_ROOT / "references" / "rule-registry.seed.jsonl",
            rule_target,
        )
    return {
        "status": "initialized",
        "memory_root": str(root),
        "issue_ledger": str(issue_target),
        "rule_registry": str(rule_target),
        "migrated_issues": bool(issue_source),
        "migrated_rules": bool(rule_source),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-root", type=Path)
    parser.add_argument("--issues-source", type=Path)
    parser.add_argument("--rules-source", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        action="append",
        default=[],
        help="Convert absolute paths below this project root to relative paths.",
    )
    parser.add_argument(
        "--external-evidence-prefix",
        default="qa/evidence/external",
    )
    args = parser.parse_args()
    root = args.memory_root or default_memory_root()
    try:
        result = initialize(
            root,
            args.issues_source,
            args.rules_source,
            args.project_root,
            args.external_evidence_prefix,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
