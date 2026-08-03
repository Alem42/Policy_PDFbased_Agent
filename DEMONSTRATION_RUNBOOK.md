# AI Policy Research Assistant — Demonstration Runbook

## 推荐演示流程

### Step 1 — 注册与登录

建议时间：30–45 秒

1. 打开登录页。
2. 简单说明系统区分普通用户与管理员。
3. 若注册功能已完善，快速注册并登录；否则使用预先准备的账号。
4. 后续进入 Configuration 时切换到管理员账号，强调只有管理员能修改全局配置。

讲解重点：

- 普通用户负责选择资料和研究问答。
- 管理员负责文档治理、模型、分类和 Web Search 配置。
- 注册密钥目前仍是占位设计，不在演示中声称已经实现真实管理员密钥验证。

### Step 2 — Document Library 与文件处理

#### 2.1 上传文件

1. 进入 `Documents / Library`。
2. 上传一份演示文件，只现场上传体积最小的 South Africa OCR 文件，其余三份提前上传。
3. 展示状态变化，例如 Uploaded、Parsed、OCR、Annotated、Ready。

讲解话术：

> Uploading is an ingestion pipeline, not just file storage. The backend extracts
> text, uses OCR when necessary, generates English metadata, splits the document
> into chunks, and creates embeddings for retrieval.

#### 2.2 展示文件详情

打开一份文档的 `Details`（展示几个就可以了）：

- 自动生成的英文 Title 和 Summary；
- Country / Region、Language、Year、Source organisation；
- 二级 Document categories；
- 原始文件名和文件来源；
- Page count、Chunk count；
- Chunk 原文、页码和 Metadata；
- Approved / Access level 等治理状态。

可选：展示中文文件：源文件和 Chunk 可以保留中文，但面向 Library 用户的 Metadata 被标准化为英文。例如中文文件标题显示为 `Artificial Intelligence Safety Governance Framework`。

#### 2.3 重复文件检测

再次上传刚才的一份完全相同的 PDF。

预期结果：系统基于文件 hash 识别重复文件，而不是创建第二份相同记录。

可补充说明：系统还有规范化正文 hash，用于发现“内容相同但 PDF 被重新保存”的副本。

#### 2.4 Filter Bar（可选）

快速演示：

- Country / Region = Australia；
- Language = Chinese；
- Year；
- Document category；
- Processing status / approval status。

说明 Filter Bar 用于寻找和管理资料；Chat 中的自然语言 Metadata Filter 则由 Agent 从问题中推断，两者用途不同。

### Step 3 — Configuration

建议时间：2–3 分钟。这里只讲“为什么可配置”，不要逐项修改全部设置。

#### 3.1 LLM & API keys

展示内容：

- 一个 Provider key 可以由该 Provider 下的多个模型/API 复用；
- 系统按 capability 区分 chat、embedding、rerank 等 endpoint；
- 系统没有预置的新服务可以在 `API endpoints` 中手动添加；
- key 只保存一次，界面不会重新显示完整值。

推荐话术：

> Provider credentials and model endpoints are separated. This lets an
> administrator reuse one provider key across chat, embedding and reranking,
> while still selecting different models for each capability.

#### 3.2 Document categories

展示二级分类结构：

```text
Parent category
└── Leaf category
```

说明：

- 管理员可以添加、删除和维护分类；
- 文档 Metadata 保存的是 leaf category；
- 自动 Metadata 生成会把模型输出映射到规范分类，避免同义标签无限增长。

#### 3.3 Embedding model

展示但不一定保存：

- 本地模型，例如 `BAAI/bge-small-en-v1.5`；
- API 模型，例如当前使用的 `embedding-3`；
- dimension 自动探测；
- batch size、chunk token budget、token counting；
- Evidence distance threshold。

需要说明：

- Embedding 用于召回语义相关的 Chunk；
- cosine distance 越小表示越相近；
- Local model 可使用精确 tokenizer，API 模型通常使用近似 token counting；
- 修改 model、dimension 或 chunk size 会影响已有向量，需要全库重新 Embedding；
- 系统会显示二次确认，避免误操作触发昂贵的重建任务；
- 当前阈值是使用演示 corpus 标定后的值，不是对所有模型通用的常数。

