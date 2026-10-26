#!/usr/bin/env python3
"""Validate generation/review handoff, findings, changes, and verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
COVERAGE = {
    "technical",
    "content",
    "text",
    "visual",
    "motion",
    "editorial",
    "audio_visual",
    "rights",
    "accessibility",
}
COVERAGE_STATUSES = {"pass", "warn", "fail", "not_checked", "skipped"}
VERDICTS = {
    "pass",
    "revise",
    "reject",
    "provisional",
    "insufficient_evidence",
}
ISSUE_VERDICTS = {
    "confirmed",
    "conditionally_confirmed",
    "not_reproduced",
    "insufficient_evidence",
}
SEVERITIES = {"blocker", "major", "minor", "note"}
CONFIDENCES = {"high", "medium", "low"}
INTENT_JUDGMENTS = {
    "intentional-supported",
    "intentional-ambiguous",
    "accidental-harmful",
    "insufficient-evidence",
}
REVIEWER_KINDS = {"self", "cold-agent", "human", "external"}
SCOPES = {
    "project-specific",
    "route-specific",
    "model-specific",
    "conditional-core",
    "unconditional-core",
}
TARGET_LAYERS = {
    "quality-contract",
    "direction-reference",
    "script-clock",
    "shot-design",
    "asset-keyframe",
    "route-model",
    "prompt",
    "compositing-timeline",
    "qa-evidence",
    "skill-rule",
}
REGRESSION_ROLES = {
    "original-failure",
    "same-mechanism-positive",
    "cross-route-positive",
    "high-complexity-positive",
    "known-clean-control",
    "negative-example",
    "holdout",
}
REGRESSION_RESULTS = {
    "pass",
    "fail",
    "not_run",
    "not_available",
}
VERIFICATION_RESULTS = {
    "validated",
    "rejected",
    "provisional",
    "insufficient_evidence",
    "not_applicable",
}
REVIEW_PHASES = {"initial", "calibrated"}
SOURCE_ROLES = {"brief", "project", "shots", "timeline", "qa_report"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json_without_keys(path: Path, excluded: set[str]) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON hash scope requires a top-level object")
    filtered = {
        key: item for key, item in value.items() if key not in excluded
    }
    canonical = json.dumps(
        filtered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def require(
    value: dict[str, Any],
    key: str,
    prefix: str,
    errors: list[str],
) -> Any:
    if key not in value or value[key] in (None, ""):
        errors.append(f"{prefix}: missing {key}")
        return None
    return value[key]


def semver_tuple(value: Any) -> tuple[int, int, int] | None:
    if not SEMVER.match(str(value or "")):
        return None
    return tuple(int(part) for part in str(value).split("."))


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def project_root_for(handoff_path: Path) -> Path:
    return handoff_path.resolve().parent.parent


def resolve_project_path(
    root: Path,
    value: Any,
    prefix: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{prefix} must be a non-empty project-relative path")
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        errors.append(f"{prefix} must be project-relative")
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{prefix} escapes the project root")
        return None
    return resolved


def validate_hashed_file(
    root: Path,
    path_value: Any,
    declared_hash: Any,
    prefix: str,
    errors: list[str],
    allow_missing: bool,
    hash_mode: str = "raw",
) -> Path | None:
    path = resolve_project_path(root, path_value, f"{prefix}.path", errors)
    if path is None:
        return None
    if not SHA256.match(str(declared_hash or "")):
        errors.append(f"{prefix}.sha256 must be 64 hex characters")
        return path
    if not path.is_file():
        if not allow_missing:
            errors.append(f"{prefix} file not found: {path}")
        return path
    if hash_mode == "raw":
        actual = sha256(path)
    elif hash_mode == "json-without-gates":
        try:
            actual = sha256_json_without_keys(path, {"gates"})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{prefix}: {exc}")
            return path
    else:
        errors.append(f"{prefix}.hash_mode is invalid")
        return path
    if actual.lower() != str(declared_hash).lower():
        errors.append(
            f"{prefix}.sha256 mismatch (declared {declared_hash}, actual {actual})"
        )
    return path


def validate_evidence(
    root: Path,
    evidence: Any,
    prefix: str,
    errors: list[str],
    allow_missing: bool,
    required: bool,
) -> None:
    if not isinstance(evidence, list):
        errors.append(f"{prefix} must be a list")
        return
    if required and not evidence:
        errors.append(f"{prefix} must contain at least one evidence object")
    for index, item in enumerate(evidence):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object")
            continue
        require(item, "path", item_prefix, errors)
        require(item, "type", item_prefix, errors)
        validate_hashed_file(
            root,
            item.get("path"),
            item.get("sha256"),
            item_prefix,
            errors,
            allow_missing,
        )


def validate_reviewer(
    reviewer: Any,
    prefix: str,
    errors: list[str],
    independent_required: bool,
) -> None:
    if not isinstance(reviewer, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ("id", "kind", "reviewed_at"):
        require(reviewer, key, prefix, errors)
    if reviewer.get("kind") not in REVIEWER_KINDS:
        errors.append(f"{prefix}.kind is invalid")
    if not valid_timestamp(reviewer.get("reviewed_at")):
        errors.append(f"{prefix}.reviewed_at must be an ISO timestamp")
    if not isinstance(reviewer.get("independent_from_producer"), bool):
        errors.append(f"{prefix}.independent_from_producer must be a boolean")
    elif independent_required and reviewer.get("independent_from_producer") is not True:
        errors.append(f"{prefix} must be independent from the producer")


def validate_control(
    control: Any,
    root: Path,
    prefix: str,
    errors: list[str],
    allow_missing: bool,
) -> None:
    if not isinstance(control, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ("id", "role", "expected", "media"):
        require(control, key, prefix, errors)
    media = control.get("media")
    if isinstance(media, dict):
        validate_hashed_file(
            root,
            media.get("path"),
            media.get("sha256"),
            f"{prefix}.media",
            errors,
            allow_missing,
        )
    else:
        errors.append(f"{prefix}.media must be an object")


def validate_handoff(
    handoff: dict[str, Any],
    path: Path,
    allow_missing_media: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    root = project_root_for(path)
    if handoff.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"handoff: schema_version must be {SCHEMA_VERSION}")

    project_id = require(handoff, "project_id", "handoff", errors)
    if not valid_timestamp(handoff.get("created_at")):
        errors.append("handoff: created_at must be an ISO timestamp")

    generation = handoff.get("generation_skill")
    if not isinstance(generation, dict):
        errors.append("handoff: generation_skill must be an object")
        generation = {}
    if generation.get("name") != "video-production-director":
        errors.append(
            "handoff: generation_skill.name must be video-production-director"
        )
    generation_version = semver_tuple(generation.get("version"))
    if generation_version is None:
        errors.append("handoff: generation_skill.version must be semantic")
    generation_hash = generation.get("sha256")
    if generation_hash and not SHA256.match(str(generation_hash)):
        errors.append("handoff: generation_skill.sha256 is invalid")

    min_review = semver_tuple(handoff.get("review_skill_min_version"))
    if min_review is None:
        errors.append("handoff: review_skill_min_version must be semantic")

    scope = handoff.get("review_scope")
    if not isinstance(scope, list) or not scope:
        errors.append("handoff: review_scope must be a non-empty list")
        scope = []
    elif len(set(scope)) != len(scope):
        errors.append("handoff: review_scope contains duplicates")
    unknown_scope = sorted(set(scope) - COVERAGE)
    if unknown_scope:
        errors.append(
            "handoff: review_scope contains unknown categories: "
            + ", ".join(unknown_scope)
        )

    media = handoff.get("media")
    media_sha = ""
    duration = None
    if not isinstance(media, dict):
        errors.append("handoff: media must be an object")
    else:
        media_sha = str(media.get("sha256") or "")
        validate_hashed_file(
            root,
            media.get("path"),
            media_sha,
            "handoff.media",
            errors,
            allow_missing_media,
        )
        for key in ("duration_sec", "width", "height", "fps"):
            value = media.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                errors.append(f"handoff.media.{key} must be positive")
        if not isinstance(media.get("has_audio"), bool):
            errors.append("handoff.media.has_audio must be a boolean")
        if isinstance(media.get("duration_sec"), (int, float)):
            duration = float(media["duration_sec"])

    delivery = handoff.get("delivery")
    if not isinstance(delivery, dict):
        errors.append("handoff: delivery must be an object")
    else:
        for key in ("platform", "quality_mode"):
            require(delivery, key, "handoff.delivery", errors)
        if delivery.get("quality_mode") not in {"draft", "standard", "hero"}:
            errors.append("handoff.delivery.quality_mode is invalid")
        intended_size = delivery.get("intended_size")
        if (
            not isinstance(intended_size, list)
            or len(intended_size) != 2
            or any(
                not isinstance(value, (int, float)) or value <= 0
                for value in intended_size
            )
        ):
            errors.append(
                "handoff.delivery.intended_size must be [positive width, positive height]"
            )

    sources = handoff.get("sources")
    source_hashes: dict[str, str] = {}
    if not isinstance(sources, dict):
        errors.append("handoff: sources must be an object")
    else:
        missing_sources = SOURCE_ROLES - set(sources)
        if missing_sources:
            errors.append(
                "handoff: missing source roles: "
                + ", ".join(sorted(missing_sources))
            )
        for role in sorted(set(sources) & SOURCE_ROLES):
            source = sources.get(role)
            prefix = f"handoff.sources.{role}"
            if not isinstance(source, dict):
                errors.append(f"{prefix} must be an object")
                continue
            source_hashes[role] = str(source.get("sha256") or "")
            validate_hashed_file(
                root,
                source.get("path"),
                source.get("sha256"),
                prefix,
                errors,
                False,
                hash_mode=str(source.get("hash_mode", "raw")),
            )

    observations = handoff.get("required_observations")
    if not isinstance(observations, list) or not observations:
        errors.append("handoff: required_observations must be a non-empty list")
        observations = []
    observation_ids: set[str] = set()
    for index, observation in enumerate(observations):
        prefix = f"handoff.required_observations[{index}]"
        if not isinstance(observation, dict):
            errors.append(f"{prefix} must be an object")
            continue
        observation_id = require(observation, "id", prefix, errors)
        require(observation, "observable", prefix, errors)
        acceptance_ids = observation.get("acceptance_ids")
        if not isinstance(acceptance_ids, list) or not acceptance_ids:
            errors.append(f"{prefix}.acceptance_ids must be a non-empty list")
        if observation_id in observation_ids:
            errors.append(f"{prefix}.id is duplicated")
        if observation_id:
            observation_ids.add(str(observation_id))

    choices = handoff.get("intentional_choices")
    if not isinstance(choices, list):
        errors.append("handoff: intentional_choices must be a list")
        choices = []
    choice_ids: set[str] = set()
    for index, choice in enumerate(choices):
        prefix = f"handoff.intentional_choices[{index}]"
        if not isinstance(choice, dict):
            errors.append(f"{prefix} must be an object")
            continue
        choice_id = require(choice, "id", prefix, errors)
        for key in ("relationship", "declared", "evidence"):
            require(choice, key, prefix, errors)
        for key in ("allowed_effects", "must_preserve"):
            value = choice.get(key)
            if not isinstance(value, list) or not value:
                errors.append(f"{prefix}.{key} must be a non-empty list")
        if choice_id in choice_ids:
            errors.append(f"{prefix}.id is duplicated")
        if choice_id:
            choice_ids.add(str(choice_id))

    anchors = handoff.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        errors.append("handoff: anchors must be a non-empty list")
        anchors = []
    anchor_ids: set[str] = set()
    for index, anchor in enumerate(anchors):
        prefix = f"handoff.anchors[{index}]"
        if not isinstance(anchor, dict):
            errors.append(f"{prefix} must be an object")
            continue
        anchor_id = require(anchor, "id", prefix, errors)
        require(anchor, "kind", prefix, errors)
        start = anchor.get("start_sec")
        end = anchor.get("end_sec")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
            or start < 0
            or end < start
        ):
            errors.append(f"{prefix} has invalid start_sec/end_sec")
        elif duration is not None and end > duration + 0.001:
            errors.append(f"{prefix} extends beyond media duration")
        if anchor_id in anchor_ids:
            errors.append(f"{prefix}.id is duplicated")
        if anchor_id:
            anchor_ids.add(str(anchor_id))

    context = handoff.get("control_context")
    if not isinstance(context, dict) or not context:
        errors.append("handoff: control_context must be a non-empty object")
    else:
        for key in ("route", "model", "prompt_or_source"):
            require(context, key, "handoff.control_context", errors)
        if not isinstance(context.get("references"), list):
            errors.append("handoff.control_context.references must be a list")

    for control_key in ("known_clean_controls", "known_failure_controls"):
        controls = handoff.get(control_key)
        if not isinstance(controls, list):
            errors.append(f"handoff: {control_key} must be a list")
            continue
        for index, control in enumerate(controls):
            validate_control(
                control,
                root,
                f"handoff.{control_key}[{index}]",
                errors,
                allow_missing_media,
            )
    if not isinstance(handoff.get("excluded_checks"), list):
        errors.append("handoff: excluded_checks must be a list")

    return {
        "project_id": project_id,
        "generation_name": generation.get("name"),
        "generation_version": generation.get("version"),
        "generation_sha256": generation_hash,
        "review_min_version": handoff.get("review_skill_min_version"),
        "review_scope": set(scope),
        "media_sha256": media_sha,
        "duration_sec": duration,
        "anchor_ids": anchor_ids,
        "source_hashes": source_hashes,
        "quality_mode": delivery.get("quality_mode") if isinstance(delivery, dict) else None,
        "root": root,
    }, errors


def validate_result(
    result: dict[str, Any],
    handoff: dict[str, Any],
    context: dict[str, Any],
    allow_missing_evidence: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    root: Path = context["root"]
    if result.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"result: schema_version must be {SCHEMA_VERSION}")
    review_id = require(result, "review_id", "result", errors)
    if result.get("project_id") != context["project_id"]:
        errors.append("result: project_id differs from handoff")

    review_skill = result.get("review_skill")
    if not isinstance(review_skill, dict):
        errors.append("result: review_skill must be an object")
        review_skill = {}
    if review_skill.get("name") != "video-review-evolution":
        errors.append("result: review_skill.name must be video-review-evolution")
    review_version = semver_tuple(review_skill.get("version"))
    minimum = semver_tuple(context["review_min_version"])
    if review_version is None:
        errors.append("result: review_skill.version must be semantic")
    elif minimum is not None and review_version < minimum:
        errors.append("result: review_skill.version is below handoff minimum")
    review_hash = review_skill.get("sha256")
    if review_hash and not SHA256.match(str(review_hash)):
        errors.append("result: review_skill.sha256 is invalid")

    generation = result.get("generation_skill")
    if not isinstance(generation, dict):
        errors.append("result: generation_skill must be an object")
        generation = {}
    if generation.get("name") != context["generation_name"]:
        errors.append("result: generation_skill.name differs from handoff")
    if generation.get("version") != context["generation_version"]:
        errors.append("result: generation_skill.version differs from handoff")

    independent_required = context["quality_mode"] in {"standard", "hero"}
    validate_reviewer(
        result.get("reviewer"),
        "result.reviewer",
        errors,
        independent_required,
    )
    if result.get("media_sha256") != context["media_sha256"]:
        errors.append("result: media_sha256 differs from handoff")
    phase = result.get("phase", "calibrated")
    if phase not in REVIEW_PHASES:
        errors.append("result: phase must be initial or calibrated")
    if not isinstance(result.get("user_calibration_required", True), bool):
        errors.append("result: user_calibration_required must be a boolean")
    elif (
        context["quality_mode"] in {"standard", "hero"}
        and result.get("user_calibration_required", True) is not True
    ):
        errors.append(
            "result: standard and Hero reviews require user issue calibration"
        )

    coverage = result.get("coverage")
    if not isinstance(coverage, dict) or not coverage:
        errors.append("result: coverage must be a non-empty object")
        coverage = {}
    for name, status in coverage.items():
        if name not in COVERAGE:
            errors.append(f"result: unknown coverage category {name!r}")
        if status not in COVERAGE_STATUSES:
            errors.append(f"result: invalid coverage status for {name}: {status!r}")
    missing_coverage = context["review_scope"] - set(coverage)
    if missing_coverage:
        errors.append(
            "result: missing declared review coverage: "
            + ", ".join(sorted(missing_coverage))
        )
    coverage_reasons = result.get("coverage_reasons")
    if not isinstance(coverage_reasons, dict):
        errors.append("result: coverage_reasons must be an object")
        coverage_reasons = {}
    for name, status in coverage.items():
        if status != "pass" and not str(coverage_reasons.get(name, "")).strip():
            errors.append(f"result: coverage {name} needs a reason for {status}")

    verdict = result.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"result: invalid verdict {verdict!r}")

    issues = result.get("issues")
    if not isinstance(issues, list):
        errors.append("result: issues must be a list")
        issues = []
    issue_ids: set[str] = set()
    issues_by_id: dict[str, dict[str, Any]] = {}
    for index, issue in enumerate(issues):
        prefix = f"result.issues[{index}]"
        if not isinstance(issue, dict):
            errors.append(f"{prefix} must be an object")
            continue
        issue_id = require(issue, "issue_id", prefix, errors)
        if issue_id in issue_ids:
            errors.append(f"{prefix}.issue_id is duplicated")
        if issue_id:
            issue_ids.add(str(issue_id))
            issues_by_id[str(issue_id)] = issue
        anchor = issue.get("anchor")
        if anchor is not None and str(anchor) not in context["anchor_ids"]:
            errors.append(f"{prefix}.anchor is unknown")
        start = issue.get("start_sec")
        end = issue.get("end_sec")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
            or start < 0
            or end < start
        ):
            errors.append(f"{prefix} has invalid start_sec/end_sec")
        elif (
            context["duration_sec"] is not None
            and end > context["duration_sec"] + 0.001
        ):
            errors.append(f"{prefix} extends beyond media duration")
        for key in ("observed", "expected_source"):
            require(issue, key, prefix, errors)
        if issue.get("intent_judgment") not in INTENT_JUDGMENTS:
            errors.append(f"{prefix}.intent_judgment is invalid")
        if issue.get("verdict") not in ISSUE_VERDICTS:
            errors.append(f"{prefix}.verdict is invalid")
        if issue.get("severity") not in SEVERITIES:
            errors.append(f"{prefix}.severity is invalid")
        if issue.get("confidence") not in CONFIDENCES:
            errors.append(f"{prefix}.confidence is invalid")
        validate_evidence(
            root,
            issue.get("evidence"),
            f"{prefix}.evidence",
            errors,
            allow_missing_evidence,
            issue.get("verdict") in {"confirmed", "conditionally_confirmed"},
        )

    confirmed_blocking = [
        issue
        for issue in issues_by_id.values()
        if issue.get("verdict") in {"confirmed", "conditionally_confirmed"}
        and issue.get("severity") in {"blocker", "major"}
    ]
    if verdict == "pass":
        if any(status != "pass" for status in coverage.values()):
            errors.append("result: pass verdict requires every coverage item to pass")
        if confirmed_blocking:
            errors.append(
                "result: pass verdict conflicts with confirmed blocker/major issues"
            )

    requests = result.get("generation_change_requests")
    if not isinstance(requests, list):
        errors.append("result: generation_change_requests must be a list")
        requests = []
    if phase == "initial" and requests:
        errors.append(
            "result: initial issue list cannot contain generation change requests"
        )
    request_ids: set[str] = set()
    request_by_id: dict[str, dict[str, Any]] = {}
    for index, request in enumerate(requests):
        prefix = f"result.generation_change_requests[{index}]"
        if not isinstance(request, dict):
            errors.append(f"{prefix} must be an object")
            continue
        request_id = require(request, "id", prefix, errors)
        if request_id in request_ids:
            errors.append(f"{prefix}.id is duplicated")
        if request_id:
            request_ids.add(str(request_id))
            request_by_id[str(request_id)] = request
        linked = request.get("issue_ids")
        if not isinstance(linked, list) or not linked:
            errors.append(f"{prefix}.issue_ids must be non-empty")
            linked = []
        for issue_id in linked:
            if issue_id not in issues_by_id:
                errors.append(f"{prefix} references unknown issue {issue_id!r}")
            elif issues_by_id[str(issue_id)].get("verdict") not in {
                "confirmed",
                "conditionally_confirmed",
            }:
                errors.append(
                    f"{prefix} may only link confirmed issues ({issue_id})"
                )
        if request.get("target_layer") not in TARGET_LAYERS:
            errors.append(f"{prefix}.target_layer is invalid")
        if request.get("suggested_scope") not in SCOPES:
            errors.append(f"{prefix}.suggested_scope is invalid")
        for key in ("relationship", "required_observable_change"):
            require(request, key, prefix, errors)
        preserved = request.get("must_preserve")
        if not isinstance(preserved, list) or not preserved:
            errors.append(f"{prefix}.must_preserve must be non-empty")

        regression_cases = request.get("regression_cases")
        if not isinstance(regression_cases, list) or not regression_cases:
            errors.append(f"{prefix}.regression_cases must be non-empty")
            regression_cases = []
        case_ids: set[str] = set()
        roles: set[str] = set()
        for case_index, case in enumerate(regression_cases):
            case_prefix = f"{prefix}.regression_cases[{case_index}]"
            if not isinstance(case, dict):
                errors.append(f"{case_prefix} must be an object")
                continue
            case_id = require(case, "case_id", case_prefix, errors)
            require(case, "role", case_prefix, errors)
            require(case, "route", case_prefix, errors)
            if case.get("role") not in REGRESSION_ROLES:
                errors.append(f"{case_prefix}.role is invalid")
            else:
                roles.add(str(case["role"]))
            if not isinstance(case.get("required"), bool):
                errors.append(f"{case_prefix}.required must be a boolean")
            if case_id in case_ids:
                errors.append(f"{case_prefix}.case_id is duplicated")
            if case_id:
                case_ids.add(str(case_id))
        if "original-failure" not in roles:
            errors.append(f"{prefix} needs an original-failure regression case")
        scope_name = request.get("suggested_scope")
        if scope_name in {"conditional-core", "unconditional-core"}:
            required_roles = {
                "same-mechanism-positive",
                "known-clean-control",
                "negative-example",
            }
            if not required_roles.issubset(roles):
                errors.append(
                    f"{prefix} is missing regression roles: "
                    + ", ".join(sorted(required_roles - roles))
                )
        if scope_name == "unconditional-core":
            required_roles = {"cross-route-positive", "holdout"}
            if not required_roles.issubset(roles):
                errors.append(
                    f"{prefix} is missing universal regression roles: "
                    + ", ".join(sorted(required_roles - roles))
                )

        risk = request.get("risk_assessment")
        if not isinstance(risk, dict):
            errors.append(f"{prefix}.risk_assessment must be an object")
        else:
            for key in (
                "possible_negative_effects",
                "exemption_conditions",
                "net_benefit_metrics",
            ):
                value = risk.get(key)
                if not isinstance(value, list) or not value:
                    errors.append(f"{prefix}.risk_assessment.{key} must be non-empty")

    if not isinstance(result.get("limitations"), list):
        errors.append("result: limitations must be a list")
    if not isinstance(result.get("residual_risks"), list):
        errors.append("result: residual_risks must be a list")

    return {
        "review_id": review_id,
        "request_ids": request_ids,
        "request_by_id": request_by_id,
        "issues_by_id": issues_by_id,
        "reviewer": result.get("reviewer"),
        "review_skill": review_skill,
        "generation_skill": generation,
        "media_sha256": result.get("media_sha256"),
        "project_id": result.get("project_id"),
        "verdict": verdict,
        "phase": phase,
    }, errors


def validate_response(
    response: dict[str, Any],
    result: dict[str, Any],
    result_context: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if response.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"response: schema_version must be {SCHEMA_VERSION}")
    if response.get("review_id") != result.get("review_id"):
        errors.append("response: review_id differs from review result")
    if response.get("media_sha256") != result.get("media_sha256"):
        errors.append("response: media_sha256 differs from reviewed media")
    if result_context.get("phase") != "calibrated":
        errors.append(
            "response: user issue calibration must complete before generation response"
        )

    responses = response.get("responses")
    if not isinstance(responses, list):
        errors.append("response: responses must be a list")
        return {"accepted_request_ids": set(), "new_media_sha256": None}, errors
    seen: set[str] = set()
    accepted_request_ids: set[str] = set()
    accepted_hashes: set[str] = set()
    for index, item in enumerate(responses):
        prefix = f"response.responses[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        request_id = require(item, "change_request_id", prefix, errors)
        if request_id not in result_context["request_ids"]:
            errors.append(f"{prefix} references unknown change request {request_id!r}")
        if request_id in seen:
            errors.append(f"{prefix} duplicates change request {request_id!r}")
        if request_id:
            seen.add(str(request_id))
        decision = item.get("decision")
        if decision not in {"accepted", "rejected", "deferred"}:
            errors.append(f"{prefix}.decision is invalid")
        if decision == "rejected" and not str(item.get("reason", "")).strip():
            errors.append(f"{prefix} rejected decision needs reason")
        if decision != "accepted":
            continue
        accepted_request_ids.add(str(request_id))
        for key in ("responsible_layer", "changed_files_or_rules", "preserved"):
            value = item.get(key)
            if not isinstance(value, list) or not value:
                if key == "responsible_layer":
                    if not str(value or "").strip():
                        errors.append(f"{prefix}.{key} must be non-empty")
                else:
                    errors.append(f"{prefix}.{key} must be a non-empty list")
        new_sha = str(item.get("new_media_sha256") or "")
        if not SHA256.match(new_sha):
            errors.append(f"{prefix}.new_media_sha256 must be 64 hex characters")
        elif new_sha == result.get("media_sha256"):
            errors.append(f"{prefix} did not produce new media bytes")
        else:
            accepted_hashes.add(new_sha)
        if not isinstance(item.get("regression_results"), list):
            errors.append(f"{prefix}.regression_results must be a list")
        regression = item.get("regression_results")
        request = result_context["request_by_id"].get(str(request_id), {})
        required_cases = {
            str(case.get("case_id"))
            for case in request.get("regression_cases", [])
            if isinstance(case, dict) and case.get("required") is True
        }
        if isinstance(regression, list):
            case_ids: set[str] = set()
            for case_index, case in enumerate(regression):
                case_prefix = f"{prefix}.regression_results[{case_index}]"
                if not isinstance(case, dict):
                    errors.append(f"{case_prefix} must be an object")
                    continue
                case_id = require(case, "case_id", case_prefix, errors)
                if case.get("result") not in REGRESSION_RESULTS:
                    errors.append(f"{case_prefix}.result is invalid")
                elif (
                    case_id in required_cases
                    and case.get("result") != "pass"
                ):
                    errors.append(
                        f"{case_prefix} must pass before the change can be accepted"
                    )
                if case_id in case_ids:
                    errors.append(f"{case_prefix}.case_id is duplicated")
                if case_id:
                    case_ids.add(str(case_id))
            missing = required_cases - case_ids
            if missing:
                errors.append(
                    f"{prefix} is missing required regression results: "
                    + ", ".join(sorted(missing))
                )
        unresolved = item.get("unresolved")
        if not isinstance(unresolved, list):
            errors.append(f"{prefix}.unresolved must be a list")
        elif unresolved:
            errors.append(
                f"{prefix}.unresolved must be empty before the change is accepted"
            )

    missing = result_context["request_ids"] - seen
    if missing:
        errors.append(
            "response: missing responses for: " + ", ".join(sorted(missing))
        )
    if len(accepted_hashes) > 1:
        errors.append("response: accepted changes use inconsistent media hashes")
    top_hash = response.get("new_media_sha256")
    if accepted_hashes:
        if not SHA256.match(str(top_hash or "")):
            errors.append("response: new_media_sha256 must be 64 hex characters")
        elif str(top_hash) not in accepted_hashes:
            errors.append("response: new_media_sha256 does not match accepted changes")
    if not isinstance(response.get("rule_changes"), list):
        errors.append("response: rule_changes must be a list")
    skill_change = response.get("generation_skill_change")
    if not isinstance(skill_change, dict):
        errors.append("response: generation_skill_change must be an object")
    else:
        changed = skill_change.get("changed")
        if not isinstance(changed, bool):
            errors.append("response: generation_skill_change.changed must be boolean")
        old_version = semver_tuple(skill_change.get("from_version"))
        new_version = semver_tuple(skill_change.get("to_version"))
        if old_version is None or new_version is None:
            errors.append("response: generation Skill versions must be semantic")
        elif changed and new_version <= old_version:
            errors.append("response: changed generation Skill version must increase")
        elif not changed and new_version != old_version:
            errors.append(
                "response: unchanged generation Skill must keep the same version"
            )
    return {
        "accepted_request_ids": accepted_request_ids,
        "new_media_sha256": top_hash if accepted_hashes else None,
    }, errors


def validate_verification(
    verification: dict[str, Any],
    handoff: dict[str, Any],
    result: dict[str, Any],
    response: dict[str, Any] | None,
    result_context: dict[str, Any],
    response_context: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    root = Path(handoff["_path"]).resolve().parent.parent
    if verification.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"verification: schema_version must be {SCHEMA_VERSION}")
    require(verification, "verification_review_id", "verification", errors)
    if verification.get("prior_review_id") != result.get("review_id"):
        errors.append("verification: prior_review_id differs from review result")
    if verification.get("project_id") != result.get("project_id"):
        errors.append("verification: project_id differs from review result")

    review_skill = verification.get("review_skill")
    if not isinstance(review_skill, dict):
        errors.append("verification: review_skill must be an object")
    elif review_skill.get("name") != "video-review-evolution":
        errors.append("verification: review_skill.name is invalid")
    elif semver_tuple(review_skill.get("version")) is None:
        errors.append("verification: review_skill.version must be semantic")
    validate_reviewer(
        verification.get("reviewer"),
        "verification.reviewer",
        errors,
        True,
    )

    accepted_ids = (
        response_context["accepted_request_ids"]
        if response_context is not None
        else set()
    )
    request_ids = verification.get("change_request_ids")
    if not isinstance(request_ids, list):
        errors.append("verification: change_request_ids must be a list")
        request_ids = []
    if accepted_ids and set(request_ids) != accepted_ids:
        errors.append(
            "verification: change_request_ids must match accepted change requests"
        )

    result_status = verification.get("result")
    if result_status not in VERIFICATION_RESULTS:
        errors.append("verification: result is invalid")
    if accepted_ids:
        if verification.get("original_media_sha256") != result.get("media_sha256"):
            errors.append("verification: original_media_sha256 differs from review")
        expected_new = response.get("new_media_sha256") if response else None
        if verification.get("reviewed_media_sha256") != expected_new:
            errors.append("verification: reviewed_media_sha256 differs from response")
        media = verification.get("media")
        if not isinstance(media, dict):
            errors.append("verification: media must be an object")
        else:
            validate_hashed_file(
                root,
                media.get("path"),
                media.get("sha256"),
                "verification.media",
                errors,
                False,
            )
            if media.get("sha256") != expected_new:
                errors.append("verification: media hash differs from response")
        if result_status != "validated":
            errors.append("verification: accepted change must be independently validated")
        regression = verification.get("regression_results")
        if not isinstance(regression, list):
            errors.append("verification: regression_results must be a list")
        else:
            required_case_ids = {
                str(case.get("case_id"))
                for request_id in accepted_ids
                for case in result_context["request_by_id"]
                .get(request_id, {})
                .get("regression_cases", [])
                if isinstance(case, dict) and case.get("required") is True
            }
            observed_case_ids = {
                str(case.get("case_id"))
                for case in regression
                if isinstance(case, dict)
            }
            missing_cases = required_case_ids - observed_case_ids
            if missing_cases:
                errors.append(
                    "verification: missing required regression results: "
                    + ", ".join(sorted(missing_cases))
                )
            failed = [
                case
                for case in regression
                if not isinstance(case, dict) or case.get("result") != "pass"
            ]
            if failed:
                errors.append(
                    "verification: every regression result must pass before validation"
                )
    elif result_status != "not_applicable":
        errors.append(
            "verification: no accepted change requests require not_applicable"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--allow-missing-media", action="store_true")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Require the response and second-review verification when requested.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    context: dict[str, Any] = {}
    result_context: dict[str, Any] = {}
    response_context: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    try:
        handoff = load_json(args.handoff)
        handoff["_path"] = str(args.handoff)
        context, handoff_errors = validate_handoff(
            handoff,
            args.handoff,
            args.allow_missing_media,
        )
        errors.extend(handoff_errors)

        result: dict[str, Any] | None = None
        if args.result:
            result = load_json(args.result)
            result_context, result_errors = validate_result(
                result,
                handoff,
                context,
                args.allow_missing_media,
            )
            errors.extend(result_errors)

        if args.response:
            if result is None:
                errors.append("response validation requires --result")
            else:
                response = load_json(args.response)
                response_context, response_errors = validate_response(
                    response,
                    result,
                    result_context,
                )
                errors.extend(response_errors)

        if args.verification:
            if result is None:
                errors.append("verification validation requires --result")
            else:
                verification = load_json(args.verification)
                errors.extend(
                    validate_verification(
                        verification,
                        handoff,
                        result,
                        response,
                        result_context,
                        response_context,
                    )
                )

        if args.require_complete:
            if result is None:
                errors.append("complete validation requires --result")
            elif result_context.get("phase") != "calibrated":
                errors.append(
                    "complete validation requires a user-calibrated review result"
                )
            elif result_context.get("request_ids") and response is None:
                errors.append("complete validation requires --response")
            elif (
                response_context
                and response_context.get("accepted_request_ids")
                and args.verification is None
            ):
                errors.append("complete validation requires --verification")
    except ValueError as exc:
        errors.append(str(exc))

    payload = {
        "ok": not errors,
        "schema_version": SCHEMA_VERSION,
        "handoff": str(args.handoff),
        "result": str(args.result) if args.result else None,
        "response": str(args.response) if args.response else None,
        "verification": str(args.verification) if args.verification else None,
        "warnings": warnings,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        for warning in warnings:
            print(f"WARN: {warning}")
    else:
        print("PASS: review contract is consistent")
        for warning in warnings:
            print(f"WARN: {warning}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
