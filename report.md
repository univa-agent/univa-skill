# UniVA-SKILL 功能实现报告

> 第三轮修改稿。本文基于当前仓库实现、已有功能报告素材和指导意见整理，重点从“系统实现说明”调整为“调研反查、功能刻画、技术剖析、场景展示”的报告结构。  
> 当前仓库根目录 `report.md` 原文件为空，本稿主要吸收 `allmd/univa_function_report_abcd.md`、`allmd/univa_skills_mcp_analysis.md`、`allmd/three_layer_skill_framework_refactor.md`、`skills/INDEX.md`、`pipeline_defs/*.yaml` 和 `README.zh-CN.md` 中已有内容。

## A. 前期调研

### A.1 OpenMontage 调研

#### A.1.1 项目定位

OpenMontage 是一个面向智能体的视频生产项目。它的基本思路不是提供一个单独的视频生成接口，而是把视频制作拆成 pipeline、stage director skill、tool、review 和 checkpoint。用户提出视频需求后，AI coding agent 读取项目中的说明文件和流水线配置，按阶段完成调研、方案、脚本、场景计划、素材生成、剪辑和最终合成。

这一点和 UniVA-SKILL 的方向比较接近：二者都不是简单调用一个模型，而是把“创作过程”作为系统的一部分来设计。不同之处在于，UniVA-SKILL 当前更聚焦在图像、视频、音频、编辑、理解等 MCP 工具的统一调用，以及 Codex/Claude Code/后端/Web 前端共用同一套 skill 与 review gate。

#### A.1.2 OpenMontage 功能清单

根据公开 README，OpenMontage 把视频生产拆成多个可选 pipeline。对 UniVA-SKILL 来说，这些 pipeline 可以作为反查表，用来判断我们已经覆盖了哪些视频类型，哪些还只是工具层具备但没有形成完整展示。

| OpenMontage pipeline | 主要产出 | 对 UniVA-SKILL 的参考意义 |
|---|---|---|
| Animated Explainer | 调研、旁白、视觉、音乐组合的解释型视频 | 对应 UniVA 的 PPT 式演示视频和科普讲解场景 |
| Animation | 动态图形、动态排版、动画序列 | 对应动漫/漫剧、科幻动漫、国潮等 theme 场景 |
| Avatar Spokesperson | 虚拟人或讲述人视频 | UniVA 当前不是主展示方向，可作为后续扩展项 |
| Cinematic | 预告片、品牌片、情绪片 | 对应剧场故事、广告、旅行风光、汽车广告 |
| Clip Factory | 长视频切短视频、批量短视频 | UniVA 当前有理解和编辑能力，但还没有独立批量切条 pipeline |
| Documentary Montage | 从素材库检索真实视频并剪辑成 montage | UniVA 当前更偏生成式，素材检索与授权链路需要补 |
| Hybrid | 源素材加 AI 生成辅助画面 | 对应“上传视频 -> 理解 -> 补镜头 -> 合并”的复合流程 |
| Localization & Dub | 翻译、字幕、配音 | UniVA 有字幕包装和 speech/audio 工具，翻译与对口型还需补齐 |
| Podcast Repurpose | 播客内容转短视频或 audiogram | UniVA 有音频工具，但缺少播客再创作 pipeline |
| Screen Demo | 软件录屏、教程、产品演示 | 对应安装流程录屏和 Web 编辑器录屏展示 |
| Talking Head | 讲话人、访谈、演示类视频 | UniVA 当前不作为主能力展示 |

#### A.1.3 对报告写法的启发

OpenMontage README 的主要特点是先写“能做什么”，再写“怎么实现”。这对当前报告的修改有直接参考意义：

1. 把功能清单放在前面，先让用户和评审知道系统支持哪些任务。
2. 把 pipeline、skill、tool、artifact 放到技术剖析部分，不在首页零散展开。
3. 把 demonstration 单独成章，用真实成片、录屏、链接作为证据。
4. 把缺口明确写出来，避免把工具层能力写成已经完整产品化的能力。

### A.2 Motion / Remotion 调研

#### A.2.1 Motion 的定位

Motion 是面向 React、JavaScript、Vue 的 Web 动画库，主要用于页面动效、手势、滚动动画、布局动画、弹簧动画和交互动画。它适合前端界面，不适合作为视频生成、视频编辑或多媒体 pipeline 的核心能力来介绍。