建议演示配置：

```text
provider: api
model: embedding-3
dimensions: 2048
chunk token budget: 600
distance metric: cosine
evidence distance threshold: 0.50
```

#### 3.4 Reranker

说明 Embedding 与 Reranker 的分工：

```text
Embedding：从大量 Chunk 中快速召回候选
Reranker：同时阅读问题和候选，重新排列相关性
Evidence Gate：综合 distance、reranker、文本覆盖和实体校验决定是否足以回答
```

推荐演示配置：

```text
enabled: true
provider: local
model: BAAI/bge-reranker-base
minimum score: -2.0
```

如果现场仍使用 Zhipu API Reranker，说明它在当前样本上的分数接近饱和，因此不能单独依赖 Reranker score，系统还会检查 distance 和明确命名的政策实体。

#### 3.5 Suggested follow-ups

简单展示：

- 可以整体开启/关闭；
- 可以控制回答后显示多少个建议问题；
- 每个候选问题会经过与正常问题一致的 Evidence Gate；
- 因此系统不会故意推荐当前文档无法回答的问题。

演示时只需要展示 `Enable follow-up suggestions` 和 `Suggestions shown`。Candidate pool、validation override、temperature 等高级项可以口头说明或在时间不足时跳过。

#### 3.6 Web search 与网页永久导入

说明两种不同能力：

1. **Live Web Search**：Chat 临时读取网页以回答时效性问题，不自动写入 Library。
2. **Import page**：把指定网页永久导入共享 Library，之后像普通文档一样进行 Metadata、Chunk 和 Embedding。

配置 Firecrawl provider 和 access key。Firecrawl 有免费额度，但正式演示前应确认额度可用。

永久导入示例：

```text
https://www.industry.gov.au/publications/national-ai-plan
```

预期结果：网页被检查重复、转换为可搜索内容并出现在 Library 中。页面不是简单保存为书签；其正文会进入与文档相同的检索流程。

关于确认行为：

- 管理员在 Configuration 页面点击 `Import page`，这个点击本身就是明确授权；
- 如果 Agent 在聊天中建议永久导入网页，必须先向用户显示确认步骤；
- 单纯 Live Web Search 不会永久写数据库，也不应表述为“已经导入”。

网页导入可能较慢，核心版演示可以只展示页面和已导入结果，不现场等待。

### Step 4 — Add to Chat

1. 在 Library 中选择四份演示文件。
2. 点击 `Add to Chat`。
3. 点击 `Go to Chat`。
4. 展示左侧 Sources，说明它们是当前 selected scope，不等于整个共享 Library。
5. 指出 `Answer purpose`、`Document Analysis / Open Discussion` 和可选模型。

### Step 5 — Chat / ReAct 场景

以下问题按功能组织。核心版建议展示 5.1、5.3、5.4、5.5 和 5.6；其余作为完整版或 History 回放。

#### 5.1 普通文档回答：引用与 Follow-up Questions

模式：`Policy Researcher` + `Document Analysis`

建议只选择 Australia 文档，或保留四份文件但明确问题对象。

```text
Under Australia's Policy for the Responsible Use of AI in Government v2.0,
which entities must apply it, when did it take effect, and what are three
mandatory governance requirements?
```

预期：

- 直接从 selected documents 找到足够证据；
- 回答 non-corporate Commonwealth entities、2025-12-15 和相应强制治理要求；
- 正文出现 `[N]` 引用；
- 点击 Sources/Citations 可查看标题、页码和原文 quote；
- 回答下方显示经过验证的 Suggested follow-ups；
- 顶部显示所用模型和 Token Usage。

这里顺便展示 Copy / Export answer（若时间允许）。

#### 5.2 跨语言、跨地区、跨文件比较（可选）

模式：`Policy Researcher` + `Document Analysis`

