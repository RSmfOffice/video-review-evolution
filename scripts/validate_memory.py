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

from memory_paths import issue_ledger, rule_registry


DEFAULT_ISSUES = issue_ledger()
DEFAULT_RULES = rule_registry()

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
RULE_KINDS = {"process-invariant", "quality-heuristic"}
REGRESSION_ROLES = {
    "original-failure",
    "same-mechanism-positive",
    "cross-route-positive",
    "high-complexity-positive",
    "known-clean-control",
    "negative-example",
    "holdout",
}
REPORTERS = {
    "user",
    "user-correction",
    "agent",
    "agent-initial-review",
    "independent-reviewer",
}


def load_jsonl(path: Path, allow_empty: bool = False) -> list[dict[str, Any]]:
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
    if not records and not allow_empty:
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


def is_absolute_locator(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized) is not None
        or normalized.startswith("file:")
    )


def validate_evidence(
    value: Any,
    line: int,
    errors: list[str],
    require_hash: bool,
) -> None:
    if not isinstance(value, list):
        errors.append(f"line {line}: evidence must be a list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"line {line}: evidence[{index}] must be an object")
            continue
        if not item.get("path"):
            errors.append(f"line {line}: evidence[{index}] missing path")
        elif is_absolute_locator(str(item["path"])):
            errors.append(
                f"line {line}: evidence[{index}].path must be project-relative"
            )
        if not item.get("type"):
            errors.append(f"line {line}: evidence[{index}] missing type")
        sha = item.get("sha256")
        if require_hash and not sha:
            errors.append(f"line {line}: evidence[{index}] missing sha256")
        elif sha is not None and not SHA256.match(str(sha)):
            errors.append(f"line {line}: evidence[{index}] has invalid sha256")


def semver_tuple(value: Any) -> tuple[int, int, int] | None:
    if not SEMVER.match(str(value or "")):
        return None
    return tuple(int(part) for part in str(value).split("."))


def validate_issues(records: list[dict[str, Any]], errors: list[str]) -> None:
    old_ids = {str(r.get("record_id")) for r in records if r.get("record_id")}
    known_records = {
        str(r.get("record_id")): r for r in records if r.get("record_id")
    }
    seen_versions: set[tuple[str, int]] = set()
    revisions_by_issue: dict[str, set[int]] = {}
    seen_record_ids: set[str] = set()

    for record in records:
        if record.get("record_kind") != "issue":
            errors.append(f"line {record['_line']}: expected record_kind=issue")
            continue
        validate_common(record, errors)
        line = int(record["_line"])
        record_id = str(record.get("record_id") or "")
        if record_id in seen_record_ids:
            errors.append(f"line {line}: duplicate record_id {record_id}")
        seen_record_ids.add(record_id)
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
            if is_absolute_locator(str(media["path"])):
                errors.append(f"line {line}: media.path must be project-relative")
            sha = media.get("sha256")
            if not sha or not SHA256.match(str(sha)):
                errors.append(f"line {line}: media.sha256 must be 64 hex characters")

        evidence = record.get("evidence")
        review_version = semver_tuple(record.get("reviewer_skill_version"))
        require_hash = review_version is None or review_version >= (0, 3, 0)
        validate_evidence(evidence, line, errors, require_hash)
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
            revisions_by_issue.setdefault(issue_id, set()).add(revision)

        supersedes = record.get("supersedes")
        if supersedes is not None and supersedes not in old_ids:
            errors.append(f"line {line}: supersedes unknown record {supersedes!r}")
        elif supersedes is not None:
            previous = known_records[str(supersedes)]
            if previous.get("issue_id") != issue_id:
                errors.append(f"line {line}: supersedes must reference the same issue")
            if isinstance(revision, int) and previous.get("revision") != revision - 1:
                errors.append(
                    f"line {line}: supersedes must reference the previous revision"
                )

    for issue_id, revisions in revisions_by_issue.items():
        expected = set(range(1, max(revisions) + 1))
        if revisions != expected:
            errors.append(
                f"{issue_id}: revisions must be contiguous from 1; "
                f"found {sorted(revisions)}"
            )


def validate_rules(records: list[dict[str, Any]], errors: list[str]) -> set[str]:
    rule_ids: set[str] = set()
    old_ids = {str(r.get("record_id")) for r in records if r.get("record_id")}
    seen_versions: set[tuple[str, int]] = set()
    revisions_by_rule: dict[str, set[int]] = {}
    seen_record_ids: set[str] = set()

    for record in records:
        if record.get("record_kind") != "rule":
            errors.append(f"line {record['_line']}: expected record_kind=rule")
            continue
        validate_common(record, errors)
        line = int(record["_line"])
        record_id = str(record.get("record_id") or "")
        if record_id in seen_record_ids:
            errors.append(f"line {line}: duplicate record_id {record_id}")
        seen_record_ids.add(record_id)
        for key in [
            "rule_id",
            "version",
            "rule_kind",
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
        if record.get("rule_kind") not in RULE_KINDS:
            errors.append(f"line {line}: invalid rule_kind {record.get('rule_kind')!r}")

        rule_id = record.get("rule_id")
        revision = record.get("revision")
        if isinstance(rule_id, str):
            rule_ids.add(rule_id)
        if isinstance(rule_id, str) and isinstance(revision, int):
            key = (rule_id, revision)
            if key in seen_versions:
                errors.append(f"line {line}: duplicate rule revision {rule_id} r{revision}")
            seen_versions.add(key)
            revisions_by_rule.setdefault(rule_id, set()).add(revision)

        evidence_ids = record.get("evidence_case_ids")
        if not isinstance(evidence_ids, list):
            errors.append(f"line {line}: evidence_case_ids must be a list")
        regression = record.get("regression_cases")
        if not isinstance(regression, list):
            errors.append(f"line {line}: regression_cases must be a list")
        else:
            for index, case in enumerate(regression):
                if not isinstance(case, dict):
                    errors.append(
                        f"line {line}: regression_cases[{index}] must be an object"
                    )
                    continue
                for key in ("case_id", "role", "result"):
                    require(case, key, errors)
                if case.get("role") not in REGRESSION_ROLES:
                    errors.append(
                        f"line {line}: regression_cases[{index}].role is invalid"
                    )
                if case.get("result") not in {
                    "pass",
                    "fail",
                    "not_run",
                    "not_available",
                }:
                    errors.append(
                        f"line {line}: regression_cases[{index}].result is invalid"
                    )

        if (
            record.get("status") in {"active", "validated"}
            and record.get("rule_kind") == "quality-heuristic"
            and record.get("scope") != "project-specific"
        ):
            if not isinstance(evidence_ids, list) or not evidence_ids:
                errors.append(
                    f"line {line}: non-project quality rule needs evidence cases"
                )
            if not isinstance(regression, list) or not regression:
                errors.append(
                    f"line {line}: non-project quality rule needs regression cases"
                )
            if record.get("scope") in {"route-specific", "model-specific"}:
                roles = {
                    case.get("role")
                    for case in regression or []
                    if isinstance(case, dict)
                }
                if "known-clean-control" not in roles:
                    errors.append(
                        f"line {line}: route/model quality rule needs a clean control"
                    )
            if record.get("scope") in {"conditional-core", "unconditional-core"} and (
                not isinstance(evidence_ids, list)
                or len(set(evidence_ids)) < 2
            ):
                errors.append(
                    f"line {line}: validated cross-route rule needs >=2 evidence cases"
                )
            if record.get("scope") == "unconditional-core" and isinstance(
                regression, list
            ):
                roles = {
                    case.get("role")
                    for case in regression
                    if isinstance(case, dict)
                }
                required_roles = {
                    "original-failure",
                    "same-mechanism-positive",
                    "cross-route-positive",
                    "known-clean-control",
                    "negative-example",
                    "holdout",
                }
                if not required_roles.issubset(roles):
                    errors.append(
                        f"line {line}: unconditional core is missing regression roles: "
                        + ", ".join(sorted(required_roles - roles))
                    )

        supersedes = record.get("supersedes")
        if supersedes is not None and supersedes not in old_ids:
            errors.append(f"line {line}: supersedes unknown record {supersedes!r}")

    for rule_id, revisions in revisions_by_rule.items():
        expected = set(range(1, max(revisions) + 1))
        if revisions != expected:
            errors.append(
                f"{rule_id}: revisions must be contiguous from 1; "
                f"found {sorted(revisions)}"
            )
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
    parser.add_argument("--memory-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.memory_root:
        args.issues = issue_ledger(args.memory_root)
        args.rules = rule_registry(args.memory_root)

    errors: list[str] = []
    try:
        issues = load_jsonl(args.issues, allow_empty=True)
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