因此，Motion 在本文中的位置应当放在前期调研中，用来说明“前端动效库”和“媒体生产系统”之间的边界。UniVA-SKILL 的正文不应把 Motion 作为主功能展开。

#### A.2.2 Remotion 的定位

Remotion 是用 React 程序化生成视频和动态图形的框架。它可以通过代码渲染 MP4，也适合做字幕、标题卡、数据卡、品牌角标、CTA、进度条等确定性图层。

在 UniVA-SKILL 当前实现中，Remotion 的定位是“最终包装层”，不是视频生成模型，也不是编辑模型。它在生成计划批准之后使用，用来做可控的字幕和图层包装。当 Remotion 在本地环境无法运行时，系统可以退回到 FFmpeg ASS 字幕烧录。

#### A.2.3 为什么 Remotion 不应散落正文

原始材料中 Remotion、前端、后端、agents、pipeline 等内容容易混在一起。按指导意见，Remotion 应集中写在 A.2 和 C.4 中：

1. A.2 写调研结论：Remotion 是程序化视频框架。
2. C.4 写实现位置：UniVA 把 Remotion 当最终包装层。
3. B 模块只写系统支持什么功能，不把 Remotion 写成一个独立生成模态。

### A.3 Skill 机制基础调研

#### A.3.1 Agent 自动读取机制

UniVA-SKILL 的运行前提是外部 agent 能够读取仓库中的本地说明文件。当前仓库的入口文件包括：

- `AGENTS.md`：外部智能体进入仓库后的总规则。
- `skills/INDEX.md`：skill、pipeline、MCP tool 的总索引。
- `skills/agent-integrations/codex-univa-video-ops/SKILL.md`：Codex 使用 UniVA 媒体能力的接入说明。
- `skills/agent-integrations/claude-code-univa-video-ops/SKILL.md`：Claude Code 使用 UniVA 媒体能力的接入说明。
- `skills/meta/media-review-gate.md`：所有媒体生成和编辑任务的审批规则。

#### A.3.2 Skill 装载方式

当前 skill 装载并不是把所有 Markdown 一次性塞给模型，而是按任务和工具选择相关内容：

1. 任务识别阶段读取 `skills/INDEX.md` 和 meta skill。
2. 生成、编辑、理解等任务按 pipeline 加载对应 director skill。
3. 工具调用前读取对应 core skill，把函数名、参数、输出和失败形态作为执行合同。
4. theme skill 只做质量增强，不改变工具合同和审批规则。

#### A.3.3 对 UniVA-SKILL 的调研结论

UniVA-SKILL 的文档应把 skill 写成“系统能力组织方式”，而不是只写成文件列表。评审真正关心的是：这些 skill 如何约束 agent，如何避免跳过审批，如何保证最终输出可追踪。

## B. 功能刻画

### B.1 原子功能

本节只描述系统支持的原子功能，不放运行日志，也不放 Codex 的确认信息。运行过程和 artifact 证据放到 C 和 D 中说明。

#### B.1.1 文生视频

文生视频是 UniVA-SKILL 的基础视频生成能力。用户输入文本需求后，系统先把需求拆成镜头计划、视觉描述、运动方式、时长、画幅、转场和声音策略，再通过视频生成工具生成片段。

当前实现入口包括：

- Core Skill：`skills/core/wavespeed-video-gen.md`
- 主要工具：`plan_video_shots`、`text2video_gen`、`merge2videos`
- Codex 直连入口：`scripts/codex_video_runner.py`
- 典型产物：`research_brief.json`、`shot_plan.json`、`storyboard_review.json`、`delivery_report.json`

适合展示的任务包括商品广告、故事短片、科技宣传片、风格化镜头和平台短视频。

#### B.1.2 文生图

文生图用于生成独立图片，也可以作为视频生成的上游素材。它可以生成海报、产品主视觉、角色设定图、关键帧、封面图和分镜参考图。

当前实现入口包括：

- Core Skill：`skills/core/wavespeed-image-gen.md`
- 主要工具：`text2image_generate`
- 扩展工具：`image2image_generate`、`sequential_image_gen`
- Pipeline：`media-atomic`

在复合流程中，文生图经常用于先稳定角色、产品或场景，再进入图生视频。

#### B.1.3 图生视频

