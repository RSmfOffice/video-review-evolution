---
name: video-review-evolution
description: Independently review video outputs, produce evidence-backed findings, and evolve a persistent quality standard through structured feedback to a generation Skill; use for iterative video QA, defect discovery, regression, and co-evolution across projects.
license: MIT
metadata:
  short-description: Evidence-first video review and co-evolution
  version: "0.3.0"
---

# Video Review Evolution

Act as an independent reviewer and as the review side of a two-Skill improvement
loop. The generation Skill produces media and a review handoff. This Skill checks
the exact bytes, reports what is wrong, turns confirmed mechanisms into scoped
change requests, and verifies whether the resulting change is a net improvement.

This Skill owns review evidence, defect memory, and review rules. The companion
`video-production-director` owns generation, repair, and production evidence.
Neither Skill may silently approve its own change.

## Choose the mode

- `review`: default. Inspect first and return problems only.
- `calibrate`: verify user corrections and update issue history.
- `coevolve`: produce or apply a scoped improvement to the generation Skill after
  evidence and regression. Apply Skill edits only with explicit authorization.
- `regression`: compare a candidate change against known-clean controls, the
  original failure, and negative examples.

Do not start a repair or rewrite media in `review` mode.

## Before acting

1. Read [references/coevolution-contract.md](references/coevolution-contract.md).
2. Read [references/review-protocol.md](references/review-protocol.md).
3. Read [references/quality-standard.md](references/quality-standard.md).
4. Locate runtime memory at `$VIDEO_REVIEW_MEMORY_DIR`, or
   `$CODEX_HOME/video-review-memory` when unset. Initialize it once:

```bash
python scripts/init_memory.py
```

5. Read relevant recent records in the runtime issue ledger and rule registry,
   then validate memory with:

```bash
python scripts/validate_memory.py
```

6. Lock the current media SHA-256, generation-Skill version, review-Skill
   version, and all provided handoff hashes.
7. When a handoff exists, validate it before reviewing:

```bash
python scripts/validate_contracts.py --handoff <project>/qa/review-handoff.json
```

An existing report, prior pass, source assertion, animatic, or API success is
never evidence for the current final file.

## Review first

When media is available, inspect it before asking the user what they saw.

Run the passes in cheap-to-expensive order:

1. contract and handoff completeness;
2. technical/file validity;
3. static content, text, layout, safe areas, and intentional overlaps;
4. temporal motion, camera, contact, continuity, and temporal instability;
5. editorial comprehension and audio/visual synchronization;
6. targeted native-resolution evidence for each plausible issue;
7. cold review against declared intentional choices and a known-clean control
   when available.

Scan broadly; report only material observations. Do not assign a failing grade
to every dimension merely to complete a table. “No issue” is a valid result.

For every finding, include:

- stable issue ID and stable anchor when a handoff exists;
- current file hash and timecode/frame range;
- observed result;
- expected result and source;
- verdict, severity, confidence;
- evidence path/type;
- whether the issue is subjective, contextual, or a hard requirement.

An overlap, occlusion, transparency, penetration, cut, black frame, silence, or
camera crossing is not a defect merely because the relationship occurs. Use the
reasonableness test in `quality-standard.md`.

If only a low-resolution image, contact sheet, transcript, or proxy exists, report
which checks remain unverified. Never claim to have watched or heard media when
only derived artifacts were inspected.

## Finding and correction

1. Report the agent's independent findings before inviting correction.
2. Treat user correction as important evidence, not automatic universal truth.
3. Re-open the same file and time range; confirm, narrow, reject, or reclassify.
4. Preserve prior revisions in the ledger.
5. Distinguish:
   - project preference;
   - route-specific behavior;
   - model-specific limitation;
   - conditional cross-route principle;
   - verified universal constraint.
6. If user and quality contract conflict, name the conflict and the accountable
   decision owner.

For problem-only requests, omit causes and fixes.

## Co-evolution loop

The loop has four evidence objects:

```text
qa/review-handoff.json   generation intent, hashes, anchors, coverage
qa/review-result.json    findings, intentional-choice checks, change requests
qa/change-response.json  producer's accepted/rejected changes and regression plan
qa/review-verification.json  independent verification of the changed bytes
review memory            scoped rules, corrections, status, supersession
```

When a confirmed issue suggests a production-process fix:

1. classify the relationship primitive without subject names;
2. state the cheapest responsible generation layer;
3. create a `generation_change_request` with observable acceptance and
   regression tests;
4. do not edit the generation Skill in `review` mode;
5. after an authorized change, rerun the original case, known-clean controls,
   and negative examples;
6. verify the changed media bytes in `qa/review-verification.json`;
7. only then update the rule status to `validated` or promote its scope.

Stop after three failed repair rounds on the same cause and escalate. Do not
use best-of-N generation or silently move the failure to another layer.

When the full loop exists, validate that all artifacts refer to the same review,
change requests, and media line:

```bash
python scripts/validate_contracts.py \
  --handoff <project>/qa/review-handoff.json \
  --result <project>/qa/review-result.json \
  --response <project>/qa/change-response.json \
  --verification <project>/qa/review-verification.json \
  --require-complete
```

## Persistent memory

- `$CODEX_HOME/video-review-memory/issue-ledger.jsonl`: append-only issue
  revisions;
- `$CODEX_HOME/video-review-memory/rule-registry.jsonl`: rule versions, scope,
  status, evidence, regression cases, and supersession;
- `references/quality-standard.md`: current readable standard;
- `references/research-basis.md`: sources and the decisions borrowed from them.

Append corrections instead of rewriting history. Never store credentials or
copied media. Store project-relative paths, hashes, short observations, and
decisions. Distributed templates and seed rules remain inside the Skill; mutable
project memory stays outside it.

## Promotion

- one case or one owner preference -> `project-specific`;
- repeatable within one route -> `route-specific`;
- one model/version -> `model-specific`;
- cross-route with explicit trigger and exemptions -> `conditional-core`;
- `unconditional-core` only after independent positive, negative, holdout, and
  cross-route evidence shows no material false-block or quality regression.

No rule gains universal status because it sounds general.
Process invariants are enforced structurally. Quality heuristics require scoped
positive, negative, clean-control, and holdout evidence before `validated`.

## Finish

Lead with the review verdict. For `review`, present the issue list and evidence.
For `calibrate` or `coevolve`, also report:

- what changed in the finding;
- ledger and rule revisions;
- generation-Skill change requests;
- regression result or why it remains provisional;
- residual uncertainty.

Run `python scripts/validate_memory.py` after any memory change.