选择 Australia、Singapore、China 三份文件。

```text
Please compare who each of the three documents from Australia, Singapore,
and China ultimately holds accountable. Distinguish whether each source is a
mandatory government policy, a governance framework, or technical guidance,
and cite all three documents.
```

预期：

- 英文问题可以检索中文源文件；
- 最终回答引用三份不同地区的文件；
- 多地区比较必须覆盖每个明确要求的地区，不能只回答最容易匹配的一份；
- 可进一步用中文提问，展示回答语言跟随用户，而不是跟随文档语言。

#### 5.3 Metadata Filter 放宽

模式：`Policy Researcher` + `Document Analysis`

```text
Filter files published before 2025. What four areas does Singapore's 2026
Model AI Governance Framework for Agentic AI use to organise risk management?
```

预期路径：

```text
infer year <= 2024 and region = Singapore
→ no matching target document
→ relax metadata filter to the original selected scope
→ answer with a visible filter warning
```

讲解重点：Metadata Filter 是检索偏好，不是强制让系统无输出的开关。明确过滤条件没有结果时，系统放宽范围并警告用户，而不是抛出 tool error。

在 ReAct trace 中展示：

- Agent 选择了哪个工具；
- inferred filter；
- `filter_fallback=true`；
- Evidence 是否充分；
- 为什么停止或继续搜索。

#### 5.4 Selected Documents 不足后遍历 Library

模式：`Open Discussion`

只选择 South Africa OCR 文件，然后提问：

```text
What mandatory requirements does Australia's 2025 responsible AI government
policy set for accountable officials and AI use case impact assessments?
```

预期路径：

```text
selected documents insufficient
→ search full corpus
→ Australia document sufficient
→ answer
```

预期界面：

- ReAct trace 显示 `search_internal_documents` 后调用 `search_full_corpus`；
- 最终 citation 来自 Australia 文档，不来自 South Africa 文件；
- Evidence tier 显示 `full_corpus`；
- 页面显示 `From the wider library` 提示。

这一步是解释 ReAct 最直观的场景：Agent 观察第一次工具结果，再决定下一步动作，而不是预先执行固定的所有搜索。

#### 5.5 Low Evidence：明确拒绝编造

模式：`Policy Researcher` + `Document Analysis`

```text
What exact civil penalty amount does Australia's 2031 Quantum AI Act impose
for lunar data-centre violations?
```

预期：

- `evidence_sufficient=false`；
- 0 个最终引用；
- 红色 `Insufficient Evidence` 警告；
- 使用固定、清晰的不足证据格式；
- 明确指出资料没有提到 `2031 Quantum AI Act`；
- 不编造 penalty amount；
- 实测约 1,548 tokens，明显低于让 LLM生成一份长篇拒答。

讲解重点：Embedding 可能找到“澳大利亚 + AI + policy”的泛相关片段，但 Evidence Gate 还会检查明确命名的 Act/Standard/Framework 是否真的存在。

#### 5.6 Live Web Search：文档与最新网页比较

模式：`Open Discussion`

选择 `Voluntary AI Safety Standard`（2024）。

```text
Compare the selected 2024 Voluntary AI Safety Standard with the latest
information on the web. Has Australia replaced or updated it, and what is
current as of 2026?
```

预期路径：

```text
search selected documents
→ detect latest/current intent
→ search web
→ combine document and web evidence
→ answer
```

预期界面：

- 同时出现 `internal` 和 `web` evidence tiers；
- 文档 citation 与网页 citation 可区分；
- 显示 `From the web` 提示；
- 回答区分 2024 文档内容和 2026 实时信息。

注意：这个问题触发的是临时 Live Web Search，不会自动把网页永久导入 Library，也不需要“永久导入确认”。只有 Agent 要执行永久 import 时才需要用户确认。

#### 5.7 OCR 文件（可选）

模式：`Policy Researcher` + `Document Analysis`

只选择 South Africa OCR 文件。

```text
According to this notice, was South Africa's draft National AI Policy adopted
or withdrawn, and which earlier government notice and publication date does it
reference?
```

