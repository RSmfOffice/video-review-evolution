# Video Review Evolution

**English** | [简体中文](README.zh-CN.md)

An evidence-first Codex Skill for independently reviewing video outputs,
tracking defects across revisions, and validating whether production fixes are
genuine net improvements.

Current version: **0.3.0**

This Skill is the independent review side of a two-Skill workflow. Its companion
is [video-production-director](https://github.com/RSmfOffice/Agent-Skill-for-evidence-gated-AI-video-production.).

## What it enforces

- Exact reviewed-media and source hashes.
- Stable shot, graphic, and event anchors.
- Review-scope coverage that cannot be collapsed into a vague pass.
- Evidence-backed issues with time ranges and reviewer identity.
- Separate project, route, model, and cross-route rule scopes.
- Structured regression cases for original failures, positives, negatives,
  clean controls, cross-route checks, and holdout.
- A second independent review of changed media before a fix is validated.
- Portable runtime memory outside the distributable Skill.

## Install

```bash
git clone git@github.com:RSmfOffice/video-review-evolution.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/video-review-evolution"
```

Initialize runtime memory once:

```bash
python scripts/init_memory.py
```

Default memory location:

```text
$VIDEO_REVIEW_MEMORY_DIR
or
$CODEX_HOME/video-review-memory/
```

## Validate

```bash
python scripts/validate_memory.py

python scripts/validate_contracts.py \
  --handoff <project>/qa/review-handoff.json \
  --result <project>/qa/review-result.json \
  --response <project>/qa/change-response.json \
  --verification <project>/qa/review-verification.json \
  --require-complete
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

## Version history

- `v0.3.0`: schema-v2 review contracts, structured regression, independent
  post-change verification, portable memory.
- `v0.2.0`: historical archive of the original review handoff architecture.
  Private local review ledgers are intentionally omitted from the public tag.

## License

MIT. See [LICENSE](LICENSE).
