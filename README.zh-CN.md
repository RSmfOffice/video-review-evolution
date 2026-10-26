# Video Review Evolution

[English](README.md) | **简体中文**

一个以证据为先的 Codex Skill，用于独立审阅视频成片、跨版本追踪问题，并验证
生成侧修复是否真的带来净收益。

当前版本：**0.3.0**

本 Skill 是双 Skill 工作流中的独立审阅侧，配套生成 Skill：
[video-production-director](https://github.com/RSmfOffice/Agent-Skill-for-evidence-gated-AI-video-production.)。

## 强制能力

- 锁定被审媒体和源文件的精确哈希。
- 使用稳定镜头、图形和事件锚点。
- 逐项记录审阅覆盖，不能合并成一个模糊的 pass。
- 问题必须包含时间范围、审阅者身份和可验证证据。
- 区分项目、路线、模型和跨路线规则。
- 为原始失败、正例、反例、干净对照、跨路线和 holdout 建立结构化回归。
- 变更后的新字节必须经过第二次独立复核，生成侧不能自证修复。
- 持续记忆存放在可发布 Skill 之外，避免更新覆盖和隐私泄漏。

## 安装

```bash
git clone git@github.com:RSmfOffice/video-review-evolution.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/video-review-evolution"
```

首次安装时初始化运行记忆：

```bash
python scripts/init_memory.py
```

默认记忆目录：

```text
$VIDEO_REVIEW_MEMORY_DIR
或
$CODEX_HOME/video-review-memory/
```

## 验证

```bash
python scripts/validate_memory.py

python scripts/validate_contracts.py \
  --handoff <project>/qa/review-handoff.json \
  --result <project>/qa/review-result.json \
  --response <project>/qa/change-response.json \
  --verification <project>/qa/review-verification.json \
  --require-complete
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 版本历史

- `v0.3.0`：schema v2 审阅契约、结构化回归、变更后独立验证、可移植记忆。
- `v0.2.0`：早期审阅交接架构的历史归档。公开标签不包含本地私有审阅账本。

## 许可

MIT，详见 [LICENSE](LICENSE)。
