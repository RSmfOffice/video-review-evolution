# 生成 Skill 与审阅 Skill 协同契约

## 1. 角色

- `video-production-director`：生成 Skill，拥有 brief、镜头、资产、生成、
  合成、修复、生产证据和生成侧回归。
- `video-review-evolution`：审阅 Skill，拥有独立观察、问题判定、稳定锚点、
  变更请求、审阅记忆和审阅侧回归。
- 用户/责任方：决定项目意图、审美接受、预算、权利和最终发布。

生成 Skill 不能自证通过；审阅 Skill 不能凭一句意见直接改写生产规则。

## 2. 闭环

```text
生成预检与合同
  -> 最终媒体 + review-handoff
  -> 审阅首轮问题
  -> 用户校准
  -> generation_change_request
  -> 生成侧最小修复
  -> change-response + 新媒体
  -> 原失败 / 干净对照 / 反例回归
  -> issue 与 rule 状态更新
  -> 下一轮生成读取已验证规则
```

一轮最多三次同类修复。第三次仍失败时停止自动循环，升级为路线、资产、
模型或创意方向决策。

## 3. `qa/review-handoff.json`

生成侧在进入 review 前生成，绑定当前最终文件和生成上下文。

```json
{
  "schema_version": 1,
  "project_id": "example",
  "created_at": "2026-10-26T12:00:00+08:00",
  "generation_skill": {
    "name": "video-production-director",
    "version": "0.4.0",
    "path": "C:/.../video-production-director",
    "sha256": "optional skill bundle hash"
  },
  "review_skill_min_version": "0.2.0",
  "review_scope": [
    "technical",
    "content",
    "text",
    "visual",
    "motion",
    "editorial",
    "audio_visual",
    "rights"
  ],
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
    "brief": "brief.md",
    "project": "project.json",
    "shots": "shots.json",
    "timeline": "timeline.json",
    "qa_report": "qa-report.json"
  },
  "required_observations": [
    {
      "id": "REQ-MAIN",
      "observable": "The required subject remains identifiable.",
      "acceptance_ids": ["A1"]
    }
  ],
  "intentional_choices": [
    {
      "id": "INT-01",
      "relationship": "text-graphic-overlap",
      "declared": "The accent line intentionally crosses the title as a designed strike-through.",
      "allowed_effects": ["partial glyph occlusion"],
      "must_preserve": ["exact text", "readable recognition"],
      "evidence": "creative-bible.md#title-treatment"
    }
  ],
  "anchors": [
    {
      "id": "SHOT-S01",
      "kind": "shot",
      "start_sec": 0.0,
      "end_sec": 10.0
    },
    {
      "id": "TXT-TITLE",
      "kind": "graphic",
      "start_sec": 0.35,
      "end_sec": 9.7
    }
  ],
  "control_context": {
    "route": "programmatic",
    "model": "local/pillow-ffmpeg",
    "prompt_or_source": "src/render.py",
    "references": []
  },
  "known_clean_controls": [],
  "known_failure_controls": [],
  "excluded_checks": [],
  "notes": ""
}
```

### 约束

- `media.sha256` 必须是最终文件哈希，不是 animatic 或预览。
- `intentional_choices` 必须写清允许效果和必须保留项。没有声明时，审阅者
  可以提出疑问，但不能把审美偏好自动写成缺陷。
- `anchors` 使用稳定 ID；时间码可在重新剪辑后变化，但 ID 应保持。
- `excluded_checks` 只表示用户明确不要求或环境不支持，不表示通过。

## 4. `qa/review-result.json`

审阅 Skill 生成，绑定同一媒体和两个 Skill 版本。

