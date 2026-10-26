# 公开参考与取舍

检索日期：`2026-10-26`。下列项目只用于研究流程和设计模式；本 Skill
不复制其代码或媒体。

## 直接相关的视频审阅 Skill

### oratis/video-review-skill

- https://github.com/oratis/video-review-skill
- 直接 SKILL.md 与 review rubric。
- 采用：ffmpeg/ffprobe、contact sheet、原生关键帧、时间锚点、
  P0/P1/P2、音频测量诚实边界、干净视频不制造问题。
- 不采用：把“给出具体修复”强制为本 Skill 的每次输出；本项目支持
  problem-only 模式。

### krusemediallc/video-editor-agent

- https://github.com/krusemediallc/video-editor-agent
- video-qa、四层 QA 和 review canvas。
- 采用：便宜到昂贵的分层检查、稳定 manifest anchor、测量最终文件、
  覆盖状态显式记录、已知干净 canary、第二模型审计、最多三轮修复。
- 采用审查画布思想：帧精确注释、版本、回复、证据、状态和从 notes 重建
  下一版；当前 Skill 用持久 JSONL 轻量实现，不绑定外部服务。

### runesleo/claude-video-kit

- https://github.com/runesleo/claude-video-kit
- review gate 与 pre-render review。
- 采用：预渲染与最终渲染双层门禁、独立 reviewer、最终字节哈希绑定、
  真实手机尺寸可读性、脚本变更使 receipt 失效。
- 不采用：固定五项设计原则作为唯一审美标准。

### zenstory-ai/drama-skills

- https://github.com/zenstory-ai/drama-skills
- short-drama-review、content-quality judge prompt 与 rubric。
- 采用：审查与修改分离、按范围加载、盲评、A/B 交换、development 与
  holdout、负对照、过拟合标签、预先固定阈值与 replicate。
- 不采用：把剧本文本的分数和机制直接当作视频质量分。

### talsiach/take-one

- https://github.com/talsiach/take-one
- 生成、fresh reviewer、review room 和 notes-to-next-take。
- 采用：审阅者与制作者分离、每条 note 可追踪、notes 作为下一版输入、
  三轮上限、把用户的持续偏好沉淀为 taste/记忆。
- 不采用：将具体风格选择设为全局规则。

## 视频生成评测基准

### VBench / VBench++ / VBench-2.0

- https://github.com/Vchitect/VBench
- VBench 明确把 video generation quality 拆为多维度，并提供自动评测、
  prompt suite 与 human preference alignment。
- 采用为扫描清单：主体一致性、背景一致性、时序闪烁、运动平滑、
  动态程度、美学、图像质量、对象数量/类别、动作、空间关系、风格。
- VBench-2.0 的 intrinsic faithfulness 方向支持本 Skill 把物理、常识、
  人体动作和创作组合从“画质”中分开。
- 不直接使用其模型排行榜分数替代项目审阅，因为项目意图、平台和创意
  合同高于通用模型分数。

## 综合结论

公开实现共同强调：

1. 最终文件证据；
2. 先便宜后昂贵；
3. 稳定锚点和可复现检查；
4. 独立审阅和有意选择校准；
5. 干净对照、反例和 holdout；
6. 反馈必须回到下一版，并在限次内验证；
7. 单一模型或单一审阅的次数不能代替人类责任与项目合同。

目前检索未发现一个公开 Skill 同时完整实现
“生成 Skill -> 审阅 Skill -> 结构化变更请求 -> 生成侧修复 ->
审阅侧回归 -> 规则状态升级”的双 Skill 闭环。本 Skill 的协同契约是在
上述模式基础上新增的组合设计。