图生视频把静态图片、首帧、产品图或角色图转为动态视频。它的价值在于让用户先确认视觉锚点，再生成运动画面，减少纯文本生成带来的不确定性。

当前实现入口包括：

- Core Skill：`skills/core/wavespeed-video-gen.md`
- 主要工具：`image2video_gen`、`frame2frame_video_gen`
- 相关 creative skill：`styleframe-direction`、`material-matching`、`asset-generation`

适合展示“产品图动起来”“角色设定变成短镜头”“海报转动态广告”“首尾帧生成过渡片段”等任务。

#### B.1.4 视频理解

视频理解用于分析上传视频或生成结果。系统可以提取内容、风格、镜头节奏、主体、背景、动作、质量问题和可复用提示词。

当前实现入口包括：

- Core Skill：`skills/core/video-understanding.md`
- 主要工具：`vision2text_gen`
- Pipeline：`video-understand`
- Codex 直连入口：`scripts/codex_video_task_runner.py --task understand`

该能力通常不单独作为最终卖点，而是服务于编辑、复刻风格、质量检查和前端素材理解。

#### B.1.5 视频编辑

视频编辑不是直接修改源文件，而是先分析源视频，再生成编辑提案，用户确认后才调用工具。当前实现覆盖：

| 编辑类型 | 当前状态 | 对应工具/实现 | 说明 |
|---|---|---|---|
| 风格迁移 | 已支持 | `style_transfer` | 适合把实拍、录屏或生成视频转为水彩、动漫、科技风等 |
| 局部重绘 | 已支持 | `repainting` | 可用于局部区域、物体或背景修改 |
| 深度修改 | 已支持 | `depth_modify` | 用于空间结构、深度相关画面修改 |
| 姿态参考 | 已支持 | `pose_reference` | 用参考姿态或动作约束生成结果 |
| 换背景 | 间接支持 | `repainting` | 需要在提案中写清保留主体和背景替换规则 |
| 换物体 | 间接支持 | `repainting` | 适合局部替换，但需要 demo 验证稳定性 |
| 换角色 | 间接支持 | `repainting`、`pose_reference` | 需要角色一致性约束和对比 demo |
| 抠图 | 待补齐/需验证 | `video_referring_segmentation` | 当前有指代分割能力，但还需形成透明主体或 mask 输出流程 |

#### B.1.6 片段拼接与首尾帧过渡

片段拼接由 `merge2videos` 支持，转场和合并规则由 `skills/core/ffmpeg-merge.md` 约束。当前支持硬切、crossfade、fadeblack、fadewhite 等常见转场，也可以通过中文别名表达“淡入淡出”“黑场”“白场”等。

首尾帧过渡视频的实现思路是：从前一段视频抽取尾帧，从后一段视频抽取首帧，再用 `frame2frame_video_gen` 生成中间过渡片段，最后三段合并。当前工具链具备实现条件，建议单独做一个 demo 证明。

#### B.1.7 音频、语音与混音

音频能力由 `skills/core/audio-gen.md` 和 `univa/mcp_tools/audio_gen.py` 支撑。系统可规划并生成 BGM、环境声、音效、转场音，也可在用户明确要求时生成旁白、口播或角色语音。

默认策略是：优先保留视频生成模型返回的音频；如果没有音频，再调用专门的音频工具；如果专门音频工具失败，则使用 FFmpeg fallback 并在交付报告中记录限制。

### B.2 复合功能

UniVA-SKILL 的重点是把原子功能组合成完整工作流。下面列出适合正文展示的 5 个代表性组合。

#### B.2.1 文本到广告成片

流程为：文本需求 -> 分镜计划 -> 文生视频 -> 多段拼接 -> BGM/SFX -> 字幕/CTA 包装 -> 交付报告。

该流程适合展示电车广告、饮料广告、手机广告和品牌短片。已有 `docs/assets/readme/ev-ad-captioned.mp4` 可以作为基础示例。

#### B.2.2 文本到图像再到视频

流程为：文本需求 -> 文生图生成主视觉或角色图 -> 图生视频扩展运动 -> 补充文生视频镜头 -> 合并成片。

该流程适合展示“先确定视觉，再生成视频”的稳定创作方式。

#### B.2.3 上传视频后编辑增强