```json
{
  "schema_version": 1,
  "review_id": "REV-...",
  "project_id": "example",
  "review_skill": {
    "version": "0.2.0"
  },
  "generation_skill": {
    "version": "0.4.0"
  },
  "media_sha256": "64-hex",
  "coverage": {
    "technical": "pass",
    "content": "pass",
    "text": "fail",
    "visual": "pass",
    "motion": "not_checked",
    "editorial": "warn",
    "audio_visual": "skipped",
    "rights": "pass"
  },
  "verdict": "revise",
  "issues": [
    {
      "issue_id": "ISS-...",
      "anchor": "TXT-TITLE",
      "start_sec": 1.4,
      "end_sec": 9.3,
      "observed": "A thin accent line crosses the lower glyph strokes.",
      "expected_source": "Title legibility and no accidental graphic collision.",
      "intent_judgment": "accidental-harmful",
      "verdict": "confirmed",
      "severity": "major",
      "confidence": "high",
      "evidence": []
    }
  ],
  "generation_change_requests": [
    {
      "id": "GCR-001",
      "issue_ids": ["ISS-..."],
      "target_layer": "layout",
      "relationship": "text-graphic-overlap",
      "required_observable_change": "Separate the accent line from all title glyph bounds.",
      "must_preserve": ["title content", "overall hierarchy"],
      "positive_tests": ["original case"],
      "negative_tests": ["intentional strike-through reference"],
      "suggested_scope": "project-specific"
    }
  ],
  "residual_risks": [],
  "limitations": []
}
```

### 约束

- 覆盖状态只使用 `pass`、`warn`、`fail`、`not_checked`、`skipped`。
- 未检查的覆盖不能参与 `pass`。
- `not_checked` 和 `skipped` 必须说明原因。
- 审阅者发现的问题与建议修复分开；不得把未经验证的建议写成现有结论。
- 由低分辨率代理产生的问题不得标为 high confidence，除非原生证据确认。

## 5. `qa/change-response.json`

生成 Skill 在收到变更请求后生成：

```json
{
  "schema_version": 1,
  "review_id": "REV-...",
  "responses": [
    {
      "change_request_id": "GCR-001",
      "decision": "accepted",
      "responsible_layer": "layout",
      "files_or_rules_changed": ["src/..."],
      "preserved": ["title content"],
      "new_media_sha256": "64-hex",
      "regression": {
        "original_case": "pass",
        "known_clean_control": "pass",
        "negative_examples": ["intentional strike-through: pass"],
        "unresolved": []
      }
    }
  ],
  "new_skill_version": "0.4.1"
}
```

拒绝请求时需要写 `decision: "rejected"` 和基于合同、权利、成本或证据的理由。

## 6. 规则与生成 Skill 的双向更新

审阅侧可以提出：

- 生成合同缺失；
- 分镜/动作设计风险；
- 控制路线或模型适配问题；
- 资产、关键帧、深度/遮罩/合成问题；
- QA 方法和证据要求；
- 提示词结构问题。

生成侧必须：

1. 找到最便宜、最靠上游的责任层；
2. 一次只改一个因果变量；
3. 保留已批准的主体、动作和风格；
4. 更新 `new_media_sha256`；
5. 提供回归结果和残余风险。

审阅侧必须：

1. 先复审原失败；
2. 再检查干净对照和反例；
3. 重新比较全部指标；
4. 通过后再把规则标记为 `validated`；
5. 未通过时保持 `candidate` 或标记 `rejected`。

## 7. 有意选择与误报

审阅者必须读取 `intentional_choices`，但不能盲信：

- 设计声明与最终画面明显冲突时，记录冲突；
- 声明可以解释重叠、黑场、静音、超现实物理和非写实风格；
- 声明不能保护错误文字、误导性事实、版权、安全或平台硬性要求；
- 未声明不等于禁止，尤其是没有合同的新类型探索；
- 对意图不明确的效果使用 `intentional-ambiguous`，不直接判错。

## 8. 已知干净对照

每个成熟规则至少有一个已知干净样片作为 false-positive canary：

- 轨道周期运动不应触发滚动接触规则；
- 有意多层辉光不应触发透明接缝规则；
- 无文字视频不触发文字版式规则；
- 无接触对象不触发支撑规则；
- 设计性黑场和静音不触发技术阻断。

干净样片必须有自己的哈希和当前 Skill 版本。

## 9. 工作停止条件

- 媒体或 handoff 哈希不一致；
- 必需输出无法访问；
- 原失败、对照或反例回归不完整；
- 同一原因修复三次仍失败；
- 评分提高依赖 best-of-N、挑选有利帧或隐藏失败输出；
- 用户偏好与硬要求冲突且无责任人决定；
- 规则升级会误伤明确合法的艺术风格。

遇到停止条件时保持 provisional，不要宣称已验证。