预期：

- 回答 `withdrawn in its entirety`；
- 引用 Government Notice 3880 和 2026-04-10；
- citation 来自 OCR 后生成的 Chunk。

讲解重点：原始一页 PDF 只有图片、没有文本层。能够回答并引用其中内容，说明 OCR 结果确实进入了后续 Chunk、Embedding 和检索流程。

#### 5.8 Answer Purpose / Persona（可选）

用同一个正常问题快速切换：

- Policy Researcher：结构化研究分析；
- Policymaker：偏实施、风险和行动建议；
- Student：更易理解的解释方式。

说明 persona 改变输出结构和语言风格，不改变底层证据来源。`Policymaker` 始终保持文档证据边界。

### Step 6 — History 与结束

建议时间：30–60 秒

1. 展示当前 Chat History。
2. 打开刚才的一条历史对话。
3. 展示回答、引用、ReAct steps、Token Usage 和 Suggestions 被持久化保存。
4. 简单展示 rename / delete（不要删除唯一演示记录）。

结束话术：

> The system separates retrieval, evidence checking and answer generation. It
> can answer from selected documents, expand to the shared library or the live
> web when the mode allows it, and explicitly stop when the available evidence
> cannot support the requested claim.

## 功能覆盖检查表

- [ ] 注册 / 登录或预建账号登录
- [ ] 普通用户与管理员权限
- [ ] PDF 上传及 processing status
- [ ] OCR
- [ ] Metadata 自动生成与非英文标题翻译
- [ ] Page / Chunk detail
- [ ] Duplicate detection
- [ ] Document governance：approved / access level
- [ ] Library Filter Bar
- [ ] 二级 Document categories
- [ ] LLM provider key 与 endpoint catalog
- [ ] Embedding provider、dimension、chunking、token counting
- [ ] Re-embedding 二次确认
- [ ] Reranker 与 Evidence Gate
- [ ] Suggested follow-ups
- [ ] Live Web Search
- [ ] 网页永久导入和重复检测
- [ ] Add to Chat / selected scope
- [ ] 普通文档回答
- [ ] Citation drawer、页码和 quote
- [ ] 跨语言 / 跨地区 / 跨文件
- [ ] Metadata Filter fallback
- [ ] selected → full corpus escalation
- [ ] selected → web escalation
- [ ] Low Evidence 红色警告和 0 citation
- [ ] Evidence tier 提示
- [ ] ReAct reasoning/tool trace
- [ ] Token Usage
- [ ] Copy / Export answer
- [ ] Chat History
- [ ] Answer Purpose / Persona

## 常见问题与回答

### “ReAct 是什么？”

ReAct 可以理解为循环执行：

```text
Reason：判断下一步需要什么证据
→ Act：调用选中文档、Library 或 Web 工具
→ Observe：读取工具结果和 Evidence Gate
→ Reason again：回答、升级搜索或停止
```

系统展示的是工具选择和证据结果，不展示模型隐藏的完整思维链。

### “Document Analysis 为什么不自动上网？”

Document Analysis 的承诺是严格基于所选文档。证据不足时应显示 Insufficient Evidence。Open Discussion 才允许扩展到 Library、Web 或一般知识，并在界面上提示来源边界。

### “Web Search 和网页导入有什么区别？”

Live Web Search 是一次性的实时证据；网页导入会永久进入共享 Library，并接受和普通文档相同的 Metadata、Chunk、Embedding、治理与重复检测。

### “Metadata Filter 没匹配到为什么还会回答？”

Metadata Filter 是可解释的软约束。严格过滤没有结果时，系统回到原始选择范围并显示 warning。它最多影响检索优先级和答案警告，不应让用户只得到 tool error。

### “为什么 Low Evidence 不只看 Reranker？”

不同 Reranker 的分数尺度不同，API 分数还可能过度集中。系统综合 Embedding distance、Reranker、文本覆盖、地区覆盖、上下文长度和明确命名的政策实体，避免单一分数造成误判。