流程为：上传视频 -> 视频理解 -> 编辑提案 -> 用户确认 -> 风格迁移/局部重绘/换背景 -> 结果复核。

该流程适合展示 UniVA-SKILL 的 editing gate，而不是把原视频直接交给工具修改。

#### B.2.4 两段视频生成过渡并合并

流程为：视频 A -> 抽取尾帧；视频 B -> 抽取首帧；首尾帧生成过渡视频 -> A + 过渡 + B 合并。

该流程能直接体现“首尾帧插入过渡视频”的能力，建议放入演示部分。

#### B.2.5 PPT 式演示视频

流程为：论文/项目要点 -> 分镜 -> 标题卡/图表/字幕 -> 旁白或 BGM -> Remotion 包装 -> 成片。

该流程适合对标 OmniScientist/HuggingFace 页面中的动态 demo 形式，用于论文展示、项目介绍和课程演示。

### B.3 功能对照表

| 功能类别 | OpenMontage/Motion/Remotion 参考 | UniVA-SKILL 当前实现 | 当前判断 |
|---|---|---|---|
| Agent 驱动视频 pipeline | OpenMontage 以 pipeline 组织视频生产 | `pipeline_defs/*` + `skills/pipelines/*` | 已支持 |
| 文生视频 | OpenMontage 视频生产基础能力 | `text2video_gen`、`plan_video_shots` | 已支持 |
| 文生图 | OpenMontage 可生成支撑素材 | `text2image_generate` | 已支持 |
| 图生视频 | 生成式视频和素材驱动视频 | `image2video_gen`、`frame2frame_video_gen` | 已支持 |
| 视频理解 | 参考视频分析、素材理解 | `vision2text_gen`、`video-understand` | 已支持 |
| 视频编辑 | OpenMontage 支持多类后期流程 | `style_transfer`、`repainting`、`depth_modify`、`pose_reference` | 已支持基础编辑 |
| 抠图/分割 | 素材级编辑常见需求 | `video_referring_segmentation` | 需补完整展示 |
| 换角色/换物体/换背景 | 编辑类常见细分 | `repainting` + 编辑提案 | 间接支持，需 demo 验证 |
| 多段拼接 | OpenMontage edit/compose 阶段 | `merge2videos` | 已支持 |
| 首尾帧过渡视频 | 视频间自然衔接需求 | `frame2frame_video_gen` + `merge2videos` | 工具链具备，需展示 |
| 字幕/标题/CTA | Remotion 强项 | `remotion_compose_video`、FFmpeg fallback | 已支持 |
| 前端动效 | Motion 强项 | Web 前端可使用相关思路 | 非核心能力 |
| PPT 式动态演示 | Remotion/解释型视频可参考 | Remotion 包装 + story-video | 需补展示 |
| 长视频批量切条 | OpenMontage Clip Factory | 当前没有独立 pipeline | 待补 |
| 纪录片素材检索 montage | OpenMontage Documentary Montage | 当前没有检索公开素材库 pipeline | 待补 |
| 多语言本地化/配音 | OpenMontage Localization & Dub | `speech_gen` + 字幕基础能力 | 待完善 |

## C. 技术剖析

### C.1 Skill 设计规范

#### C.1.1 工具合同优先

UniVA-SKILL 中，core skill 是 MCP 工具的执行合同。普通任务执行时，应以 `skills/core/*.md` 中写明的函数名、参数、默认值、返回字段、输出路径和失败形态为准。只有在维护工具、调试合同不一致或 core skill 缺失时，才需要直接阅读 `univa/mcp_tools/*.py`。

这一设计把“工具怎么调”从代码实现中抽出来，让 Codex、Claude Code、后端 agent 和 Web 前端都能按同一套说明调用工具。

#### C.1.2 生成前必须可审查

所有会生成或修改媒体的任务都要先产出计划或提案，再进入人工确认。视频生成对应 `shot_plan.json`、`storyboard_validation.json`、`storyboard_review.json`；图片、音频和轻量媒体任务对应 `media_plan.json`、`media_plan_validation.json`、`media_plan_review.json`；视频编辑对应 `edit_proposal.json` 和 `edit_proposal_review.json`。

确认通过后，工具调用必须使用已批准版本中的 exact prompt、源路径、时长、画幅、音频策略和参数，不能再临时改写。

#### C.1.3 Artifact 作为审计记录

