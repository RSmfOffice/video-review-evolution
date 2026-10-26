#!/usr/bin/env python3
"""Validate the persistent review ledger and rule registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ISSUES = SKILL_ROOT / "references" / "issue-ledger.jsonl"
DEFAULT_RULES = SKILL_ROOT / "references" / "rule-registry.jsonl"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")

VERDICTS = {
    "confirmed",
    "not_reproduced",
    "conditionally_confirmed",
    "insufficient_evidence",
}
SEVERITIES = {"blocker", "major", "minor", "note"}
CONFIDENCES = {"high", "medium", "low"}
SCOPES = {
    "project-specific",
    "route-specific",
    "model-specific",
    "conditional-core",
    "unconditional-core",
}
ISSUE_STATUSES = {
    "open",
    "confirmed",
    "fixed",
    "verified",
    "rejected",
    "superseded",
}
RULE_STATUSES = {"active", "candidate", "validated", "rejected", "merged"}
REPORTERS = {
    "user",
    "user-correction",
    "agent",
    "agent-initial-review",
    "independent-reviewer",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing file: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: record must be an object")
        value["_line"] = line_number
        records.append(value)
    if not records:
        raise ValueError(f"{path}: no records")
    return records


def require(record: dict[str, Any], key: str, errors: list[str]) -> Any:
    if key not in record or record[key] in (None, ""):
        errors.append(f"line {record['_line']}: missing {key}")
        return None
    return record[key]


def validate_common(record: dict[str, Any], errors: list[str]) -> None:
    required = [
        "record_kind",
        "record_id",
        "revision",
        "recorded_at",
        "status",
        "scope",
    ]
    for key in required:
        require(record, key, errors)

    recorded_at = record.get("recorded_at")
    if recorded_at and not DATE.match(str(recorded_at)):
        errors.append(f"line {record['_line']}: recorded_at must be YYYY-MM-DD")

    version = record.get("version")
    if version and not SEMVER.match(str(version)):
        errors.append(f"line {record['_line']}: version must be semantic")

    if record.get("scope") not in SCOPES:
        errors.append(f"line {record['_line']}: invalid scope {record.get('scope')!r}")

    revision = record.get("revision")
    if not isinstance(revision, int) or revision < 1:
        errors.append(f"line {record['_line']}: revision must be a positive integer")


def validate_evidence(value: Any, line: int, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"line {line}: evidence must be a list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"line {line}: evidence[{index}] must be an object")
            continue
        if not item.get("path"):
            errors.append(f"line {line}: evidence[{index}] missing path")
        if not item.get("type"):
            errors.append(f"line {line}: evidence[{index}] missing type")
        sha = item.get("sha256")
        if sha is not None and not SHA256.match(str(sha)):
            errors.append(f"line {line}: evidence[{index}] has invalid sha256")


def validate_issues(records: list[dict[str, Any]], errors: list[str]) -> None:
    old_ids = {str(r.get("record_id")) for r in records if r.get("record_id")}
    seen_versions: set[tuple[str, int]] = set()
    latest_by_issue: dict[str, int] = {}

    for record in records:
        if record.get("record_kind") != "issue":
            errors.append(f"line {record['_line']}: expected record_kind=issue")
            continue
        validate_common(record, errors)
        line = int(record["_line"])
        for key in [
            "review_id",
            "issue_id",
            "reviewer_skill_version",
            "domain_skill",
            "project_id",
            "timecode",
            "reported_by",
            "reported",
            "observed",
            "expected_source",
            "verdict",
            "severity",
            "confidence",
            "impact",
            "relationship_primitive",
            "rule_ids",
        ]:
            require(record, key, errors)

        if record.get("status") not in ISSUE_STATUSES:
            errors.append(f"line {line}: invalid issue status {record.get('status')!r}")
        if record.get("verdict") not in VERDICTS:
            errors.append(f"line {line}: invalid verdict {record.get('verdict')!r}")
        if record.get("severity") not in SEVERITIES:
            errors.append(f"line {line}: invalid severity {record.get('severity')!r}")
        if record.get("confidence") not in CONFIDENCES:
            errors.append(f"line {line}: invalid confidence {record.get('confidence')!r}")
        if record.get("reported_by") not in REPORTERS:
            errors.append(f"line {line}: invalid reported_by {record.get('reported_by')!r}")
        reviewer_version = record.get("reviewer_skill_version")
        if reviewer_version and not SEMVER.match(str(reviewer_version)):
            errors.append(f"line {line}: reviewer_skill_version must be semantic")

        media = record.get("media")
        if not isinstance(media, dict) or not media.get("path"):
            errors.append(f"line {line}: missing media.path")
        else:
            sha = media.get("sha256")
            if not sha or not SHA256.match(str(sha)):
                errors.append(f"line {line}: media.sha256 must be 64 hex characters")

        evidence = record.get("evidence")
        validate_evidence(evidence, line, errors)
        if record.get("verdict") in {"confirmed", "conditionally_confirmed"}:
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"line {line}: confirmed issue requires evidence")

        rule_ids = record.get("rule_ids")
        if not isinstance(rule_ids, list):
            errors.append(f"line {line}: rule_ids must be a list")

        issue_id = record.get("issue_id")
        revision = record.get("revision")
        if isinstance(issue_id, str) and isinstance(revision, int):
            key = (issue_id, revision)
            if key in seen_versions:
                errors.append(f"line {line}: duplicate issue revision {issue_id} r{revision}")
            seen_versions.add(key)
            latest_by_issue[issue_id] = max(latest_by_issue.get(issue_id, 0), revision)

        supersedes = record.get("supersedes")
        if supersedes is not None and supersedes not in old_ids:
            errors.append(f"line {line}: supersedes unknown record {supersedes!r}")

    for issue_id, revision in latest_by_issue.items():
        if not any(
            r.get("issue_id") == issue_id and r.get("revision") == revision for r in records
        ):
            errors.append(f"missing latest revision for {issue_id}")


def validate_rules(records: list[dict[str, Any]], errors: list[str]) -> set[str]:
    rule_ids: set[str] = set()
    old_ids = {str(r.get("record_id")) for r in records if r.get("record_id")}
    seen_versions: set[tuple[str, int]] = set()

    for record in records:
        if record.get("record_kind") != "rule":
            errors.append(f"line {record['_line']}: expected record_kind=rule")
            continue
        validate_common(record, errors)
        line = int(record["_line"])
        for key in [
            "rule_id",
            "version",
            "statement",
            "trigger",
            "pass_if",
            "fail_if",
            "exemptions",
            "evidence_case_ids",
            "regression_cases",
        ]:
            require(record, key, errors)

        if record.get("status") not in RULE_STATUSES:
            errors.append(f"line {line}: invalid rule status {record.get('status')!r}")

        rule_id = record.get("rule_id")
        revision = record.get("revision")
        if isinstance(rule_id, str):
            rule_ids.add(rule_id)
        if isinstance(rule_id, str) and isinstance(revision, int):
            key = (rule_id, revision)
            if key in seen_versions:
                errors.append(f"line {line}: duplicate rule revision {rule_id} r{revision}")
            seen_versions.add(key)

        evidence_ids = record.get("evidence_case_ids")
        if not isinstance(evidence_ids, list):
            errors.append(f"line {line}: evidence_case_ids must be a list")
        regression = record.get("regression_cases")
        if not isinstance(regression, list):
            errors.append(f"line {line}: regression_cases must be a list")

        if record.get("scope") == "unconditional-core" and record.get("status") in {
            "active",
            "validated",
        }:
            if not isinstance(evidence_ids, list) or len(set(evidence_ids)) < 2:
                errors.append(f"line {line}: unconditional core needs >=2 evidence cases")
            if not isinstance(regression, list) or not regression:
                errors.append(f"line {line}: unconditional core needs regression cases")

        supersedes = record.get("supersedes")
        if supersedes is not None and supersedes not in old_ids:
            errors.append(f"line {line}: supersedes unknown record {supersedes!r}")

    return rule_ids


def cross_link(
    issues: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    rule_ids: set[str],
    errors: list[str],
) -> None:
    issue_ids = {str(r.get("issue_id")) for r in issues}
    for record in issues:
        for rule_id in record.get("rule_ids", []):
            if rule_id not in rule_ids:
                errors.append(f"line {record['_line']}: unknown rule_id {rule_id!r}")
    for record in rules:
        for issue_id in record.get("evidence_case_ids", []):
            if issue_id not in issue_ids:
                errors.append(f"line {record['_line']}: unknown issue_id {issue_id!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    try:
        issues = load_jsonl(args.issues)
        rules = load_jsonl(args.rules)
        validate_issues(issues, errors)
        rule_ids = validate_rules(rules, errors)
        cross_link(issues, rules, rule_ids, errors)
    except ValueError as exc:
        errors.append(str(exc))
        issues = []
        rules = []

    result = {
        "ok": not errors,
        "issues": len(issues),
        "rules": len(rules),
        "issue_statuses": dict(Counter(r.get("status") for r in issues)),
        "rule_statuses": dict(Counter(r.get("status") for r in rules)),
        "errors": errors,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
    else:
        print(
            f"PASS: {result['issues']} issue records, "
            f"{result['rules']} rule records"
        )

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
