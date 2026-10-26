# 生成与审阅协同契约 v2

## 1. 角色

- `video-production-director`：负责 brief、镜头、资产、生成、合成、修复、
  生产证据和生成侧回归。
- `video-review-evolution`：负责独立观察、问题判定、稳定锚点、变更请求、
  审阅记忆和新媒体验证。
- 用户/责任方：决定项目意图、审美接受、预算、权利和最终发布。

生成 Skill 不能自证通过；审阅 Skill 不能直接修改媒体。两者通过以下五个
证据对象协作。

```text
qa/review-handoff.json       项目意图、源文件哈希、媒体哈希和稳定锚点
qa/review-result.json        独立审阅、问题和结构化变更请求
qa/change-response.json      生成侧变更、回归和版本边界
qa/review-verification.json  独立审阅对变更后新字节的确认
review memory                问题与规则的长期作用域、证据和生命周期
```

## 2. 完整闭环

```text
生成与自检
  -> review-handoff v2
  -> 独立 review-result v2
  -> generation_change_request
  -> 生成侧 change-response（provisional）
  -> 新独立 review-verification v2
  -> 原失败、同机制正例、干净对照、反例和 holdout
  -> rule candidate / validated / rejected
  -> 生成侧最终门禁
```

`change-response` 只能证明生成侧完成了修改，不能证明修改有效。只有
`review-verification.result == validated` 且新媒体哈希匹配时，变更才能被
称为已验证。

## 3. `qa/review-handoff.json`

`schema_version` 固定为 `2`。生成侧在选定最终候选后创建。

必需内容：

- `project_id`、ISO 格式 `created_at`；
- 生成 Skill 名称、版本和可选 bundle SHA-256；
- 最低审阅 Skill 版本；
- 本轮实际审阅的 `review_scope`；
- 最终媒体的相对路径、SHA-256、时长、画幅、FPS 和音频状态；
- 平台、预期观看尺寸和 quality mode；
- brief、project、shots、timeline、qa-report 的路径与哈希；
- 必需观察、关联的 acceptance IDs；
- 稳定 shot/graphic/event anchors；
- 有意选择、允许效果和必须保留项；
- route、model、prompt/source 和参考来源；
- 已知干净对照、已知失败对照和 excluded checks。

`project.json` 会随 gate 审批变化。其源哈希使用
`hash_mode: "json-without-gates"`，即去掉可变 `gates` 字段后按稳定 JSON
序列化再计算 SHA-256。

所有路径必须相对项目根目录。媒体、源文件和控制样片的哈希必须可重新计算。

示例：

```json
{
  "schema_version": 2,
  "project_id": "example",
  "created_at": "2026-10-26T12:00:00+08:00",
  "generation_skill": {
    "name": "video-production-director",
    "version": "0.5.0",
    "sha256": null
  },
  "review_skill_min_version": "0.3.0",
  "review_scope": ["technical", "content", "visual", "motion", "rights"],
  "media": {
    "path": "renders/final.mp4",
    "sha256": "64-hex",
    "duration_sec": 10.0,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "has_audio": true
  },
  "delivery": {
    "platform": "local-preview",
    "intended_size": [1920, 1080],
    "quality_mode": "standard"
  },
  "sources": {
    "brief": {"path": "brief.md", "sha256": "64-hex"},
    "project": {
      "path": "project.json",
      "sha256": "64-hex",
      "hash_mode": "json-without-gates"
    },
    "shots": {"path": "shots.json", "sha256": "64-hex"},
    "timeline": {"path": "timeline.json", "sha256": "64-hex"},
    "qa_report": {"path": "qa-report.json", "sha256": "64-hex"}
  },
  "required_observations": [],
  "intentional_choices": [],
  "anchors": [],
  "control_context": {
    "route": "programmatic",
    "model": "local/renderer",
    "prompt_or_source": "src/render.py",
    "references": []
  },
  "known_clean_controls": [],
  "known_failure_controls": [],
  "excluded_checks": [],
  "notes": ""
}
```

## 4. `qa/review-result.json`

`schema_version` 固定为 `2`。由独立审阅侧生成，必须绑定同一 handoff 和
媒体。

必需内容：

- `review_id`、`project_id`、审阅 Skill 名称与版本；
- `reviewer.id`、`reviewer.kind`、`reviewed_at` 和
  `independent_from_producer`；