每次生成或编辑都要能回看以下内容：

1. 加载了哪些 skill。
2. 计划是如何形成的。
3. 用户批准的是哪个版本。
4. 实际调用了哪个 MCP 工具。
5. 输出文件是否存在、是否可读、是否写入交付报告。

因此，`skill_context.json`、`shot_plan.json`、`storyboard_review.json`、`generation_handoff.json`、`clip_results.json`、`delivery_report.json` 是 UniVA-SKILL 报告中应该重点展示的证据链。

### C.2 具体 Skill 设计

#### C.2.1 Core Skills

Core Skills 约束原子工具调用：

- `wavespeed-video-gen`：文生视频、图生视频、帧间视频、故事视频、视频续写、视频合并。
- `wavespeed-image-gen`：文生图、图生图、序列图。
- `video-editing`：深度修改、风格迁移、局部重绘、姿态参考。
- `video-understanding`：图片/视频理解。
- `video-tracking`：文本指代分割。
- `audio-gen`：音频、语音、音频计划、混音。
- `ffmpeg-merge`：视频合并、转场、音频处理。
- `remotion-compose`：字幕、标题、CTA、品牌图层等最终包装。
- `prompt-validator`：生成前 prompt 完整性和矛盾检查。

#### C.2.2 Creative Skills

Creative Skills 负责把用户的模糊需求变成可执行创作方案。当前包括 brief、文案、风格帧、镜头规划、能量曲线、时长、素材匹配、转场声音字幕、角色一致性和创意质量检查等模块。

这部分不直接调用工具，而是帮助计划阶段形成更稳定的镜头、prompt 和包装策略。

#### C.2.3 Meta Skills

Meta Skills 负责跨任务控制，包括：

- 规划和执行协议：`plan-agent-protocol`、`act-agent-protocol`
- 审批和暂停：`media-review-gate`、`checkpoint-protocol`、`pause-forhelp`
- 质量控制：`reviewer`、`quality-gate`
- 任务路由：`generate-pipeline`、`edit-pipeline`、`understand-pipeline`、`chat-router`
- 输出与前端：`output-formatter`、`frontend-editor`
- 用户偏好：`user-maker`、`user-creator`、`user-preference-manager`

#### C.2.4 Pipeline Skills

Pipeline director skill 对应 `pipeline_defs/*.yaml` 中的阶段。当前主要 pipeline 包括：

| Pipeline | 作用 | 典型阶段 |
|---|---|---|
| `media-atomic` | 单图片、单音频、图片编辑等轻量媒体任务 | analyze、proposal、confirm、execute、validate |
| `story-video` | 多镜头故事视频生成 | idea、script、scene_plan、assets、edit、compose |
| `creative-proposal` | 先给多个创意方案，再确认生成 | proposal、selection、storyboard、confirm、generate、deliver |
| `video-edit` | 视频编辑与多轮修改 | analyze、proposal、execute、review |
| `video-understand` | 图片/视频理解 | analyze、present、refine |
| `master` | 总路由 | analyze、resolve、execute |

#### C.2.5 Theme Skills

Theme Skills 是质量增强层。当前仓库包含广告、汽车、漫画、国潮、科幻动漫、科普、旅行、美妆、教育、医疗健康、金融商业、食品烹饪、游戏电竞等主题。

Theme skill 只增强 prompt、视觉、分镜、内容结构和声音建议，不改变审批规则、工具合同和用户明确约束。

### C.3 Prompt 与 Pipeline 总体划分

Prompt、Pipeline 和 Tool 的职责应分开写：

1. Prompt 层：把用户需求写成模型能执行的视觉、运动、镜头、风格和声音描述。
2. Pipeline 层：决定任务按哪些阶段推进，什么时候暂停，什么时候需要用户确认。
3. Tool 层：调用真实 MCP 工具完成生成、编辑、理解、合并或音频处理。
4. Artifact 层：保存计划、审批、执行结果、失败原因和最终交付路径。

这种划分能解释 UniVA-SKILL 和单次模型调用的区别：它不是“输入一句话直接出片”，而是把媒体生产过程拆成可检查、可恢复、可复用的步骤。

### C.4 系统实现层

#### C.4.1 外部智能体执行路径

