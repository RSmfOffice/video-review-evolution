#!/usr/bin/env python3
"""Validate generation/review handoff, review result, and change response."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
COVERAGE = {"pass", "warn", "fail", "not_checked", "skipped"}
VERDICTS = {
    "pass",
    "revise",
    "reject",
    "provisional",
    "insufficient_evidence",
}
SCOPES = {
    "project-specific",
    "route-specific",
    "model-specific",
    "conditional-core",
    "unconditional-core",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def require(value: dict[str, Any], key: str, prefix: str, errors: list[str]) -> Any:
    if key not in value or value[key] in (None, ""):
        errors.append(f"{prefix}: missing {key}")
        return None
    return value[key]


def resolve_media(handoff_path: Path, media_path: str) -> Path:
    path = Path(media_path)
    if path.is_absolute():
        return path
    project_root = handoff_path.resolve().parent.parent
    return project_root / path


def validate_handoff(
    handoff: dict[str, Any],
    path: Path,
    allow_missing_media: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    require(handoff, "project_id", "handoff", errors)
    if handoff.get("schema_version") != 1:
        errors.append("handoff: schema_version must be 1")

    generation = handoff.get("generation_skill")
    if not isinstance(generation, dict):
        errors.append("handoff: generation_skill must be an object")
    else:
        if generation.get("name") != "video-production-director":
            errors.append("handoff: generation_skill.name must be video-production-director")
        if not SEMVER.match(str(generation.get("version", ""))):
            errors.append("handoff: generation_skill.version must be semantic")

    if not SEMVER.match(str(handoff.get("review_skill_min_version", ""))):
        errors.append("handoff: review_skill_min_version must be semantic")
    review_scope = handoff.get("review_scope")
    if not isinstance(review_scope, list) or not review_scope:
        errors.append("handoff: review_scope must be a non-empty list")
        review_scope = []

    for key in ["delivery", "sources", "control_context"]:
        if not isinstance(handoff.get(key), dict):
            errors.append(f"handoff: {key} must be an object")

    required_observations = handoff.get("required_observations")
    if not isinstance(required_observations, list):
        errors.append("handoff: required_observations must be a list")
    for index, observation in enumerate(required_observations or []):
        if not isinstance(observation, dict):
            errors.append(
                f"handoff: required_observations[{index}] must be an object"
            )
            continue
        for key in ["id", "observable", "acceptance_ids"]:
            require(
                observation,
                key,
                f"handoff.required_observations[{index}]",
                errors,
            )
        if not isinstance(observation.get("acceptance_ids"), list):
            errors.append(
                f"handoff: required_observations[{index}].acceptance_ids "
                "must be a list"
            )

    media = handoff.get("media")
    if not isinstance(media, dict):
        errors.append("handoff: media must be an object")
        media = {}
    media_sha = str(media.get("sha256", ""))
    if not SHA256.match(media_sha):
        errors.append("handoff: media.sha256 must be 64 hex characters")
    for key in ["path", "duration_sec", "width", "height", "fps", "has_audio"]:
        require(media, key, "handoff.media", errors)

    if media.get("path"):
        resolved = resolve_media(path, str(media["path"]))
        if not resolved.exists():
            message = f"handoff: media file not found: {resolved}"
            if allow_missing_media:
                warnings.append(message)
            else:
                errors.append(message)
        elif SHA256.match(media_sha):
            actual = sha256(resolved)
            if actual.lower() != media_sha.lower():
                errors.append(
                    "handoff: media hash mismatch "
                    f"(declared {media_sha}, actual {actual})"
                )

    anchors = handoff.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        errors.append("handoff: anchors must be a non-empty list")
        anchors = []
    anchor_ids: set[str] = set()
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            errors.append(f"handoff: anchors[{index}] must be an object")
            continue
        anchor_id = require(anchor, "id", f"handoff.anchors[{index}]", errors)
        require(anchor, "kind", f"handoff.anchors[{index}]", errors)
        start = anchor.get("start_sec")
        end = anchor.get("end_sec")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"handoff: anchors[{index}] needs numeric start_sec/end_sec")
        elif end < start:
            errors.append(f"handoff: anchors[{index}] end_sec precedes start_sec")
        if anchor_id in anchor_ids:
            errors.append(f"handoff: duplicate anchor id {anchor_id}")
        if anchor_id:
            anchor_ids.add(str(anchor_id))

    choices = handoff.get("intentional_choices")
    if not isinstance(choices, list):
        errors.append("handoff: intentional_choices must be a list")
        choices = []
    choice_ids: set[str] = set()
    for index, choice in enumerate(choices):
        if not isinstance(choice, dict):
            errors.append(f"handoff: intentional_choices[{index}] must be an object")
            continue
        choice_id = require(
            choice, "id", f"handoff.intentional_choices[{index}]", errors
        )
        for key in ["relationship", "declared"]:
            require(choice, key, f"handoff.intentional_choices[{index}]", errors)
        must_preserve = choice.get("must_preserve")
        if not isinstance(must_preserve, list) or not must_preserve:
            errors.append(
                f"handoff: intentional_choices[{index}].must_preserve "
                "must be a non-empty list"
            )
        if choice_id in choice_ids:
            errors.append(f"handoff: duplicate intentional choice id {choice_id}")
        if choice_id:
            choice_ids.add(str(choice_id))

    context = {
        "media_sha256": media_sha,
        "anchor_ids": anchor_ids,
        "review_scope": {str(item) for item in review_scope},
    }
    return context, errors, warnings


def validate_result(
    result: dict[str, Any],
    handoff: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if result.get("schema_version") != 1:
        errors.append("result: schema_version must be 1")
    for key in ["review_id", "project_id", "review_skill", "generation_skill"]:
        require(result, key, "result", errors)

    review_skill = result.get("review_skill")
    if isinstance(review_skill, dict):
        if not SEMVER.match(str(review_skill.get("version", ""))):
            errors.append("result: review_skill.version must be semantic")

    handoff_generation = handoff.get("generation_skill")
    result_generation = result.get("generation_skill")
    if isinstance(handoff_generation, dict) and isinstance(result_generation, dict):
        if not SEMVER.match(str(result_generation.get("version", ""))):
            errors.append("result: generation_skill.version must be semantic")
        if result_generation.get("version") != handoff_generation.get("version"):
            errors.append("result: generation_skill.version differs from handoff")

    result_media_sha = str(result.get("media_sha256", ""))
    if result_media_sha != context["media_sha256"]:
        errors.append("result: media_sha256 differs from handoff")

    coverage = result.get("coverage")
    if not isinstance(coverage, dict) or not coverage:
        errors.append("result: coverage must be a non-empty object")
        coverage = {}
    for name, status in coverage.items():
        if status not in COVERAGE:
            errors.append(f"result: invalid coverage status for {name}: {status!r}")
    missing_coverage = context["review_scope"] - set(coverage)
    for name in sorted(missing_coverage):
        errors.append(f"result: missing declared review coverage: {name}")

    verdict = result.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"result: invalid verdict {verdict!r}")
    if verdict == "pass" and any(value != "pass" for value in coverage.values()):
        errors.append("result: pass verdict requires every declared coverage item to pass")

    anchors = handoff.get("anchors", [])
    anchor_ids = {str(item.get("id")) for item in anchors if isinstance(item, dict)}

    issues = result.get("issues")
    if not isinstance(issues, list):
        errors.append("result: issues must be a list")
        issues = []
    issue_ids: set[str] = set()
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"result: issues[{index}] must be an object")
            continue
        issue_id = require(issue, "issue_id", f"result.issues[{index}]", errors)
        anchor = issue.get("anchor")
        if anchor is not None and str(anchor) not in anchor_ids:
            errors.append(f"result: issues[{index}] references unknown anchor {anchor!r}")
        for key in [
            "start_sec",
            "end_sec",
            "observed",
            "expected_source",
            "verdict",
            "severity",
            "confidence",
        ]:
            require(issue, key, f"result.issues[{index}]", errors)
        if not isinstance(issue.get("evidence"), list):
            errors.append(f"result: issues[{index}].evidence must be a list")
        if issue_id in issue_ids:
            errors.append(f"result: duplicate issue_id {issue_id}")
        if issue_id:
            issue_ids.add(str(issue_id))

    change_requests = result.get("generation_change_requests")
    if not isinstance(change_requests, list):
        errors.append("result: generation_change_requests must be a list")
        change_requests = []
    request_ids: set[str] = set()
    for index, request in enumerate(change_requests):
        if not isinstance(request, dict):
            errors.append(f"result: generation_change_requests[{index}] must be an object")
            continue
        request_id = require(
            request, "id", f"result.generation_change_requests[{index}]", errors
        )
        linked_issues = request.get("issue_ids")
        if not isinstance(linked_issues, list):
            errors.append(
                f"result: generation_change_requests[{index}].issue_ids "
                "must be a list"
            )
            linked_issues = []
        for issue_id in linked_issues:
            if issue_id not in issue_ids:
                errors.append(
                    f"result: generation change request {request_id} "
                    f"references unknown issue {issue_id}"
                )
        if request.get("suggested_scope") not in SCOPES:
            errors.append(
                f"result: generation change request {request_id} has invalid scope"
            )
        for key in [
            "target_layer",
            "relationship",
            "required_observable_change",
            "must_preserve",
            "positive_tests",
            "negative_tests",
        ]:
            require(
                request,
                key,
                f"result.generation_change_requests[{index}]",
                errors,
            )
        if request_id in request_ids:
            errors.append(f"result: duplicate generation change request id {request_id}")
        if request_id:
            request_ids.add(str(request_id))

    context = {"request_ids": request_ids, "review_id": result.get("review_id")}
    return context, errors


def validate_response(
    response: dict[str, Any],
    result: dict[str, Any],
    result_context: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if response.get("schema_version") != 1:
        errors.append("response: schema_version must be 1")
    if response.get("review_id") != result.get("review_id"):
        errors.append("response: review_id differs from review result")
    responses = response.get("responses")
    if not isinstance(responses, list):
        errors.append("response: responses must be a list")
        return errors

    seen: set[str] = set()
    for index, item in enumerate(responses):
        if not isinstance(item, dict):
            errors.append(f"response.responses[{index}] must be an object")
            continue
        request_id = require(
            item, "change_request_id", f"response.responses[{index}]", errors
        )
        if request_id not in result_context["request_ids"]:
            errors.append(f"response: unknown change request {request_id!r}")
        if request_id in seen:
            errors.append(f"response: duplicate response for {request_id}")
        if request_id:
            seen.add(str(request_id))
        decision = item.get("decision")
        if decision not in {"accepted", "rejected", "deferred"}:
            errors.append(f"response: invalid decision {decision!r}")
        if decision == "accepted":
            sha = str(item.get("new_media_sha256", ""))
            if not SHA256.match(sha):
                errors.append(
                    f"response: accepted request {request_id} needs new_media_sha256"
                )
            elif sha == result.get("media_sha256"):
                errors.append(
                    f"response: accepted request {request_id} did not produce new media bytes"
                )
            regression = item.get("regression")
            if not isinstance(regression, dict):
                errors.append(
                    f"response: accepted request {request_id} needs regression object"
                )
        if decision == "rejected" and not item.get("reason"):
            errors.append(f"response: rejected request {request_id} needs reason")

    missing = result_context["request_ids"] - seen
    for request_id in sorted(missing):
        errors.append(f"response: missing response for {request_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--allow-missing-media", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    try:
        handoff = load_json(args.handoff)
        context, handoff_errors, handoff_warnings = validate_handoff(
            handoff, args.handoff, args.allow_missing_media
        )
        errors.extend(handoff_errors)
        warnings.extend(handoff_warnings)

        result = None
        result_context = {"request_ids": set(), "review_id": None}
        if args.result:
            result = load_json(args.result)
            result_context, result_errors = validate_result(result, handoff, context)
            errors.extend(result_errors)

        if args.response:
            if result is None:
                errors.append("response validation requires --result")
            else:
                response = load_json(args.response)
                errors.extend(validate_response(response, result, result_context))
    except ValueError as exc:
        errors.append(str(exc))

    payload = {
        "ok": not errors,
        "handoff": str(args.handoff),
        "result": str(args.result) if args.result else None,
        "response": str(args.response) if args.response else None,
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
