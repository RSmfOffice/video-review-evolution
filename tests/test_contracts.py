from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_contracts.py"
FIXTURES = SKILL_ROOT / "tests" / "fixtures"


class ReviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "fixtures"
        shutil.copytree(FIXTURES, self.root)
        self.qa = self.root / "qa"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self, name: str) -> dict[str, object]:
        return json.loads(
            (self.qa / name).read_text(encoding="utf-8")
        )

    def write(self, name: str, value: dict[str, object]) -> None:
        (self.qa / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def validate(self) -> tuple[int, dict[str, object]]:
        command = [
            sys.executable,
            "-X",
            "utf8",
            str(VALIDATOR),
            "--handoff",
            str(self.qa / "review-handoff.json"),
            "--result",
            str(self.qa / "review-result.json"),
            "--response",
            str(self.qa / "change-response.json"),
            "--verification",
            str(self.qa / "review-verification.json"),
            "--require-complete",
            "--json",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        payload = json.loads(completed.stdout)
        return completed.returncode, payload

    def assert_fails(self, expected: str) -> None:
        code, payload = self.validate()
        self.assertEqual(1, code)
        errors = payload.get("errors", [])
        self.assertTrue(
            any(expected in str(error) for error in errors),
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def test_complete_fixture_passes(self) -> None:
        code, payload = self.validate()
        self.assertEqual(0, code, json.dumps(payload, ensure_ascii=False, indent=2))
        self.assertTrue(payload["ok"])

    def test_project_identity_must_match(self) -> None:
        handoff = self.load("review-handoff.json")
        handoff["project_id"] = "other-project"
        self.write("review-handoff.json", handoff)
        self.assert_fails("project_id differs from handoff")

    def test_review_skill_minimum_version_is_enforced(self) -> None:
        result = self.load("review-result.json")
        result["review_skill"]["version"] = "0.2.0"  # type: ignore[index]
        self.write("review-result.json", result)
        self.assert_fails("below handoff minimum")

    def test_confirmed_issue_requires_evidence(self) -> None:
        result = self.load("review-result.json")
        result["issues"][0]["evidence"] = []  # type: ignore[index]
        self.write("review-result.json", result)
        self.assert_fails("must contain at least one evidence object")

    def test_pass_cannot_coexist_with_confirmed_major(self) -> None:
        result = self.load("review-result.json")
        result["verdict"] = "pass"
        for name in result["coverage"]:  # type: ignore[union-attr]
            result["coverage"][name] = "pass"  # type: ignore[index]
        self.write("review-result.json", result)
        self.assert_fails("pass verdict conflicts")

    def test_response_must_cover_required_regression_cases(self) -> None:
        response = self.load("change-response.json")
        response["responses"][0]["regression_results"] = []  # type: ignore[index]
        self.write("change-response.json", response)
        self.assert_fails("missing required regression results")

    def test_accepted_response_regression_must_pass(self) -> None:
        response = self.load("change-response.json")
        response["responses"][0]["regression_results"][0]["result"] = "fail"  # type: ignore[index]
        self.write("change-response.json", response)
        self.assert_fails("must pass before the change can be accepted")

    def test_second_review_media_hash_is_enforced(self) -> None:
        verification = self.load("review-verification.json")
        verification["reviewed_media_sha256"] = "0" * 64
        self.write("review-verification.json", verification)
        self.assert_fails("reviewed_media_sha256 differs")

    def test_second_review_must_run_required_regressions(self) -> None:
        verification = self.load("review-verification.json")
        verification["regression_results"] = []
        self.write("review-verification.json", verification)
        self.assert_fails("missing required regression results")

    def test_evidence_hash_is_enforced(self) -> None:
        result = self.load("review-result.json")
        result["issues"][0]["evidence"][0]["sha256"] = "0" * 64  # type: ignore[index]
        self.write("review-result.json", result)
        self.assert_fails("sha256 mismatch")

    def test_require_complete_rejects_later_stage_omission(self) -> None:
        command = [
            sys.executable,
            "-X",
            "utf8",
            str(VALIDATOR),
            "--handoff",
            str(self.qa / "review-handoff.json"),
            "--result",
            str(self.qa / "review-result.json"),
            "--require-complete",
            "--json",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(1, completed.returncode)
        self.assertTrue(
            any("requires --response" in item for item in payload["errors"])
        )


if __name__ == "__main__":
    unittest.main()
