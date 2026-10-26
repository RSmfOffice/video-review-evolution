from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_memory.py"
INITIALIZER = SKILL_ROOT / "scripts" / "init_memory.py"
EMPTY_ISSUES = SKILL_ROOT / "references" / "issue-ledger.template.jsonl"
SEED_RULES = SKILL_ROOT / "references" / "rule-registry.seed.jsonl"


class ReviewMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.issues = self.root / "issue-ledger.jsonl"
        self.rules = self.root / "rule-registry.jsonl"
        shutil.copy2(EMPTY_ISSUES, self.issues)
        shutil.copy2(SEED_RULES, self.rules)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> tuple[int, dict[str, object]]:
        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(VALIDATOR),
                "--issues",
                str(self.issues),
                "--rules",
                str(self.rules),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return completed.returncode, json.loads(completed.stdout)

    def append_jsonl(self, path: Path, record: dict[str, object]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def test_fresh_memory_is_valid(self) -> None:
        code, payload = self.validate()
        self.assertEqual(0, code, json.dumps(payload, ensure_ascii=False))
        self.assertEqual(0, payload["issues"])
        self.assertEqual(13, payload["rules"])

    def test_absolute_media_path_is_rejected(self) -> None:
        record = {
            "record_kind": "issue",
            "record_id": "ISSUE-ABS-R1",
            "review_id": "REV-ABS",
            "issue_id": "ISS-ABS",
            "revision": 1,
            "recorded_at": "2026-10-26",
            "reviewer_skill_version": "0.3.0",
            "domain_skill": "video-production-director@0.5.0",
            "project_id": "absolute-path",
            "media": {
                "path": "/private/final.mp4",
                "sha256": "0" * 64,
            },
            "timecode": "0-1",
            "reported_by": "agent",
            "reported": "Fixture",
            "observed": "Fixture",
            "expected_source": "Fixture",
            "verdict": "confirmed",
            "severity": "major",
            "confidence": "high",
            "impact": "Fixture",
            "evidence": [],
            "relationship_primitive": "fixture",
            "rule_ids": ["VR-004"],
            "scope": "project-specific",
            "status": "confirmed",
            "supersedes": None,
            "notes": "Fixture",
        }
        self.append_jsonl(self.issues, record)
        code, payload = self.validate()
        self.assertEqual(1, code)
        self.assertTrue(
            any("project-relative" in item for item in payload["errors"])
        )

    def test_validated_quality_rule_requires_regression(self) -> None:
        record = {
            "record_kind": "rule",
            "record_id": "RULE-INVALID-R1",
            "rule_id": "VR-INVALID",
            "revision": 1,
            "recorded_at": "2026-10-26",
            "version": "0.3.0",
            "status": "validated",
            "scope": "conditional-core",
            "rule_kind": "quality-heuristic",
            "statement": "An unverified visual rule.",
            "trigger": "Any visual.",
            "pass_if": "Untested.",
            "fail_if": "Untested.",
            "exemptions": "None.",
            "evidence_case_ids": [],
            "regression_cases": [],
            "supersedes": None,
            "notes": "Negative test.",
        }
        self.append_jsonl(self.rules, record)
        code, payload = self.validate()
        self.assertEqual(1, code)
        self.assertTrue(
            any(
                "non-project quality rule needs evidence" in item
                for item in payload["errors"]
            )
        )

    def test_process_invariant_can_be_validated_without_video_regression(self) -> None:
        record = {
            "record_kind": "rule",
            "record_id": "RULE-PROCESS-R1",
            "rule_id": "VR-PROCESS",
            "revision": 1,
            "recorded_at": "2026-10-26",
            "version": "0.3.0",
            "status": "validated",
            "scope": "conditional-core",
            "rule_kind": "process-invariant",
            "statement": "Final media must be hashed.",
            "trigger": "Final review.",
            "pass_if": "The hash exists.",
            "fail_if": "The hash is absent.",
            "exemptions": "Planning only.",
            "evidence_case_ids": [],
            "regression_cases": [],
            "supersedes": None,
            "notes": "Process rules do not require visual regression.",
        }
        self.append_jsonl(self.rules, record)
        code, payload = self.validate()
        self.assertEqual(0, code, json.dumps(payload, ensure_ascii=False))


class MemoryMigrationTests(unittest.TestCase):
    def test_absolute_paths_are_rewritten_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            media = project / "renders" / "final.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"media")
            issue_source = root / "legacy.jsonl"
            issue_record = {
                "record_kind": "issue",
                "record_id": "ISSUE-MIGRATE-R1",
                "review_id": "REV-MIGRATE",
                "issue_id": "ISS-MIGRATE",
                "revision": 1,
                "recorded_at": "2026-10-26",
                "reviewer_skill_version": "0.2.0",
                "domain_skill": "video-production-director@0.4.0",
                "project_id": "migrate",
                "media": {
                    "path": str(media),
                    "sha256": "0" * 64,
                },
                "timecode": "0-1",
                "reported_by": "agent",
                "reported": "Fixture",
                "observed": "Fixture",
                "expected_source": "Fixture",
                "verdict": "not_reproduced",
                "severity": "note",
                "confidence": "low",
                "impact": "Fixture",
                "evidence": [],
                "relationship_primitive": "fixture",
                "rule_ids": [],
                "scope": "project-specific",
                "status": "rejected",
                "supersedes": None,
                "notes": "Fixture",
            }
            issue_source.write_text(
                json.dumps(issue_record, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            destination = root / "memory"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INITIALIZER),
                    "--memory-root",
                    str(destination),
                    "--issues-source",
                    str(issue_source),
                    "--project-root",
                    str(project),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            migrated = json.loads(
                (destination / "issue-ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual("renders/final.mp4", migrated["media"]["path"])


if __name__ == "__main__":
    unittest.main()