Codex 驱动视频生成时，推荐使用 `scripts/codex_video_runner.py`。它会读取仓库 skill，生成研究简报和分镜计划，写出 `shot_plan.json` 与 `storyboard_review.json`，然后停在等待审批状态。用户批准后，再用 `--approved-plan` 执行生成。

Codex 驱动视频理解或编辑时，推荐使用 `scripts/codex_video_task_runner.py --task understand|edit`。理解任务直接调用 `vision2text_gen` 并写结构化报告；编辑任务先写 `edit_proposal.json` 和 review artifact，批准后才执行修改。

#### C.4.2 后端与前端路径

后端入口是 `univa/univa_server.py`，核心执行逻辑位于 `univa/univa_agent.py`、`univa/utils/skill_loader.py` 和 `univa/utils/pipeline_orchestrator.py`。前端位于 `apps/web`，提供项目素材库、时间线、上传、AI Chat 和生成结果自动导入。

正文中不建议展开大量前端截图。前端截图可放到附录，用于证明 Web 端已能把素材路径、项目上下文和时间线操作传给后端。

#### C.4.3 Remotion 包装层

Remotion 位于最终包装阶段。它适合做稳定可读的字幕、标题卡、lower-third、CTA、品牌角标、数据卡和进度条。当前实现中，Remotion 失败时可使用 FFmpeg ASS 字幕 fallback，这一点应作为“工程可靠性”写入报告，而不是把它写成新的生成模型。

#### C.4.4 输出目录与交付验证

生成结果主要写入 `results/`、`data/` 或 `univa/results/`。一次标准视频生成的目录通常包含：

```text
results/codex_direct_<timestamp>_<slug>/
├── skill_context.json
├── skill_context_full.json
├── research_brief.json
├── shot_plan.json
├── storyboard_validation.json
├── storyboard_review.json
├── generation_handoff.json
├── audio_handoff.json
├── remotion_handoff.json
├── clip_results.json
└── delivery_report.json
```

报告展示时，可以截取其中 `shot_plan.json`、`storyboard_review.json` 和 `delivery_report.json`，说明系统不是只给出最终视频，而是保留了完整过程。

## D. 展示与场景

### D.1 场景/视频类型

#### D.1.1 剧场故事

展示重点：多镜头叙事、人物/场景连续性、镜头节奏、字幕和转场。

建议插入：

- [视频占位：剧场故事最终成片，腾讯文档 Space 链接待补]
- [图片占位：该 demo 的 shot_plan 或 storyboard_review 截图]

#### D.1.2 动漫/漫剧

展示重点：漫画风角色动作、风格化运动、角色一致性和多镜头拼接。

当前可用素材参考：

- `docs/assets/readme/comic-action-short.mp4`
- `docs/assets/readme/anime-fight-captioned.mp4`
- `docs/assets/readme/anime-fight-poster.jpg`

建议插入：

- [视频占位：动漫/漫剧最终成片，腾讯文档 Space 链接待补]
- [视频占位：终端录屏，展示从 prompt 到审批再到生成的流程]

#### D.1.3 广告

展示重点：产品质感、卖点表达、字幕、CTA、品牌包装、音频。

当前可用素材参考：

- `docs/assets/readme/ev-ad-captioned.mp4`
- `docs/assets/readme/ev-ad-poster.jpg`
- `docs/assets/readme/desert-car.mp4`
- `docs/assets/readme/desert.png`

建议插入：

- [视频占位：可口可乐款广告成片，腾讯文档 Space 链接待补]
- [视频占位：电车广告终端录屏，腾讯文档 Space 链接待补]
- [图片占位：广告字幕/CTA 包装截图]

#### D.1.4 PPT 式演示视频

展示重点：项目介绍、论文要点、分节标题、图表、动态卡片、旁白或字幕。该类视频可以参考 OmniScientist/HuggingFace 页面动态 demo 的形式，但内容应替换成 UniVA-SKILL 自身的 skill 架构、功能流程和 demo 结果。

建议插入：

- [视频占位：PPT 式演示视频成片，腾讯文档 Space 链接待补]
- [图片占位：标题卡/架构卡/功能对照卡截图]

### D.2 复合功能 Demonstration

每个复合 demo 建议放两个视频：一个是干净录屏，一个是最终结果。录屏不需要把大文件塞进正文，统一上传腾讯文档 Space 后放超链接。