- 被审媒体的 `media_sha256`；
- 每个 `review_scope` 的 coverage 状态；
- 非 `pass` 覆盖的 `coverage_reasons`；
- issue 的锚点、时间范围、观察、期望、意图判断、verdict、严重度和置信度；
- 确认问题对应的相对路径证据及 SHA-256；
- `generation_change_requests`；
- residual risks 和 limitations。

标准与 Hero 审阅必须独立于生产者。`pass` 不得与已确认的 blocker/major
共存，也不得包含任何非 `pass` coverage。

### 变更请求

每条 `generation_change_request` 必须包含：

- 关联的确认 issue；
- `target_layer` 和关系原语；
- 可观察的期望变化；
- `must_preserve`；
- 结构化 `regression_cases`；
- 负作用、豁免条件和净收益指标；
- 建议作用域。

回归案例角色：

- `original-failure`
- `same-mechanism-positive`
- `cross-route-positive`
- `high-complexity-positive`
- `known-clean-control`
- `negative-example`
- `holdout`

`conditional-core` 至少需要同机制正例、干净对照和反例；
`unconditional-core` 还必须包含跨路线正例和 holdout。仅含
`original-failure` 的请求只能保持项目专用。

## 5. `qa/change-response.json`

`schema_version` 固定为 `2`。生成侧逐条回应变更请求：

- `accepted`：提供责任层、变更文件/规则、保留项、新媒体 SHA-256、回归
  结果和 unresolved；
- `rejected`：说明合同、权利、成本或证据理由；
- `deferred`：说明等待条件和责任人。

每个 accepted 请求必须覆盖其 required regression cases。`project revision`
和 `generation Skill version` 分开记录：

- 只改当前项目媒体时，Generation Skill 版本不变；
- 只有生成 Skill 的规则或实现变化时，才允许更新 Skill 版本；
- 新版 Skill 版本必须高于旧版。

## 6. `qa/review-verification.json`

`schema_version` 固定为 `2`。由新的独立审阅轮次生成。

必需内容：

- `verification_review_id`、`prior_review_id` 和 `project_id`；
- 审阅 Skill 与独立 reviewer；
- accepted `change_request_ids`；
- 原始媒体哈希和变更后媒体哈希；
- 新媒体的相对路径与哈希；
- 每个 required regression case 的结果；
- 最终状态：`validated`、`rejected`、`provisional`、
  `insufficient_evidence` 或 `not_applicable`。

没有 accepted change 时使用 `not_applicable`。存在 accepted change 时，
所有 required regression results 必须为 `pass`，并且审阅者独立于生产者。

## 7. 规则与记忆

持久记忆不放在可发布 Skill 内。默认目录：

```text
$VIDEO_REVIEW_MEMORY_DIR
  或
$CODEX_HOME/video-review-memory/
    issue-ledger.jsonl
    rule-registry.jsonl
```

首次安装：

```bash
python scripts/init_memory.py
```

记忆只保存 `project_id`、项目内相对路径、哈希、短观察和决策。不得保存
用户名、盘符、临时绝对路径、凭据或复制媒体。

规则分为：

- `process-invariant`：流程硬约束，可直接强制执行；
- `quality-heuristic`：视觉、物理或版式判断，必须回归后验证。

超出项目范围的 `quality-heuristic` 无论标为 `active` 还是 `validated`，都必须
有证据案例和结构化回归。`conditional-core`
至少需要两个证据案例；`unconditional-core` 还必须具备跨路线、负例、干净
对照和 holdout。

## 8. 验证

首轮 handoff：

```bash
python scripts/validate_contracts.py \
  --handoff <project>/qa/review-handoff.json
```

完整闭环：

```bash
python scripts/validate_contracts.py \
  --handoff <project>/qa/review-handoff.json \
  --result <project>/qa/review-result.json \
  --response <project>/qa/change-response.json \
  --verification <project>/qa/review-verification.json \
  --require-complete
```

记忆：

```bash
python scripts/validate_memory.py
```

## 9. 停止条件

- handoff、媒体、源文件或证据哈希不一致；
- 审阅 Skill 版本低于 handoff 最低版本；
- reviewer 不独立或身份缺失；
- 已确认问题没有证据；
- accepted change 没有新媒体字节；
- 新字节没有独立 verification；
- 规则升级缺少对应 scope 的回归角色；
- 同一原因连续三轮未修复；
- 通过 best-of-N、隐藏失败结果、挑选有利帧或移动失败层来伪造改善。