| Demo | 展示目标 | 录屏内容 | 最终结果 |
|---|---|---|---|
| Demo 1 文本到广告成片 | 展示文生视频、拼接、字幕、CTA、音频 | Codex 读取 skill、生成 storyboard、等待审批、批准后生成 | [视频占位：广告成片链接] |
| Demo 2 文本到图再到视频 | 展示文生图和图生视频串联 | 先生成主视觉，再用图生视频扩展运动 | [视频占位：图生视频成片链接] |
| Demo 3 上传视频后编辑 | 展示理解、提案、编辑 gate | 上传素材，分析内容，生成编辑提案，确认后执行 | [视频占位：编辑前后对比链接] |
| Demo 4 首尾帧过渡 | 展示两段视频自然衔接 | 抽尾帧和首帧，生成过渡片段，再合并 | [视频占位：过渡合成链接] |
| Demo 5 PPT 式演示 | 展示论文/项目讲解视频 | 输入报告要点，生成分镜、标题卡和字幕包装 | [视频占位：PPT 演示链接] |

### D.3 安装流程单独录屏

安装流程应单独录一次，避免和具体 demo 混在一起。建议录屏顺序如下：

1. 新环境打开终端，进入空目录。
2. 克隆 GitHub 仓库。
3. 安装 Python 依赖，确认 `python`、`ffmpeg`、`ffprobe` 可用。
4. 配置 `.env` 和 MCP server。
5. 运行 `scripts/preflight_media_runtime.py`。
6. 让 Codex 读取 `AGENTS.md` 和 `skills/INDEX.md`。
7. 执行一次低成本 review-only 任务，证明能生成 `shot_plan.json` 和 `storyboard_review.json`。

建议插入：

- [视频占位：新环境安装流程录屏，腾讯文档 Space 链接待补]
- [链接占位：GitHub 仓库地址]
- [链接占位：release 页面或安装说明页面]

### D.4 附录材料

正文不建议堆大量截图，但附录可以放证据图。建议准备：

1. [图片占位：Skill 三层架构图，Core / Creative / Meta / Pipeline / Theme]
2. [图片占位：`skills/INDEX.md` 目录截图]
3. [图片占位：`storyboard_review.json` 审批截图]
4. [图片占位：`delivery_report.json` 交付验证截图]
5. [图片占位：Web 编辑器素材库、时间线、AI Chat 截图]
6. [链接占位：腾讯文档 Space 视频合集]

## E. 当前修改相对原稿的主要变化

### E.1 结构变化

原始素材主要按 UniVA 当前实现展开，优点是信息完整，但容易把基础模态、技术实现、前端、Remotion、demo 混在一起。修改后按 A/B/C/D 组织：

1. A 写调研，用同类项目反查自己。
2. B 写功能，说明系统支持什么。
3. C 写技术，说明系统如何实现。
4. D 写展示，说明用哪些视频和录屏证明。

### E.2 内容变化

1. 增加 OpenMontage 功能清单和功能对照表。
2. 明确 Motion/Remotion 的位置，避免把它们写成 UniVA 的核心生成能力。
3. 把编辑能力拆成抠图、换角色、换物体、换背景、风格迁移、姿态参考、拼接、首尾帧过渡等细分项。
4. 把复合功能从泛泛描述改成 5 条可展示链路。
5. 在需要插入图片、视频和链接的位置做了占位。

### E.3 仍需补充

1. 需要补真实腾讯文档 Space 视频链接。
2. 需要补安装流程录屏。
3. 需要补可口可乐款广告、PPT 式演示视频、首尾帧过渡视频三个重点 demo。
4. 抠图、换角色、换物体、换背景需要用真实 demo 更新当前“间接支持/需验证”的状态。
5. 如用于论文正文，可再增加实验指标，例如成功率、人工修改轮次、生成耗时、失败恢复率、交付验证通过率。

## 参考资料

1. OpenMontage GitHub README：https://github.com/calesthio/OpenMontage
2. OpenMontage AGENT_GUIDE：https://github.com/calesthio/OpenMontage/blob/main/AGENT_GUIDE.md
3. Motion 官方文档：https://motion.dev/
4. Remotion 官方文档：https://www.remotion.dev/
5. UniVA-SKILL 当前仓库：`skills/INDEX.md`、`pipeline_defs/*.yaml`、`README.zh-CN.md`
