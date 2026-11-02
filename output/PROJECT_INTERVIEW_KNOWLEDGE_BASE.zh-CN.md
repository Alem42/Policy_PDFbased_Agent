# Policy in Action Library：项目技术、团队协作与 Git 演进面试知识库

> 生成日期：2026-10-17（Asia/Shanghai）。候选人：Zhanpeng Zhu／Alem42。当前代码基准：feature/durable-document-tasks@2a45d2a。本文面向面试辅助Agent，既讲技术机制，也保留版本、贡献和证据边界；数据库逐表设计从简。

建议先读00、01、02和14章建立项目与个人贡献概念，再按问题检索技术章节。13章按时间讲发展史，15章把多轮重构整理为可复述案例。VX实验能力与当前V2运行树严格分开。

## 目录

- [00. 版本、身份与知识库使用规则](#kb-00)
- [01. 项目背景、用户需求与产品介绍](#kb-01)
- [02. 整体架构、技术选型与最小数据地图](#kb-02)
- [03. 文档入库、OCR、分块、元数据与Embedding](#kb-03)
- [04. 混合检索、Reranker、证据检查与跨地区覆盖](#kb-04)
- [05. Direct、ReAct、工具治理、状态恢复与SSE](#kb-05)
- [06. 网页搜索、永久入库、去重与知识治理](#kb-06)
- [07. 十月改造：数据库连接池与有界上传](#kb-07)
- [08. 十月改造：持久任务、租约、原子发布与幂等](#kb-08)
- [09. 十月排障：迁移检查与可选模型等待预算](#kb-09)
- [10. 前端、身份认证、配置与Docker交付](#kb-10)
- [11. 独立实验线：执行画像、RunEvents、评测适配与MCP](#kb-11)
- [12. 评测、测试、历史验证与效果结论边界](#kb-12)
- [13. Git发展史：从原型、课程交付到两条后续支线](#kb-13)
- [14. 团队分工、个人贡献与原课程PR集成史](#kb-14)
- [15. 大规模重构案例与面试讲述方式](#kb-15)
- [16. 能力边界、技术术语与面试问题索引](#kb-16)
- [17. 证据索引、Git复核命令与后续维护](#kb-17)

<a id="kb-00"></a>

## 00. 版本、身份与知识库使用规则

### 候选人身份、团队和归属规则

候选人为 **Zhanpeng Zhu，Git 作者／GitHub 账号为 Alem42**，由候选人于本次会话明确确认。项目最初是 UNSW COMP9900 的六人团队任务，项目名为 P30 Policy in Action Library，团队编号 9900-W11C-BREAD。其他成员在本知识库中使用组员 A–E 等匿名标识；无法核实作者实名的历史记录保留为“未确认作者”，不能为了凑齐六人而强行归并。

回答“你做了什么”时，先使用 Alem42 在对应提交中的实际改动，再结合候选人自述的架构、客户沟通和交付责任。团队已实现某项功能，不代表全部由候选人独立开发；合并 PR 也不代表合并人编写了该 PR 的全部代码。历史中出现 ZZP、Demo_ZZP、Alem 等标识，以及内容等价的镜像提交，必须结合具体版本和改写记录判断，不能简单按作者名或提交数重复计算成果。

### 本次审查的代码基准

仓库：[Alem42/Policy_PDFbased_Agent](https://github.com/Alem42/Policy_PDFbased_Agent)。已执行 `git fetch origin --tags` 核对远程引用。当前工作分支是 `feature/durable-document-tasks`，HEAD 为 `2a45d2a4d334b0a8618f9f71fd473817db715532`。本文件中新代码行号以该快照为准；其他分支使用独立提交号引用。

| 版本标识 | 提交 | 作用及边界 |
| --- | --- | --- |
| V1：个人仓库主线／交付加固基线 | `origin/main`、`origin/develop` 均为 `65e58ad` | 2026-08-10 的交付加固版；具有文档入库、混合检索、Direct/ReAct、人工中断、聊天记录、Web 导入、管理员邀请等。原课程仓库 PR #62 的 head 也是它。 |
| VC：原课程仓库最后交付线 | `course-audit/main=117f6c9`、`course-audit/develop=b56be8d` | 直接从原课程仓库核对并抓取，最终 main 于 2026-08-11 合并 PR #63；比个人 V1 多历史发布 merge、邀请表初始化顺序修复、标题和 lint 等改动。它不是 V2 的基线。 |
| V2：当前工程改造分支 | `feature/durable-document-tasks`，`2a45d2a` | 在 V1 上增加 9 个 2026-10-15 提交：连接池、有界上传、持久任务、租约、上传幂等、迁移检查及可选模型阶段超时。已经推送到同名远程分支，尚未合并到 main/develop。 |
| VX：Agent foundation／观测／评测／MCP 实验线 | `feature/agent-foundation-contracts`、`feature/run-observability`、`feature/eval-smoke-runner`、`feature/mcp-and-mode-simplification`；末端 `0b22809` | Git 作者日期主要为 2026-08-15。包含 canonical execution profile、PolicySearchCapability、统一运行事件、15 条 smoke cases、FastMCP。**这些提交不是 V2 HEAD 的祖先，不存在于 V2 的受 Git 跟踪代码树中。** |
| 历史课程引用 | `legacy/course-main`、`legacy/course-develop` | 保留原课程开发脉络；不能仅按 main 分支名判断哪一个含最新完整功能。 |

截至审查时，V2 相对 origin/main 是 `0 ahead-on-main / 9 ahead-on-V2` 的祖先关系；个人仓库 main/develop 同指一个提交。抓取原课程最新引用后，`git rev-list --all --count` 得到 604 个可达 Git 提交对象，而当前 HEAD 可达 358 个，个人 main 可达 349 个。原课程 main 相对个人 main 在祖先集合上多 10 个对象；当前 HEAD 与原课程 main 则分别独有 9／10 个对象。这些数包含多条历史分支、镜像／改写副本、发布 merge 和 stash，不能表述为“604 项独立开发成果”。

原课程仓库是 [unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread)。其 GitHub API 返回 63 条 PR，包含未合并关闭的 PR；个人仓库的 PR 集合为空。本文件的团队 PR 证据来自原课程仓库，不把个人镜像仓库误称为承载这些 PR 的位置。Git AuthorDate、CommitDate 与 PR merged_at 也分别处理：分支中已经存在的功能可能过几天才合并。

最重要的答题约束：**V2 的持久化文档任务与 VX 的 MCP／统一 run events，当前不是已合并在一起的一套版本。** 如果面试提到二者，应说明“主线项目完成后，我在不同分支继续做 Agent 能力抽象和后端可靠性改造”，而不是说最新部署一定同时包含全部功能。

### 证据等级与回答规则

本知识库采用五类描述：①当前代码事实；②指定历史版本事实；③由 diff 推断的设计动机；④已有验证报告中的历史结果；⑤建议或未实现能力。没有明确标为“已验证”的描述，不应自动转写成线上指标。

技术回答应按“业务问题 → 实现机制 → 取舍 → 验证 → 边界”展开。不能虚构客户数量、政策库规模、QPS、生产 P95、准确率提升比例、模型训练经历或云服务高可用。不能把 Retrieval 的相关性判断等同于逐条事实验证，也不能把单一数据库事务等同于文件、网络与数据库的分布式事务。

本次建立了当前 310 个 tracked 文件的目录与类型清单，并扫描 295 个可解读文本文件；结合核心实现、测试、项目说明、37 页 proposal、36 条 Jira 导出、完整 Git 日志及关键变更 diff 审阅。模型缓存、密钥文件、数据库备份、node_modules 和部署私密配置不作为知识库内容。样例政策 PDF 主要用于说明业务与演示材料，不被当作代码设计依据。文档没有包含 Key、密码、登录 Token、学生学号或成员邮箱。

<a id="kb-01"></a>

## 01. 项目背景、用户需求与产品介绍

### 项目的业务问题

政策研究的材料来自政府报告、政策 PDF、研究报告、机构发布物及后续上传的内部案例，分散且格式不一。研究人员不仅需要查到一份文件，还需要从多份材料中提炼政策目标、实施条件、风险、可迁移经验，并比较不同地区的政策。直接把问题交给通用模型，无法保证模型拥有这些材料，也难以核对答案的出处。

Policy in Action Library 的产品目标是建立可持续扩展的政策资料库：管理员负责资料入库和治理，研究用户负责发现、选择资料及提问，系统基于指定或允许扩展的证据范围生成带来源的分析。它提供政策研究支持，不自动替代政策制定。

核心业务链路为：**管理员上传／导入 → 解析与索引 → 资料检索与选择 → Direct 或 ReAct 问答 → 展示引用与原文 → 必要时澄清并恢复。** 管理端可以维护模型服务、分类、文档可见性和重建任务，研究端可以查看历史会话及继续提问。

来源：`proposal.pdf` 物理第 3–5、24–32、33–37 页；`README.md`；`backend/app/modules/documents/`、`chat/`、`frontend/src/pages/`。

### 原始团队分工与候选人的技术负责人角色

Proposal 明确六人分别承担一个 Product Owner、一个 Scrum Master 和四个 Dev Team 角色；Zhanpeng Zhu 列于 Dev Team。简历中的“开发负责人／后端核心”是技术责任描述，不应改写成自己是课程正式 Product Owner 或 Scrum Master。客户沟通、任务协调和答辩责任来自候选人自述及项目材料，不能仅靠 commit 数量完整证明。

根目录旁的 `JiraStory.xml` 有 36 条故事／任务，更新时间主要覆盖 6 月下旬，是当时的分配快照而非最终交付清单。候选人被分配了管理员浏览／搜索／删除、上传、登录、自然语言问答、跨地区比较、过程可视化与反馈等故事（例如 W11CBREAD-3/4/5/9 已在该快照标为 Done，其余状态不同）。组员 A 的分配集中在可信网站与采集状态、文档详情与搜索；组员 B 集中在资料发现筛选、所选来源与比较。其余角色分别承担复杂文档分块／处理状态／导出、元数据／不足证据／回答风格、引用核查／后续问题等方向，不能在未核实身份时硬映射到某个 Git 作者。

Jira 的 Assignee 表示当时责任归属，不证明整项代码仅由一人实现；反过来，后来某人在同一模块做重构也不抹除原始开发者的贡献。面试可表述“团队最初按用户故事分工，我承担文档管理与研究问答主链，后来进一步负责后端架构整合与可靠性改造”，再用具体 SHA 支撑实现细节。

### 用户、角色与功能边界

系统权限角色主要是普通用户和管理员。研究者、学生、policymaker 等术语还曾作为输出风格或使用场景出现，不能将其全部视作数据库中独立的权限角色。普通用户选择可访问文档、提问并管理自己的会话；管理员上传及治理文档、调整模型和分类、重建索引、管理邀请。公开资料与 restricted 文档存在可见性差异，但这不是已完备的企业多租户隔离。

Document Analysis 模式强调所选文档是否足以回答问题。评价这条路径前，应先确认测试问题确实可由所选文档的原文／chunk 回答；与文档无关的问题被拒绝不等于检索失败。Open Discussion 允许进一步使用全库、网页等能力，且部分策略依赖模型遵循提示词。回答时必须先说清模式和来源范围。

### 原始设计与最后代码并不完全相同

Proposal 封面日期为 2026-06-20，仓库记录在 `2bf9088`（2026-06-27）加入该文件。它是需求和设计证据，不证明全部方案当时已经实现。

| 设计稿内容 | 实际演变 | 正确说法 |
| --- | --- | --- |
| 前端选择 React + Next.js | 当前 package.json、入口和 Dockerfile 是 React + Vite + React Router + MUI | 原设计讨论过 Next.js，实际交付采用 Vite SPA；没有证据证明曾完成一个 Next.js 生产版再迁移。 |
| 模板驱动、可预测的 RAG MVP | 先实现固定 LangGraph 工作流，之后增加 ReAct 工具循环 | Agent 是后续能力演进，LangGraph 早期就已用于线性 RAG，二者不能混为同一时间点。 |
| section-aware chunking | 当前主要为 token 预算、段落／句子优先和重叠 | 原方案目标不能替代代码事实；不能称已经完成标题感知或语义分块。 |
| 定期收集受信任政策网站 | 曾有独立 crawling 子系统，后改为 Web Search 与显式永久导入 | 需要说明旧爬取系统后来删除，不能把删除后的路由仍列为现有功能。 |
| 答案／引用评分、专门学习摘要等 backlog | 部分由问答、建议问题或界面能力承接，部分无完整实现证据 | Jira／设计稿中的故事不自动等于最终已交付。 |

### 面试项目介绍的两个长度

30 秒介绍：这是一个六人团队开发的政策研究 Agentic RAG 平台，把 PDF、DOCX 和网页资料变成可检索的政策知识库，支持带引用的问答、跨材料分析与人工中断恢复。我主要负责架构和 Agent／后端核心，后续继续做模块抽象、混合检索以及连接池、上传与持久任务等可靠性改造。不同后续能力分别保存在对应分支中。

三分钟介绍可按以下顺序展开：客户需要解决的证据追溯问题；资料入库与 dense/BM25/RRF/reranker 检索链；Direct 与 ReAct 为什么同时存在；人工确认怎样持久化；自己具体承担的实现和重构；如何用测试和已有小规模验证证明边界。最后说明数据集与规模局限，不用“用了很多框架”代替技术贡献。

<a id="kb-02"></a>

## 02. 整体架构、技术选型与最小数据地图

### 当前系统调用关系

```text
浏览器 React / MUI / React Router
  ├─ 文档库、筛选、选中文档、详情与引用
  ├─ Chat SSE、人工澄清、历史会话
  └─ 管理端上传、分类、模型配置、任务重试
         ↓ HTTP / JSON / multipart / SSE
FastAPI 路由和鉴权
  ├─ ChatTurnService → DirectOrchestrator / ReactOrchestrator
  │       ├─ RetrievalService → 文档 retrieval service
  │       │      ├─ pgvector dense → BM25 → RRF → reranker
  │       │      └─ evidence / context / citation
  │       └─ 兼容接口模型客户端 / WebSearchService / WebImportService
  ├─ 上传暂存 → 文档 + task + 幂等登记（V2）
  └─ 管理和目录服务 → 按职责拆分的 Repository
         ↓
PostgreSQL / pgvector + 原始文件目录 + 运行配置文件
         ↑
文档 worker：领取 task → 解析 / OCR / 元数据 / chunk / embedding
                         → 验证租约 → 原子发布索引（V2）
```

MCP 不在上图 V2 当前运行树中；它是 VX 对共享检索能力增加的另一个适配入口，详见实验分支章节。

### 关键技术及选择理由

| 技术 | 在项目中的职责 | 取舍与不能夸大的部分 |
| --- | --- | --- |
| Python / FastAPI / Pydantic | AI 与文档生态、类型验证、HTTP、异步入口、OpenAPI | async 不自动使同步数据库／推理非阻塞；需线程卸载或独立 worker。 |
| LangGraph | 固定 RAG 图、ReAct 图、状态、条件边、中断／恢复 | 当前是单 Agent 工具循环，不是多 Agent 自主协作系统。 |
| PostgreSQL / pgvector | 业务持久化、向量、检查点；V2 还承担任务 broker | 业务与检索在一个数据库便于事务及筛选；不代表具备跨机高可用或已完成大规模验证。 |
| FastEmbed / 外部 Embedding API | 文档与查询向量、部分元数据匹配 | 调用预训练模型，没有自研训练或微调证据。 |
| BM25 / RRF / Cross-encoder Reranker | 精确词补充、排名融合、精排 | RRF 没有学习权重，重排阈值应按服务校准；未证明全任务固定提升。 |
| pypdf / PyMuPDF / Tesseract / python-docx | 原文提取与扫描页 OCR | 没有完整复杂版面理解，DOCX 真分页与中文 OCR 有明确边界。 |
| React / Vite / MUI | SPA、组件、资料篮、流式回答与管理端 | 不使用 Next.js SSR；页面路由受 Caddy SPA fallback 支持。 |
| Docker Compose / Caddy | 前端构建、反向代理、后端与数据库编排 | 是单套服务交付编排；不能自动等同 Kubernetes、滚动发布或 Azure 托管服务。 |
| pytest / Ruff / Node test | 逻辑回归、集成验证、静态检查和上传前端测试 | 当前 GitHub Actions 只自动跑 Ruff，不能称已配置完整测试／部署 CI/CD。 |

### 数据设计只保留理解链路所需信息

数据大类包括用户与邀请、文档及其元数据、页面与 chunk、按模型隔离的向量、聊天会话与消息，以及 V2 的持久任务和上传幂等登记。原始文件存放在文件目录中，不直接塞入向量列。LangGraph 检查点由其 PostgreSQL saver 管理内部表。

本知识库不逐列解释数据库 DDL。需要重点理解的是身份 ID 与文件名分离、chunk 与向量空间分离、任务状态与文档状态分离，以及相关数据在什么事务中一起提交。VX 的 `agent_runs/agent_run_events` 属于另一个分支，不能补到 V2 当前表清单中。

<a id="kb-03"></a>

## 03. 文档入库、OCR、分块、元数据与Embedding

### 文档模块的职责与完整调用链

适用版本：V2；包含V1已有能力，十月增强单独说明。

#### 分层不是多拆几个文件

当前 `backend/app/modules/documents/service/` 由三层职责构成：

| 模块 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `library.py` | 文档 UUID/文件名解析、页面/文件读取、元数据编辑、治理和删除 | 不决定召回排序，不执行完整入库流水线 |
| `pipeline.py` | 上传注册后的抽取、元数据、chunk、embedding、索引发布、重扫、重嵌入、网页去重 | 不在这里拼 Agent 的规划循环 |
| `retrieval.py` | 从选中文档或全库取 dense 候选，BM25/RRF，rerank | 不做文档 CRUD 与 PDF 解析 |
| `app/modules/retrieval/service.py` | 过滤、检索、证据判定、引用和 context 的统一业务语义 | 不拥有 HTTP/SSE/LangGraph 会话状态 |

`pipeline.py` 与文档 `retrieval.py` 都依赖 `library.py` 做标识符解析，避免库管理反向依赖入库和检索。统一检索服务又复用文档层的检索能力，从而让 Direct、ReAct 和建议问题验证共享判定语义。依据：`documents/service/library.py:1`、`documents/service/retrieval.py:1`、`retrieval/service.py:36`。

#### 当前管理员上传路径

```text
POST /admin/documents
  -> require_admin
  -> save_upload(... durable=True, metadata, idempotency_key)
  -> 分块读取/暂存文件、文件类型与大小校验、SHA-256
  -> 文档+上传请求幂等记录+持久化任务登记
  -> 返回 202 + document_id + task_id
  -> queue.notify() 仅是唤醒提示
  -> worker 领取 ingest 任务
  -> execute_document_task -> process_document -> _process_document
  -> 抽取 / 可选元数据 / chunk / 可选 header / embedding
  -> 持有当前任务所有权的最终事务发布页面、元数据、chunks、vectors、ready 与任务成功
```

入口见 `documents/admin_router.py:71`，`durable=True` 在 `:106`，返回结构和 notify 在 `:112`。当前默认单文件上限 **20 MiB**，上传读取块 **1 MiB**，见 `core/config.py:34`。连接池、lease、上传幂等细节由专门工程章节展开；这里必须记住：HTTP 返回 202 代表已接受任务，不代表已完成索引。

当前 `process_document` 在 `embedding.snapshot()` 内执行，见 `documents/service/pipeline.py:49`。`_process_document` 的算法计算主要放在最终发布事务之外；到 `:124` 才取得有任务所有权的连接，将 `replace_pages`、`upsert_generated_metadata`、content hash、`replace_document_chunks`、文档 ready、job finish 和 task succeed 放在同一连接上发布。见 `:126` 至 `:143`。这与早期“每一阶段各自先提交、最终可能只更新部分索引”的路径不同。

算法计算失败时不发布半套新 chunks/vectors；普通非 durable 调用会把 document 标为 failed，durable 调用则由任务重试机制管理状态。`LostTaskLease` 单独抛出，避免失去 lease 的 worker 当作普通失败继续写结果，见 `pipeline.py:150`。

#### 状态与实际阶段要对应

数据库状态 `uploaded -> ocr（需要时） -> parsed -> annotated -> ready/failed`，HTTP 映射为 queued/OCR/chunking/embedding/indexed/failed。见 `documents/admin_router.py:60`。这些是业务进度状态，不是每个算法子步骤的性能 profile。

入库 job 的老名称仍叫 `ingest_pdf`，但实际分发支持多文件格式；不能仅凭这个字符串判断只支持 PDF。见 `pipeline.py:59` 与 `documents/extraction.py:11`。

### 解析、OCR、清洗与原文定位

适用版本：V2；包含V1已有能力，十月增强单独说明。

#### 支持哪些输入，统一输出什么

`documents/extraction.py:11` 按扩展名将 `.pdf/.docx/.txt/.md` 分发到各 extractor。输出统一是 `[{file, page, text}, ...]`，使下游无需按输入类型分支。旧版 `.doc`、Excel、图片文件作为独立上传源不在分发表中。

PDF 使用 `pypdf.PdfReader` 原生文本抽取；`enumerate(..., start=1)` 保存 PDF 文件中的物理页序号。见 `documents/pdf_extractor.py:59`。它不是封面上印出的页码，也没有对 Roman numeral 或正文页码重新映射。

DOCX 使用 python-docx：先收集非空段落，再遍历表格，将非空 cells 用 ` | ` 合并成行；最后整个文件当成 `page=1`。见 `documents/docx_extractor.py:17`。DOCX 本身不包含跨渲染器稳定的物理分页；当前没有调用 Word/LibreOffice 渲染器，因此不能声称 Word 引用精确到用户看到的真实页码。由于先全部段落、后全部表格，正文与表格原来的交错位置也未完整保留。

TXT/Markdown 用 UTF-8 解码，错误字符替换，全文 `page=1`，见 `documents/text_extractor.py:14`。Markdown 只是可检索文本，这里没有按 AST 解析标题层次。

#### OCR 的触发条件和失败语义

每页原生抽取文字长度低于 `ocr_min_text_chars` 才 OCR，默认 **20 字符**，见 `core/config.py:57`、`pdf_extractor.py:86`。这是“低文本页启发式”，不是扫描页分类模型。数字版文档里真正只有几个字的页面也可能触发 OCR。

OCR 路径：PyMuPDF 打开 PDF -> 单页渲染 **200 DPI** bitmap -> PIL Image -> `pytesseract.image_to_string`。见 `pdf_extractor.py:19/:112`。只有需要 OCR 的页会执行，所以文字页与扫描签名页混合的 PDF 不必全篇 OCR。回调 `on_ocr_start` 让上层将状态改成 ocr，见 `:91`。

默认语言为 **eng**，可配置 `eng+chi_sim` 等；见 `core/config.py:59`。`backend/Dockerfile:10` 只显式安装 `tesseract-ocr`，不能由此保证中文 traineddata 已装好。配置一个语言名称不等于镜像具有该语言包。

渲染打不开、Tesseract 未安装、某页 OCR 异常都记录 warning 并返回原页面文本/空 OCR 文本；只有 OCR 成功且非空才替换该页原文，见 `pdf_extractor.py:96/:103/:117`。因此“支持 OCR”不等于“所有扫描页均可读取”；若读不到文字，下游可能没有 chunks 或证据不足。

#### 清洗规则及其取舍

`pdf_extractor.py:128` 做三种清洗：

1. 页首三行和页尾三行中统计重复行；先压空白、小写、将数字替换成 `#`，长度 4–120 的行参与统计；频次至少 `max(3, page_count//4)` 视作重复边缘噪声。
2. 若有英文 contents 标记，且点引导条目/编号条目达到阈值，清空目录页。
3. 文档后 30% 出现独立的 References/Bibliography/Works Cited 标题后，删除后续参考文献文本。

收益逻辑是降低固定页眉页脚、目录和引用列表对检索的干扰；这不是已测的 Recall 提升数字。风险是重复正文、具有内容意义的页尾或后部章节可能误删，英文标题规则也不全面适用于中文。没有版面框、栏排序、表格单元格结构识别、OCR 置信度统计或识别纠错模型。

#### 引用为何能定位，以及能定位到什么程度

chunk 构造保存 `page_start/page_end`；数据库 chunk 还保存 `document_id/chunk_index/text/token_count/language/metadata_json`。见 `documents/chunker.py:58`、`documents/repositories/embeddings.py:111`。原始抽取页面单独保存在 `document_pages`，见 `documents/repositories/content.py:15`。

统一 citation 当前输出 `document_id/title/chunk_id/page/quote`，其中 `page` 的值取自 chunk 的 `page_start`；quote 为 chunk 文本前 **500 字符**；无向量页面 fallback 的 quote 为页面前 **300 字符**。见 `retrieval/service.py:320`。`page_end` 暂未出现在该 citation 结构中。跨页 chunk 的 quote 可能包含多页内容，但 UI citation 仍只给起始页。

所以准确表述是“PDF 可回到文档、起始物理页和已保存文本片段”；当前没有字符 offset、PDF bbox、逐句证据抽取、每条生成 claim 的 entailment 校验。引用存在，也不能证明答案每句话都被引用支持。contextual header 不进入原文 quote，避免生成的说明句冒充原文。

### 分块：从 tokenizer 到跨页 overlap

适用版本：V2；包含V1已有能力，十月增强单独说明。

#### 当前算法和参数

默认 `max_tokens=480`、`overlap=120`，见 `documents/chunker.py:13`。入库会读取可配置 `chunk_token_budget`，再限制到 64–8000，见 `pipeline.py:90`；schema 允许 64–8192，见 `embedding/settings.py:79`。不能把管理员可填的上限当成模型真实上下文窗口。

分块函数首先将 `max_tokens` 限制为至少 64，并把 overlap 限制在 `[0,max_tokens//2]`；每个单独段落/句子片段的预算为 `item_budget=max_tokens-overlap`，见 `chunker.py:37`。对 pages 逐页处理，按空行分自然段、压缩段内空白；段落超过 item_budget 时按句末标点后空白分句，仍太长则二分查找可容纳的字符切点。见 `:101/:171/:207`。

将片段累积进当前 chunk，加入新片段前若 token 总和超预算则 flush。chunk 可能跨页，页范围来自首末片段。flush 后保留尾部完整段落作为 overlap；最后一段自身大于 overlap 时，退回尾句，单尾句仍超限时保留 token 预算内的尾部字符串。见 `:53/:79/:125/:141`。

这解决两个实际问题：单一巨长段落不能绕过 chunk 上限；尾段较长也不会导致 overlap 完全为零。同时 overlap 不是必定精确 120 tokens，而是尽量保留段/句边界的近似预算。

#### tokenizer 与模型输入窗口

生产默认实例为 `EmbeddingModelDocumentChunker`，通过 `embedding.count_tokens` 计数，见 `chunker.py:238/:247`。本地 fastembed provider 使用该模型 tokenizer 且关闭 truncation 来计数，见 `embedding/providers.py:89/:130`；API provider 没有本地 tokenizer 时回退 `tiktoken/cl100k_base`，见 `embedding/tokens.py:33`。API 计数是近似，不应说成“所有模型都精确计 token”。

单独片段 token 数相加与最终拼接文本重新 tokenize 不一定严格可加；最终 chunk 保存重算的 token_count，但控制逻辑使用片段计数和。sentence regex 要求标点后有空白，连续中文标点后无空格时可能继续走硬切。再加 contextual header 后，最终 embedding 输入比裸 chunk 更长；当前没有在 header 拼接后再按模型上限严格截断/重分块。

#### 480/120 怎么解释，怎么调

480 的工程背景是早期 bge-small 输入长度约束与给特殊 token 留余量；120 让边界附近证据能够重复出现。它不是由当前真实政策大样本搜索得出的最优值。调整时可设计 256/480/768 等 chunk budget 与 10%/25% overlap 的组合，但必须保证模型窗口允许，固定其余变量，按长短政策、跨页事实、表格和中文分别评估召回与成本。

小 chunk 通常定位更细，可能丢上下文且增加 chunk 数/embedding 成本；大 chunk 上下文更完整，可能主题混杂、稀释匹配并增加 reranker 输入和最终 context。overlap 增加边界召回机会，也增加重复候选和上下文浪费。当前未做按 section 感知切块、embedding 相邻句相似度切块、父子索引或递归 parent retriever；TODO 明确写在 `chunker.py:24`，`section_title` 当前一直为 None。

### 元数据、taxonomy 与 contextual retrieval

适用版本：V2；包含V1已有能力，十月增强单独说明。

#### 元数据抽取使用文档采样而非全文无限输入

`documents/ingestion/metadata_extractor.py:159` 将带页号文本拼接，最多头 **9000**、中 **5000**、尾 **2000** 字符，文档 <=16000 字符时直接用全文；长文档插入 `[...]`。头部权重大是因为政策标题、发布机构、国家和目的经常在前部，中尾用于发现后部主题。

LLM 要求输出 title、summary、source_type、source_organisation、country_region、language、year、publication_date、policy_areas、keywords、stakeholders、implementation_risks 的 JSON。人类可读 metadata 统一英文；policy_areas 要求选 taxonomy 的叶子项 3–6 个，keywords 5–12 个。见 `metadata_extractor.py:32`。Prompt 要求数量不等于所有结果都严格通过 Pydantic 对每项强校验；代码还会清洗 list、year/date、剥 code fence 或从文本抓 JSON。见 `:73/:90/:96/:133`。

语言优先 LLM 值，再 lingua 检测，再粗规则；粗规则无法当作可靠的通用语种模型，见 `metadata_extractor.py:112/:126`。每 chunk 还单独 detect language，见 `pipeline.py:106`。

#### taxonomy 对齐减少自由标签漂移

自由输出的 policy-area 标签和所有标准叶子标签使用同一个 embedding 模型编码，按 cosine 找最近叶子；相似度至少 **0.5** 才接受，最多 **6** 个且去重。标签向量缓存键为 `(active_model_id, leaf_labels)`，LRU 8，见 `documents/ingestion/policy_matcher.py:25/:34/:55`。embedding 失败则退精确匹配，再退 Other。它是推理时最近邻归一化，不是监督分类训练或微调。

这里有值得回答的局限：缓存键包含 model_id 与标签集，却没有维数/provider 版本。如果同名模型换维数，理论上仍可能命中不匹配缓存；这是未来可以加强的配置身份设计，不能声称已解决所有模型切换场景。标签模型相似度阈值同样没有当前真实标注集上的校准报告。

人工审核过且已有值的若干字段会在重新生成时保留，见 `documents/repositories/content.py:49` 后的 CASE；stakeholders/implementation_risks 等仍更新为生成值，不能说所有人工字段都完全锁定。

#### contextual header 的实现与成本边界

每个 chunk 发送 document title、已生成 summary、chunk 前 **1200 字符**，要求一句最多 25 words 的定位说明；清洗空白，最多保留 **240 字符**。只将 `header + '\n\n' + chunk_text` 送 embedding，原 chunk text 用于展示和引用，header 存 metadata_json 方便解释。见 `contextual_header.py:30/:37/:50/:82`、`pipeline.py:94`。

这采用 contextual retrieval 的思路，但没有把整本文档送进每个 chunk 的上下文，也没有使用 provider prompt caching；文件注释将其列为未来升级，`contextual_header.py:8`。不能声称复现某论文/厂商的完整实验条件或性能收益。

2026-10-15 `fc53841` 后：header 单请求 timeout **10 秒**、max_tokens **128**、max_retries **0**；每文档线程池最多 **6**，阶段 wait 最多 **20 秒**，未完成的 header 退空字符串；shutdown 不等待已运行网络请求，网络 timeout 再限制其存活。见 `contextual_header.py:30/:66/:96`。这使可选增强不必拖垮整个入库，但 Python cancel 不等于已运行线程立即终止。

同一提交还给 metadata LLM 请求 **15 秒**、阶段 future.result **30 秒**、max_tokens **1024**、max_retries **0**，全进程共享 **3** 线程池，见 `metadata_extractor.py:25/:188/:209`。超时抛出到 pipeline，退文件名/default metadata 后继续。30 秒限制覆盖该 LLM future 的等待，不应扩大成“taxonomy、embedding、整个文档任务最多 30 秒”；后面的标签 embedding 等有独立耗时。

### Embedding provider、向量空间与 pgvector

适用版本：V2；包含V1已有能力，十月增强单独说明。

#### 用一个服务入口包住不同模型

调用方只依赖 `app.modules.embedding.service`：embed_documents、embed_queries、count_tokens、active_model_id/dimension/vector_table。provider 是本地 FastEmbed 或 OpenAI-compatible `/embeddings`。见 `embedding/service.py:1`、`embedding/providers.py:52`。

本地默认 `BAAI/bge-small-en-v1.5`，**384 维**；另列 bge-base 768、multilingual-e5-large 1024。API 可自动探测真实维数或指定维数。见 `embedding/settings.py:24/:40/:73`、`embedding/service.py:171`。这些是代码默认与可选项，不是本次读取到的部署实时模型，本次没有连接数据库去读当前配置。

本地文档调用 passage_embed，query 调用 query_embed，是非对称编码接口；API 通常使用同一 `/embeddings` 请求形式，provider 设为 symmetric。见 `embedding/providers.py:99/:107/:118/:138`。非对称检索不是简单地让两个 encoder 永远不同，而是允许训练/前缀/编码路径针对 query 与 passage 的任务角色不同；本项目使用库提供的路径，没有自行训练 encoder。

每个向量转 float、验证长度与 finite，防止 NaN/Inf 或错误维数写库。批大小默认 **32**，可设 1–256；HTTP embedding timeout **30 秒**，见 `embedding/providers.py:41/:150`。接口没有通用的自动 API provider 切换或 provider 内重试；durable 文档任务可能重试整次任务，这是另一层。

#### 为什么要按模型分表

`vector_table_name(model_id,dim)` 对默认 bge-small/384 映射老 `chunk_embeddings`，其他模型形成 `chunk_vectors_{slug}_{dim}`，见 `embedding/settings.py:28`。chunk 文本保存在模型无关的 document_chunks，各模型向量表用 chunk_id 外键引用它。不同模型即使维数相同，向量空间也不应混算；更换维数更不能直接塞进同一固定维数列。

切模型只是切表，不会自动给新模型生成旧文档向量；目标模型尚无该文档向量时需要 reembed，切回已经建好向量的模型空间可以直接复用。重嵌入复用 chunk 文本和已存 header，不重新解析/分块，不删除其他模型已有向量。完整 rescan 则重新分块，删除 document_chunks 会级联删除各模型旧向量，见 `documents/repositories/embeddings.py:81/:136/:155`。

表名当前只按 slug+dim 并截 63 字符，不包含模型权重 revision、provider 身份或内容 hash；长模型名有潜在截断碰撞，同名模型的服务端权重改变也不是新的数据版本。这是进一步完善模型身份/versioning 的方向。

#### 10 月 snapshot 解决的并发问题

一次任务从 tokenize、embed 到选择存储表之间，若管理员切模型，不能出现“模型 A 产生向量，按 B 的维数或名称写库”。当前 `embedding.snapshot()` 用 RLock 获取 config 的深拷贝和 provider 引用，用 ContextVar 固定本次执行上下文；finally reset，见 `embedding/service.py:37/:82`。入库和 durable reembed 都使用它，并把明确 `(table,dim,model_id)` target 传给 repository，见 `pipeline.py:49/:164`。这是配置一致性，不是数据库快照隔离，也不是多进程自动广播配置。

模型/设置缓存仍是进程内状态；管理员更新一个进程的设置不会天然让其他进程立即 reload。普通检索路径没有看到同样包围整次 query+SQL 的 snapshot。因此不能把“入库 attempt 已固定模型”泛化为所有读写请求在所有 worker 间都已经完全一致。

#### 实际使用什么索引和距离

当前 SQL 固定 `embedding <=> query`，即 cosine distance，升序排序。见 `documents/repositories/embeddings.py:230/:275`。即便 `EmbeddingConfig.distance_metric` 允许 cosine/l2/ip，代码的 SQL 和 index ops 仍固定 cosine，见 `embedding/settings.py:83`。这个字段当前没有完整接入，不可声称已支持切换三种距离。

数学定义：

\[
\operatorname{cos}(q,d)=\frac{q\cdot d}{\|q\|\|d\|},\qquad
\operatorname{distance}_{cos}=1-\operatorname{cos}(q,d).
\]

单位归一化时，dot product 与 cosine 排序一致，且 `||q-d||²=2-2cos(q,d)`，L2 升序也等价；未归一化时不能直接互换。该等价是理论，不代表代码已做了显式 normalize 或同时测过三种 metric。

旧表 init SQL 建 HNSW cosine index；动态建表见 `repositories/embeddings.py:34/:53`：维数 <=2000 用 vector 和 vector_cosine_ops；2001–4000 用 halfvec 和 halfvec_cosine_ops；>4000 用 halfvec 但不建 ANN index，退 exact scan。配置维数上限 4096，因此有可能走 >4000 情况。

HNSW 理论上用多层近邻图导航，通常以更多内存和较贵建索引换查询速度/召回；m 控图连接数，ef_construction 控建图搜索，ef_search 控查询候选。当前代码没有显式调这三个参数，也没有本次 EXPLAIN ANALYZE、ANN recall 或百万级压力数据。建立索引不等于 PostgreSQL 优化器每次必选该索引；有过滤的小 scope 也可能选择精确扫描。halfvec 半精度可节约存储，但不能仅凭注释声称“质量不变”。

<a id="kb-04"></a>

## 04. 混合检索、Reranker、证据检查与跨地区覆盖

### BM25 与 RRF：公式、缓存与失败边界

适用版本：V2／V1检索主链。

#### 先把文档范围和排序算法分开

选中文档路径先经 `library.resolve_document_ids` 在当前权限下把 UUID/filename 解析为 document_id，再 query embedding -> dense SQL -> BM25/RRF -> rerank；全库路径使用 retrieve_all，并按 approved/public 限制非管理员文档。见 `documents/service/retrieval.py:74/:100`、`documents/service/library.py:123`、`documents/repositories/embeddings.py:241`。

候选池 `C=max(3*K,20)`：dense 取 C，BM25 取 C，融合后再截 C，最后 rerank 输出 K。默认低层 K=8，得到 C=24；应用 settings 也有 default_top_k=6，不能把某一个默认值当所有入口的固定值。见 `documents/service/retrieval.py:83/:111`、`retrieval/contracts.py:71`、`core/config.py:48`。

#### BM25 的 document 实际是 chunk

这里的 BM25 是 Python 进程内实现，未引入 Elasticsearch、Lucene、pg_search 或数据库 FTS 排名。每个 chunk 作为一篇 document，统计 term frequency、document frequency、token length、avg length，并建立 term -> [(chunk slot,tf)] 倒排表。见 `retrieval/keyword_search.py:73`。

Latin/数字分词小写，保留 Unicode 字母和数字，去少量英文 stopwords；CJK 连续串取字符 bigrams，单字符单独保留。见 `keyword_search.py:28/:37/:59`。例：“人工智能安全”得到“人工/工智/智能/能安/安全”。没有中文词典分词、英文词干化、同义词词典或短语距离匹配。

当前 Okapi BM25：

\[
\mathrm{BM25}(q,d)=\sum_{t\in\operatorname{unique}(q)}
\log\left(1+\frac{N-df_t+0.5}{df_t+0.5}\right)
\frac{tf_{t,d}(k_1+1)}{tf_{t,d}+k_1(1-b+b|d|/avgdl)}.
\]

默认 **k1=1.5,b=0.75**；见 `keyword_search.py:22/:96/:104`。k1 控 tf 饱和程度，b 控长度归一化；b=0 相当于不用文档长度，b 越高越惩罚很长 chunk。query terms 使用 set，因此不重复加 query tf；不单独实现 BM25 k3。只返回正分结果，同分按原 slot 保持确定性，`:109/:122`。

BM25适合精确法案名、缩写、年份、条款号；dense 更适合语义改写。BM25 不理解跨语言同义，英语 query 与中文 chunk 若没有共享数字/词，稀疏侧本来就难匹配；多语言能力仍依赖模型与数据。

#### 索引是按范围缓存，不是持续增量搜索服务

BM25 从 PostgreSQL 取当前 scope 的全文 chunk rows，scope key 为排序后的 document_ids 或全库，加 include_restricted。索引 LRU 最多 **8** 个，锁保护缓存读写；fingerprint 是该 scope 的 **chunk count + max(created_at)**，每次 lookup 先查询 fingerprint。见 `keyword_search.py:132/:140/:172`、`documents/repositories/chunk_texts.py:19`。

重新入库会改变 chunk count/最新时间，触发重建；只 reembed 不改变文本，缓存可以复用。缓存 build 在锁外，避免长时间阻塞其他读取，但并发 miss 可能重复构建。不同 Python worker 有各自索引副本，首次构建加载全 scope，数据规模变大后会有内存与冷启动成本。fingerprint 是粗变化标记，不是完整内容校验和。

full-corpus BM25 仅纳入 approved/public；selected IDs 的仓储方法假定上层已经做过 ACL，与 dense scoped 行为一致。见 `chunk_texts.py:12/:16/:29/:58`。这不是数据库 RLS，直接绕过上层调用内部 repository 的开发代码必须自己保证身份边界。

#### RRF 为什么不用原始分数相加

cosine distance 越低越好，BM25 越高越好，量纲与分布不同，直接加总很依赖归一化和权重。RRF 只使用名次：

\[
\mathrm{RRF}(d)=\sum_{r\in\{dense,sparse\}}\frac{1}{k+rank_r(d)},\qquad k=60.
\]

当前两路等权，rank 从 1 起。按 **chunk_id** 去重；同时在两路出现的 chunk 累加两次贡献，dense 记录保留 distance，合并 bm25_score；排序截 C。见 `keyword_search.py:214`。代码没有保存输出 rrf_score，也没有按文档去重、MMR 或全局 diversity 目标。k 越大，头部名次差的影响相对平缓；k 越小，更突出每路排名前列。默认60是常用设计参数，不是当前语料上 grid search 得出的最优值。

融合后只在 BM25 中出现的候选会额外计算 query 的真实 cosine distance，当前模型没向量则默认 **1.0**，确保后面证据 gate 的 distance 含义不被 bm25_score 替代。见 `documents/service/retrieval.py:64` 和 `repositories/embeddings.py:311`。

#### 重要失败路径

- BM25 被 env 开关关闭、scope 无文本、内部 SQL/缓存/分词异常时返回 []，外层保留 dense 排序，见 `keyword_search.py:183/:209`。
- **dense=[] 时直接跳过 BM25**，不是让稀疏独立救回无向量库。设计意图是保持 selected 的页面 fallback；见 `documents/service/retrieval.py:46/:54`。
- dense 非空但 BM25-only chunk 没当前模型向量时，distance=1；最终能否通过还取决于 reranker/词法规则，不能说词项一命中就回答。
- 提问建议批量 validation 使用 retrieve_many 的 dense 路径，没有每问题再跑 BM25；临时网页 evidence 也不复用持久语料的 BM25 索引。见 `retrieval/service.py:244`、`docs/BM25_HYBRID_RETRIEVAL.md:160`。

### Reranker 与证据充分性

适用版本：V2／V1检索主链。

#### Bi-encoder 和 cross-encoder 怎么分工

Embedding 检索通常独立编码 q 和 d，文档向量可预计算，适合从大集合快速召回；cross-encoder 让 query 与候选 passage 联合进入模型，学习更细粒度的匹配，但每个候选都要重算，适合小候选集重排。当前 local 为 FastEmbed TextCrossEncoder，默认 `BAAI/bge-reranker-base`，见 `documents/reranker.py:12/:21`。没有自行训练/蒸馏 reranker。

管理员可选 local/API、开关、模型与分数门槛，配置为数据库单行 JSON。local 模型按 model_name 缓存最多2个，避免每次请求重新加载。API 使用 Cohere-style `/rerank`，发 model/query/documents，按返回 index 对齐输入顺序，见 `reranking/providers.py:29`、`reranking/service.py:75`。

#### 分数门槛不能跨模型照搬

当前默认 local floor **-2.0**，API floor **0.99**；local score 通常是 logits，API文档约定为相关性分数，数值处于0–1也不自动意味着已校准概率。schema 分别限制 local -10–10、API0–1，见 `reranking/config.py:19/:41/:54`。`evidence.py:14` 的 -7.0 只是读取服务异常时的兜底常量，不是当前常规 local 默认。

embedding 默认 distance cutoff local **0.45**、API **0.50**，见 `embedding/settings.py:46`。两种 provider 的阈值是代码默认/历史 demo 调整，不足以证明所有模型都完成同等质量校准。

#### Reranker 抛异常与静默错误不同

外层 `_rerank_or_dense` 关闭或异常时返回输入 candidates 的前 K，见 `documents/service/retrieval.py:25`。如果输入已被 RRF 排好，实际是退回 **RRF 排序**；注释/log 仍称 dense ranking，这个命名不完全反映当前流程。不会自动切另一个 reranker provider。

当前 API timeout **30 秒**，不传 top_n；响应 `results` 逐项取 index/relevance_score（或 score），未返回项预填 **0.0**，见 `reranking/providers.py:40/:48`。因此 HTTP200、results=[] 不会抛异常，不会触发 fallback，而是所有候选都带0分进入 gate。未实现完整结果数量校验、重复 index 校验、finite分数校验和 provider-specific适配；注释所说多个厂商“同形状”不能代替实际兼容性验证。

#### 当前 gate 的逻辑可以写成真值路径

对单 chunk，`retrieval/evidence.py:213`：

1. 若 distance <= active cutoff，则要求“没有 reranker_score，或 score >= active floor”。
2. 若 distance 超门槛，则计算英文有效 query 词在文本中的覆盖率；至少匹配 **2** 词且 coverage>=**0.30**，并且已有 reranker score 要过 floor。
3. 若没有 reranker score，要走更强词法条件：至少匹配 **3** 词且 coverage>=**0.60**。

词法 regex 是 `[a-z0-9]+`，见 `evidence.py:44/:95`，这里与 BM25 中英分词不是同一套逻辑。中文 query 的这一回退基本不起作用，不能说所有证据规则都中英对称。

对整体 evidence，indexed 情况必须有 raw候选、有相关 chunk，context 至少 **200 字符**，且显式命名的政策工具受到支持，见 `evidence.py:231`。没有当前模型 embedding 的 selected scope 才使用 pages fallback；full corpus 空检索不退全页，见 `retrieval/service.py:72/:103/:122`。已经有向量但结果不相关时，不能再把全部 PDF 页塞回去并伪造可回答感。

#### 专名约束为何比一般相似度更严格

英文 Title Case 的 Act/Bill/Regulation/Standard/Framework/Policy/Plan 被识别为政策实体名，去 generic词后，要求 distinctive terms 都存在于 evidence。这样 broad Australian AI文本不能仅凭主题相近就支持不存在的“2031 Quantum AI Act”，见 `evidence.py:27/:185`。

词袋只能保证词都出现，不能保证在同一句或同一实体里；当前补了 LLM veto：只有词袋已经允许时，问模型是否明显是另一个国家/组织的政策，YES才否决，出错则放行。见 `evidence.py:110` 后注释与 `_llm_disputes_named_instrument`。所以 gate 不是完全 deterministic，也不是“检索一定不调用 LLM”；该分支会额外调用生成模型。

它仍有英文实体规则覆盖窄、跨段词项误匹配、译名/同义表达误拒、LLM veto不确定性和失败放行等限制。没有逐项claim entailment、法律效力自动判别或事实核验模型。

### 元数据过滤与跨地区比较

适用版本：V2／V1检索主链。

#### 过滤是确定性解析，不是任意语义理解

`retrieval/metadata_filters.py:117` 读取当前可见文档已有的 policy labels、regions、organisations，用已知标签全文出现/有限中文别名、年份规则、特定语言语句和显式字段构造 MetadataFilters。region alias 在 `:65`，源语言模式在 `:34`。用户说“用中文回答”不等于只查中文文档，测试也固定了这个区别。

年份支持 before/after/since/through等范围；before/after为排除该年的严格界限；明确filter before子句优先于问题主语里的year。没有范围词时可能把出现的年份 min/max 当过滤。freshness词触发从代码运行年往前5年的下界，见 `:157/:188`。这只是近年偏好，不代表法律“现行有效”或自动知道所有修订/废止版本。

同一字段多个 policy areas/regions/languages 通常 OR，tags 要全部包含，跨不同字段 AND，见 `_matches` `:252`。匹配大小写不敏感但要求精确标签，不做语义范围扩展。metadata 是生成或人工维护的数据，识别错国家/年份会影响过滤质量。

#### 无结果与弱结果的两级回退

若 metadata subset 为空，保留原始可见 scope，`applied=True/fallback=True`，返回明确 notice；freshness无命中时特别提示可能是旧材料。见 `metadata_filters.py:203/:233`。这只能放松检索偏好，不能放松ACL。

若 metadata subset 非空但证据不足，且不是多地区比较，统一服务再用原始 scope、清空metadata filter重试一次，并返回 filter_notice。见 `retrieval/service.py:157`。它不会无限递归，因为第二次 filter为空。

若用户明确要求多个地区，不能简单把过滤放松成只答一个国家；`_supplement_region_evidence` 为每个地区单独搜索，加“Focus region” query，per-region limit=`max(2,K//region_count)`，按chunk_id合并。见 `retrieval/service.py:184`。最终检查每个地区是否有相关引用文档或正文提及，否则 sufficient=False，`:217`。

补充后 raw候选总数可能超过初始K；它是特定跨地区覆盖策略，不是统一MMR优化。正文提及地区也可算覆盖，不能等价于“引用来自该地区官方来源”。这个边界正好适合解释：比较回答需要覆盖约束，单纯全局topK可能全部偏向资料最多的一个国家。

<a id="kb-05"></a>

## 05. Direct、ReAct、工具治理、状态恢复与SSE

### 从请求到答案：实际分层和调用链

适用版本：V2当前代码；主链来自V1。

#### HTTP 入口与应用层

`backend/app/modules/chat/router.py` 保留 HTTP 责任：Pydantic 输入、登录依赖、至少选一篇文档、用户角色到 `include_restricted` 的转换、元数据约束推断、创建/检查会话、选择 Direct 或 ReAct、构建 `StreamingResponse`。

- `POST /chat`：完整同步 Direct 工作流被 `asyncio.to_thread` 包装，`wait_for(..., 120s)` 等待；这个入口不因为请求里的 `agent_mode=react` 而切成 Agent。见 `router.py:89`、`125`。
- `POST /chat/stream`：按 `agent_mode` 分流；Direct 分支在 `router.py:245`，ReAct 构造 thread/state 在 `266`、`293`；响应 content type 是 `text/event-stream`，设置 `Cache-Control: no-cache` 和 `X-Accel-Buffering: no`。
- `POST /chat/resume`：只恢复 ReAct 暂停的线程，见 `router.py:351`。
- `GET /chat/models`：从模型目录中筛选已配置 Key 的 provider；这是避免前端列出必然缺凭据的模型，不是模型在线健康检查。见 `router.py:44`。

`ChatTurnService` 负责会话生命周期而不是模型推理。`application/turn_service.py:24` 先校验会话归属，再读取旧历史，再写当前用户问题；需要 SSE 时预建 pending assistant，返回 `assistant_message_id`。通过依赖注入 repository，可以用假的存储实现验证调用顺序。

它解决了“读历史时把当前问题也读进去，拼 prompt 时又追加一次”的问题。已有会话每轮还同步当前选中的 document IDs。相关实现 `turn_service.py:34`、`39`、`55`、`62`。但这些 repository 调用分开提交，不能把它描述为包含会话、用户问题、assistant pending 的单一原子事务。

应用执行位于 `application/streaming.py`；SSE 编码和步骤字段映射位于 `api/sse.py`；生成位于 `rag/generation.py`；引用来源 badge 的归因位于 `generation/citations.py`；Direct / ReAct facade 位于 `orchestration/`。这是一种按职责拆分的应用分层，不需要夸称完整 DDD 或微服务架构。

#### Direct 的两种执行路径

`rag/graph/workflow.py:21` 编译普通工作流：

```text
START → load_documents → retrieve_context → check_evidence
                                      ├→ generate_answer → END
                                      └→ insufficient_evidence → END
```

`load_documents` 提供页面文本 fallback；`retrieve_context` 委托统一的 `RetrievalService`；`check_evidence` 暴露检索服务已经给出的判断，并没有重新让 LLM 判断。见 `rag/graph/nodes.py:31`、`41`、`57`。

同步 `/chat` 走完整图 `run_pdf_qa()`。Direct SSE 不先跑整张图再把整段答案切碎，而是 `DirectOrchestrator.retrieve()` 调用 `run_retrieval()`，拿到统一检索状态后，单独对模型 `astream()`。见 `orchestration/direct.py:12`、`rag/graph/workflow.py:51`、`application/streaming.py:324`、`356`。

分流规则在 `nodes.py:94`：充分证据可生成；policymaker 无证据必须拒答；researcher/student 的 chat 模式无证据仍允许生成，analysis 模式拒答。所谓 Direct 的“一次检索”指没有 ReAct 决策循环，不代表底层永远只发一次数据库查询——元数据放宽、地区补检、混合召回和 reranker 仍可能多次调用。

#### 为什么选 LangGraph

可以从项目需求解释：工具调用不是固定一次，存在人工审批导致的长暂停，且需要跨请求保留状态。显式节点、条件边、状态更新和 checkpoint 更适合把这些控制点放进可检查的图。不能只说“因为 LangGraph 很流行”。

当前并不是多 Agent 系统：只有一个研究决策模型循环，加上一个最终答案生成阶段。没有多角色 Agent 相互协商、独立规划器/执行器集群或分布式 Agent 调度器。

### ReAct 图：节点、状态、停止条件与失败处理

适用版本：V2当前代码；主链来自V1。

#### 五个业务节点和真实边

`rag/agent/graph.py:568`：

```text
START → agent → record_tool_call → tools ────────────────┐
          ↑                         │                  │
          └──── 非 prepare 的结果 ──┘                  │
                                    prepare_final_answer
                                             ├→ final_generation → END
                                             └→ insufficient_evidence → END
```

这里图节点共五种业务节点：`agent`、`record_tool_call`、`tools`、`final_generation`、`insufficient_evidence`；START/END 是图控制标记。六种是工具种类，不能把“六类工具”误说成“六个 Agent 节点”。

`agent_node` 在 `graph.py:215` 读取模型和预算，生成可用工具集合，把 system prompt 和本轮可见消息交给模型。`record_tool_call_node` 在 `475` 要求恰好一条已接受调用，并在执行前累加计数、提取 UI 说明与该决策消息的 token。`ToolNode(ALL_TOOLS)` 在 `581` 真正执行工具，工具用 `Command(update=...)` 回写消息和引用等状态。

`route_after_tools` 在 `510`：只有最后工具是 `prepare_final_answer` 才退出研究循环；analysis 且 `evidence_sources` 为空进入模板化拒答，否则进 final writer。普通搜索即使充分，也先回到 agent，让模型显式输出 prepare 步骤。

`final_generation_node` 在 `546` 不绑定工具，给模型研究轨迹和交接计划生成答案。应用层只把此节点的内容消息作为最终 token 发给前端；研究节点的工具调用不会混进正文。它用 `ainvoke`，LangGraph 的 messages stream 仍可捕获模型流事件，不能据函数名把它误判为“整段输出后伪流式”。见 `application/streaming.py:145–154`。

#### ReAct 中的 reasoning、action、observation

Action 是模型的结构化 tool call；Observation 是执行后的 ToolMessage；下一次模型结合 observation 选择下一动作。`decision_reason` 和 `reflection_on_previous_result` 是简短的用户可读摘要，不是私有 chain-of-thought。reflection 描述刚刚完成的前一步，由前后端同时挂在上一条步骤上，避免显示成新步骤自己的执行结果。见 `agent/prompts.py:37`、`application/streaming.py:172`、`frontend/src/pages/ChatPage.jsx:1032`。

“有可见推理轨迹”可以解释成“有动作理由、工具结果摘要、前一步反思”，不要宣传暴露/保存了模型全部内部思维。`prepare_final_answer` 只传 answer_plan 和 citation_numbers，不是让模型在工具参数里写最终长答案。

#### 状态生命周期与 reducer

`rag/agent/state.py:126` 的 `AgentState` 使用 TypedDict 描述结构，并非数据库表。重要字段分为：

| 生命周期 | 字段 | 合并/重置方式 |
|---|---|---|
| 对话累计 | `messages` | `Annotated[..., add_messages]`，按 LangGraph 消息规则合并 |
| 对话累计且有上限 | `web_pages_seen` | URL 去重，最多 50 条；最旧先丢弃 |
| 每个用户问题 | `tool_call_counts`、`citations`、`evidence_sources`、`turn_citation_keys`、`last_evidence_reason` | 普通 LastValue；新问题显式替换，工具内部手工合并 |
| 当前上下文 | 文档 IDs、model、modes、top_k、metadata_filters、is_admin、user_id | 新问题输入更新；resume 继续使用 checkpoint 中值 |
| 当前 assistant 身份 | `assistant_message_id` | 人机中断恢复时沿用，避免另起一条答案 |

不能把所有列表都配成 append reducer。若 citations 配成只能追加的 reducer，下一轮输入 `[]` 不会清掉上一轮来源，编号与充分性都会串轮。代码中的 `add_citations`、`add_evidence_sources` 是工具主动调用的普通 helper，只有 `messages` 真正在字段声明中注册 reducer。见 `state.py:33`、`47–60`、`136`；新轮重置见 `router.py:305–324`。

`tool_call_counts={"__current_turn__":1}` 是一个非空 reset marker；resume 传的是 Command，不重放该 reset。引用身份为 `(document_id, chunk_id, source_url)`，见 `state.py:20`。`turn_citation_keys` 存列表而非 tuple，是为了跨 checkpoint 序列化后还能恢复并比较身份。

`evidence_sources` 不等于“曾调用过哪些搜索工具”，而是“本轮充分检索且贡献了未被其他 tier 认领的引用身份”。最终再按答案中实际出现的 `[N]` 过滤来源 badge。这避免全库检索找回同一文档后错误显示增加了新证据来源。见 `agent/tools.py:121`、`325`、`396`，`generation/citations.py:6`。

#### 历史：DB 与 checkpoint 是两种存储责任

数据库 chat history 面向界面和普通上下文；checkpointer 面向图执行位置、工具消息、状态和中断。

- 新 thread 从 DB 最近历史播种；已有 thread 只追加当前 HumanMessage，避免重复加载。见 `router.py:268–291`。
- DB history 的 `MAX_HISTORY_TURNS=5`，repository 用最后 10 条消息，再按时间正序还原。它没有强制配对，也未按 complete status 过滤，异常/空 pending 行可能占窗口。见 `schemas.py:23`、`history_repository.py:314`。
- 已有 ReAct thread 的 messages 累积在 checkpoint。`_messages_for_current_turn` 隐藏旧轮工具轨迹，只保留旧用户/最终 AI 对话和本轮完整工具记录；这不是截断所有旧对话，也不是 checkpoint 压缩。见 `graph.py:186`。
- 网页搜索记忆跨轮保存真实 URL/title/turn_index，引用“上一轮第二个网页”时由代码解析，避免模型凭旧答案重新拼 URL；最多 50 条，因此不是永久完整网页历史。见 `state.py:74`、`tools.py:162`、`search_web`。

一个需坦诚说明的来源细节：page fallback citation 没有 document_id/chunk_id/source_url，而 Agent 用上述三元组去重，会把不同页面的 fallback citation 映射到相同空身份。这是值得完善的边界，不要说所有无向量 fallback 页都已具备稳定全局身份。

### 六类工具治理：Schema、权限、预算、升级策略、协议纠正

适用版本：V2当前代码；主链来自V1。

#### 工具 Schema 与可信参数

工具由 `@tool`、类型注解及 docstring 定义，框架产生模型可见 Schema。模型只负责 query、说明、选项、计划等业务参数；文档范围、用户身份、restricted 权限、当前引用等通过 `InjectedState` 从后端状态传入，调用 ID 通过 `InjectedToolCallId` 传入。不能让模型传 `is_admin=true` 获权。见 `agent/tools.py:243–257`、`332–343`、`572`。

| 工具 | 职责与关键行为 | 当前实现入口 |
|---|---|---|
| `search_internal_documents` | 搜索本会话选中文档，统一 RetrievalService，在线程中执行同步检索 | `tools.py:244`，`222` |
| `search_full_corpus` | 搜索整个可访问共享库；不是“仅选中文档之外的集合差集” | `tools.py:332` |
| `ask_user` | confirm / choice / freeform 三模式；choice 至少两选项；interrupt 后返回字符串 | `tools.py:403` |
| `search_web` | provider 搜索最多 5 结果，对网页片段 embedding/rerank，仅通过片段可升级为引用 | `tools.py:487` |
| `import_web_page` | 管理员共享入库；URL 或会话历史消歧；单独确认后写入 | `tools.py:572` |
| `prepare_final_answer` | 明确退出研究循环，交接计划/引用号给最终生成 | `tools.py:448` |

当前 HEAD 工具直接调用 `RetrievalService`，没有 PolicySearchCapability 包装层。`tools.py:222` 是兼容 adapter，并不是 MCP 远程客户端。

#### 预算不是只写在 prompt 里

默认 `search_internal_documents=5`、`search_full_corpus=1`、`ask_user=20`、`search_web=4`、`import_web_page=1`、`prepare_final_answer=1`；每字段允许 1–50。见 `chat/agent_limits/config.py:16`。

`policy.py:23` 根据 mode/role/本轮 counts 返回工具；达到预算的工具不再绑定给模型。`record_tool_call_node` 在执行前加一，所以即使工具失败，该次也消耗调用次数。新问题 reset，人工 resume 保留。管理员持久配置通过 `active_limits()` 取；每次 agent_node 读取一个快照，用同一份 limits 同时构造工具集合和 prompt，减少描述预算和实际预算不同步。见 `graph.py:224`、`agent/prompts.py:236`。

这不是成本预算或超时预算：没有按剩余 token/金额动态降级，也没有本图显式全局 deadline。默认工具次数多，仍应考虑框架递归步数和每轮最大执行时间；当前 API 没有显式传 recursion_limit。

#### 角色、模式和联网授权的不同强度

analysis 只绑定 selected search + prepare；chat 普通用户绑定除 import 外的工具，管理员可见完整工具集。入库工具内部再次检查 is_admin，真正副作用前又 interrupt 确认。见 `policy.py:12–39`、`tools.py:620`、`681`。

搜索升级 prompt 目标是 selected → 全库 → 网页，网页需用户明确请求或澄清同意。**硬约束只实现了一部分**：`_enforce_tier_order` 在 selected 本轮尚未调用时隐藏 full_corpus/web，用户显式联网例外；selected 执行一次后直接返回可用集合，因此 Tier2 已失败、用户已同意 Tier3 并没有被独立授权状态完整编码。见 `graph.py:160–183`。

模型规则里的“不联网”检测用于控制联网例外，但不等于从所有后续 tools schema 全面移除 search_web。`search_web` 内也没有注入的 web_authorized 判断。故不能说“提示注入或模型违约绝不可能未经授权联网”。若要改进，应把用户授权变成服务端状态与执行前 guard；这是建议，不是已实现。

特殊处理：analysis 检索后仅绑定 prepare；有文档证据且问题要求最新/网页核实，保留 web + prepare；地区约束不满足时可直接开放全库/澄清/prepare，避免同一错范围重复检索。见 `graph.py:241–281`。

#### 工具协议纠正与确定性 fallback

`graph.py:284` 绑定 `tool_choice="required"` 和 `parallel_tool_calls=False`。随后最多 3 次 `ainvoke`：

1. 模型没输出 tool call：补一条纠正消息再试；
2. 输出多条：只保留第一条，重建 AIMessage，并去掉 additional_kwargs 的原始 tool_calls，避免 parsed/raw 数量冲突；
3. 输出不在当前 allowed_tool_names 的工具：以 ToolMessage 提醒不可用，再试；
4. 三次不合规：构造一个确定性的 AI tool call，优先继续安全检索或交接答案。

见 `graph.py:302–379`、`382–465`。这套 retry 针对 tool-calling 协议，不是对所有 HTTP 429、工具超时、网络异常统一重试 3 次。参数字段错误的 Schema 校验仍由框架执行层处理，不能说本循环显式覆盖全部 schema 修复。

fallback 当前根据最后工具和充分性选择；`ask_user` 后如果 web 可用会选 search_web，没有代码解析用户回答是否否定。这再次说明仅靠 prompt/可见工具控制还不构成完整执行权限状态机。

`create_chat_client` 允许调用者设置网络 timeout/max_retries，但 Agent 默认调用没有传入这两个参数；不要把 LangChain/SDK 默认值说成本项目明确设计的生产重试策略。见 `core/ai/chat_models.py:27–55`。

### Checkpointer 与人机协作：恢复什么，不能保证什么

适用版本：V2当前代码；主链来自V1。

#### 初始化、线程标识、生命周期

`rag/checkpointer.py:13` 用 `AsyncPostgresSaver.from_conn_string`，调用库提供的 `setup()`，连接持有到应用 shutdown；不手写第三方 checkpoint 内部表迁移。`graph.py:600` compile 时绑定 saver，因此图采用 lazy 构建。`app/main.py:24–35` 在 lifespan 中先连接 DB，再初始化 checkpointer，退出时关闭。

Windows 在 `main.py:8–12` 切换 SelectorEventLoop，原因是 psycopg async 不支持默认 ProactorEventLoop。它解决的是驱动兼容，不是性能优化。

应用的普通业务 DB 已有连接池，但 checkpointer 使用自己的长生命周期连接上下文；不能据此声称 checkpoint 也自动用了新增的业务连接池。

#### interrupt / resume 的完整闭环

`ask_user` 执行 `interrupt({type,mode,question,options})`。图流收到 `__interrupt__` 后，应用先将 interrupted 标记为 true，再发同型 SSE 并关闭本次响应。先设标记很关键：若前端收到提示马上断开，清理逻辑不能把可恢复的 pending assistant 标成 error。见 `tools.py:441`、`application/streaming.py:157–167`。

客户端用相同 session_id 调用 `/chat/resume`，后端检查归属；检查 state.next 非空，否则 409；用 `Command(resume=answer)` 继续同一 thread。原 assistant_message_id、citations、计数和模式来自 checkpoint。见 `router.py:360–384`。

恢复不是把 Python 进程内存栈原样复活。LangGraph 会重新进入包含 interrupt 的节点/工具，按中断顺序消费恢复值。因此 interrupt 前逻辑需要可重放，多个 interrupt 的顺序需稳定，副作用应放在授权之后并做好幂等。

网页入库可能先 interrupt 让用户从真实候选页面中消歧，再 interrupt 确认永久写入。两者都来自工具自己，避免模型编造候选标题导致第二轮仍无法匹配。见 `tools.py:633–692`。

#### 新问题、停止、断线、进程崩溃分别是什么

- **人工暂停**：checkpoint 留下 next，pending assistant 仍可恢复，不发正常 done。
- **用户发新问题替代暂停任务**：旧 pending assistant 标记失败，新问题从 START 开始，重置本轮状态。见 `router.py:274–281`。
- **前端 Stop**：AbortController 取消当前 HTTP fetch，不是调用一个持久 Agent cancel API；也不能等同于业务 interrupt/resume。
- **普通断线**：驱动在 GeneratorExit 分支尽量保存已流出的部分答案并标记 error。见 `streaming.py:280–300`。
- **进程被杀**：每个工具步骤此前有持久化，但正文并非每 token 写数据库；不能承诺崩溃后所有已显示文本都已保存、任务会自动继续。

当前驱动显式处理 GeneratorExit/常规 Exception，没有专门处理 asyncio.CancelledError（它是 BaseException）。实际 ASGI 的取消路径不一定只表现成 GeneratorExit。因此“所有断线/取消路径必然正确回写状态”仍需专项验证，本知识库未做该验证。

#### 幂等、并发与权限恢复边界

当前 resume 请求只有 session_id 和 answer，没有用户请求幂等键、指定 interrupt ID 或 CAS 版本。`aget_state → 检查 next → 执行 resume` 之间也没有 session 排他锁。多标签页/客户端同时恢复存在静态竞态风险；不能说有 exactly-once 执行保证。

网页入库有 canonical URL / SHA-256 去重与唯一约束，可以降低重复文档；不是网络抓取、embedding、元数据模型调用都只执行一次。入库使用异常清理补偿，也不是跨 DB/文件/网络的一次原子事务。相关 `documents/service/pipeline.py:save_web_import`、`documents/repositories/documents.py:create`。

resume 重新检查会话归属，但 is_admin/include_restricted 使用暂停时 checkpoint 的值；没有完整的角色撤销重验证流程。管理员在暂停期间降权后的副作用授权边界不应凭空保证。

UI 的 pendingConfirm 主要在 React 状态中；历史加载恢复正文/steps，但没有重新查询并重建 interrupt 选项。后端可持久恢复和浏览器刷新后必然还原原确认对话框，是两个不同能力。

### 证据充分性与引用：可追溯不等于逐句已验证

适用版本：V2当前代码；主链来自V1。

#### 当前 gate 的技术含义

`retrieval/evidence.py` 的默认 fallback 参数：最小上下文 200 字符、最大 cosine distance 0.45、reranker floor -7。实际阈值从 embedding / reranking provider 配置读取，因此不同 provider 不能无条件共享固定数值。

`is_chunk_relevant` 的规则：距离达标时还需已提供的 reranker score 达标；未提供 reranker score 不自动拒绝。距离没过时，英文词覆盖作为 backstop：至少 2 个有效词且 coverage≥0.30，并需要已有 reranker 达标；没有 reranker 时要求至少 3 词且 coverage≥0.60。见 `evidence.py:213`。

显式英文政策名称做 distinctive term 检查；词面通过时，默认额外发一次 LLM YES/NO veto，识别明显属于不同国家/机构的政策。该调用使用默认生成模型、temperature=0、max_tokens=10，并非保证使用便宜小模型；异常时 fail-open。见 `evidence.py:152–182`、`185`。因此 docstring 所谓 deterministic gate 不是全部逻辑都无 LLM。

gate 主要证明“有一定相关材料”，没有严格证明答案每个 claim 都由材料蕴含；200 字符也不是对跨地区比较、时间更新、例外条款等问题的充分性证明。英文 regex 对中文、别名、改写有局限，LLM veto 也会误判或在失败时放行。

多主题拆问目前主要由 prompt 指导模型完成，没有显式的子问题列表、逐子问题完成标记或 claim-to-evidence coverage map。`evidence_sources` 非空就被应用层报告为充分，也可能只是其中一个子主题拿到材料；后一次更新核实失败时，前面的文档证据仍可保留。因此“有引用来源”不等于“用户提出的每项要求都已验证”，也没有通用的新旧政策冲突裁决器。

网页 gate 是单独实现：网页结果切块后批量 embedding，每个结果保留与 query 最近的一个块，再做距离筛选和可选 rerank。reranker 没给分会丢该结果；reranker 抛异常则退回 cosine。见 `agent_tools/web_evidence.py:25–97`。它复用了阈值，但没有完全复用文档 gate 的长度、英文词覆盖、命名政策和多地区约束，因此不要说“网页和文档执行完全相同的充分性检查”。

#### 引用生成、编号与前端落点

引用由服务端检索结果生成，而非模型编造 bibliographic 字段。向量 chunk 引用含 document_id、chunk_id、title、page_start 对应的 page、text[:500]；无向量 page fallback 为 title/page/quote[:300]。见 `retrieval/service.py:_citations`。

Agent `_number_citations` 读取已有身份到编号的映射，重复来源复用编号，新来源顺序增号。只有充分结果加入本轮 citations；弱结果仍作为 observation 供研究模型反思。模型工具结果带完整 chunk text，history/API quote 保持紧凑。见 `agent/tools.py:52–118`、`289–328`。

final writer 提示词要求使用准确 `[N]`，prepare 工具的 `citation_numbers` 没做编号存在性验证，最终文本也没有 claim-level entailment 检查。`generation/citations.py` 的 regex 仅据引用号决定显示哪个 evidence tier badge，不负责修复或拒绝虚假引用。

前端 `ChatPage.jsx:61–106` 用正则将 `[1]`、范围/并列标记变成可点击上标；以第一个号码减一定位 citation 数组。超出范围就保留普通文本，不强制阻断错误答案。抽屉显示标题、页码、片段和文档/网页入口。抽屉 quote 展示最多 400 字符，见 `ChatPage.jsx:2263–2308`。

chunk 可跨页；引用当前只返回起始页，没有精确选出支持当前结论的句子页码、字符 offset、PDF bounding box。所以“文档、页码、原文片段可追溯”合理；“每条事实都精确定位到正确页和原句且已机器验证”不合理。

#### 不同知识边界下的无证据行为

analysis 模式只选中文档，失败走模板化拒答。chat 模式 prompt 明确允许标注后的模型常识；因此 evidence_sufficient=false 的答案不一定是拒答。policymaker 虽在 UI 中被移除，但后端为兼容仍接收，并强制 answer_mode=analysis。见 `rag/graph/state.py:7`、`rag/prompts.py:122–159`、`rag/agent/prompts.py:169`。

这应成为面试时的准确产品定义：平台提供证据优先和可追溯输出；并非所有开放讨论回答都要求有文档依据。

### SSE 与 React：真实协议、状态推进与体验取舍

适用版本：V2当前代码；主链来自V1。

#### 为什么用 fetch 的 SSE，不是 WebSocket

当前交互主要是服务端向浏览器连续发送 token/工具状态；用户下一次输入可用新的 POST 请求。SSE 的 HTTP 响应和代理部署简单；双向长连接不是此实现的必需。因为请求有 JSON body 和 Bearer header，前端使用 `fetch` 的 ReadableStream 手工解析，而不是原生 EventSource。

`frontend/src/api.js:260` 构造 POST、JSON、Authorization 和 Abort signal；`278` 的 `readSSEFrames` 用 TextDecoder 保持 UTF-8 跨字节片段状态，缓冲后按空行切帧，保留末尾不完整帧；只接收 `data: ` 后面的 JSON。服务端 `api/sse.py:7` 输出 `data: JSON\n\n`。

这里 SSE 是传输协议，payload 的 type 是应用事件类型。没有 SSE `id:` / `event:` 字段、heartbeat、Last-Event-ID、自动重连与漏帧重放。解析器也不是通用完整 SSE parser：多行 data、CRLF 等外部格式未全面适配；它与本项目固定 encoder 配套使用。

#### 事件表与流顺序

| 应用 type | 含义 | 关键字段 |
|---|---|---|
| `tool_call` | 接受工具动作、显示运行步骤 | tool、query、decision_reason、reflection、tokens_used |
| `tool_result` | 紧凑 observation 摘要 | tool、result_count、source_titles、evidence_sufficient、reason、filter_* |
| `token` | 最终回答内容片段 | value；是字符串 chunk，不等于一个 tokenizer token |
| `ask_user` | 人工澄清暂停 | session_id、mode、question、options |
| `confirm_import` | 永久入库确认暂停 | session_id、url、title、question |
| `citations` | 回答元数据/来源 | data、evidence flags、modes、session_id、resolved model；ReAct 有 token_usage |
| `answer_done` | 正文完成，停止正文光标 | suggestions_pending |
| `suggestions` | 验证过的后续问题 | items |
| `done` | 本次响应全部完成 | 无额外正文 |
| `error` | 已发出流后的应用错误 | message |

正常 ReAct：若干 tool_call/result → token → citations → answer_done → 可选 suggestions → done。人工中断：tool_call → ask_user/confirm_import → 关闭响应，等待另一个 POST resume。Direct 不发研究工具 trace，仍共用 token/citations/answer_done/suggestions/done。

回答必须先 finalize 数据库，之后发 citations，再跑建议尾部；建议失败不会把已完成答案改成失败。`answer_done` 与 `done` 分离，目的是避免正文已结束、后续问题仍生成时前端光标持续闪烁。见 `streaming.py:224–278`、`46–114`。

后续建议不是把模型随便生成的几个问句直接展示：先 LLM proposal，再清洗去重/排除历史问题，再用选中文档检索验证可回答性。最多等 45 秒，异常则返回空列表。见 `suggestions/generator.py:122–207`。建议模型调用不计入当前 ReAct state token 汇总。

#### React 消费协议

`consumeAgentStream` 是新问与恢复共享的状态更新器，见 `ChatPage.jsx:1025`。收到 tool_call 时确保最后存在 assistant placeholder，追加 running step；tool_result 逆序找到匹配 running step，标 done；token 追加正文，并在第一段正文到来时自动折叠 trace，但不持续覆盖用户后续展开动作。

收到 ask_user/confirm_import 后记录 pendingConfirm、设 paused，但继续读到服务端关闭，避免 checkpoint 尚未关闭就立刻发送 resume。见 `ChatPage.jsx:1108–1114`。confirmSubmissionRef、busy、confirmBusy 三者防止界面重复提交；这是客户端防抖，不等于服务端并发幂等。

停止按钮调用 abort；异常时保留已有正文或有步骤的 placeholder；finally 清除 busy 和 streaming，暂停时保留等待状态。见 `1187`、`1203–1279`。历史恢复把 DB snake_case 转为界面字段，并恢复最后答案的 answer/agent mode；老 policymaker 会话在界面回到 researcher + analysis。见 `772–809`。

元数据过滤 mismatch 提示在步骤过程中先出现；后续某 tier 真正满足约束后可以清除，最终 citations 事件为权威终值。前后端都按相同 set/reset 规则执行。见 `streaming.py:136–141,182–195`、`ChatPage.jsx:1062`、`1132`。

界面实现需要承认仍然庞大：`ChatPage.jsx` 同时包含历史、引用、确认、stream 状态、trace 和布局；后端完成职责提取不代表前端已全部组件化/状态机化。当前前端测试文件主要是上传，不能说上述 SSE/恢复交互都已有端到端自动测试。

### 当前可观测性：已经有的与还没有的

适用版本：V2当前代码；主链来自V1。

HEAD 已将每个工具动作和结果摘要写入 chat_messages.reasoning_steps，再用同样结构恢复历史。`api/sse.py:49` 定义 running step；`64` 完成匹配步骤；`streaming.py:175–198` 每步持久化。

每步 tokensUsed 来自选择该工具的 AIMessage.usage_metadata，不是这个工具内部全部花费。例如 search 工具内部命名政策校验可能另发模型请求，该成本不会因此自动归到此工具。见 `graph.py:485–505`。

`core/ai/token_usage.py:4` 只累加最后一个 HumanMessage 后、真正保存在 state 中的 AIMessage provider usage。缺失 usage 不估算；无可信数据返回 `{}`。ask_user 的恢复结果是 ToolMessage，不会另加 HumanMessage 把聚合截断；final writer 的 style reminder 只在本地调用消息中追加，不写入 checkpoint messages。

**汇总仍非全账单：**协议纠正的失败响应只在 agent_node 的临时 messages 中，不返回 state；命名政策 LLM veto、后续建议、入库元数据抽取可能不在这个累计链；Direct 的 StrOutputParser/文本流未传递 usage 到 finalize。没有每一模型调用的统一 tracing hook。

HEAD 没有独立 run_id/事件仓库/TTFT 事件/管理员 run 查询 API。已有工具步骤可追踪与“全链路所有模型和工具耗时、token 均有持久化”不是同一个完成程度。

当前 HEAD 的 async 改善可直接讲：`d52fdfc` 把 Agent 的 resolve_generation_target、create_chat_client、active_limits 和最终生成的相同同步设置/构造操作放到 `asyncio.to_thread`；`generate_answer_streaming` 也这样处理。原因是这些同步路径可能访问 DB/配置，async 函数内直接调用仍会阻塞事件循环。`to_thread` 不保证 Python CPU 计算获得真正并行，也不代表 wait_for 超时可以强杀已经运行的线程。

Direct 只给检索部分设置 120 秒等待，随后最终生成没有应用层统一总超时；ReAct 驱动虽然捕获 TimeoutError，但并没有自己给整张研究图设 deadline。可以说“有部分阶段超时”，不要说“所有问答统一 120 秒硬终止”。

<a id="kb-06"></a>

## 06. 网页搜索、永久入库、去重与知识治理

### 永久网页入库、去重、权限与生命周期

适用版本：V2／V1；网页处理未全面任务持久化。

#### 临时搜索证据和永久知识不同

临时网页搜索/fetch可以供本轮回答使用；永久导入才创建共享库文档、生成chunks/vectors并记录治理信息。HTTP管理员导入和Agent导入共同调用 `WebImportService.import_page`，见 `documents/web_import.py:75/:100`。Agent工具先验证is_admin，且有独立confirm_import interrupt，见 `chat/rag/agent/tools.py:618/:681`；WebImportService内部并不验证管理员，它是可信应用层接口，身份约束依赖HTTP/Agent调用入口。

当前普通管理员文件上传进入durable任务；**网页导入仍走 save_upload默认durable=False，然后 await asyncio.to_thread(process_document)**，见 `documents/service/pipeline.py:356/:391/:412`。它不是同一套已持久化异步网页抓取任务队列，不能把10月文档任务增强泛化为所有网页导入都可断点恢复。

#### URL身份与SSRF

normalize_web_url只接受http/https，拒内嵌user:password；scheme/host小写、host尾点去除、默认端口去除、fragment去除，path/query保持，以免把不同资源错误合并，见 `web_import.py:46`。最初请求URL和provider返回的不同canonical/redirect URL都执行public地址验证，`:100`。

public验证异步DNS解析所有返回IP，只允许 `ipaddress.is_global`，拒loopback/private/link-local等，见 `web_search/url_security.py:11`。这是重要SSRF基础边界，但没有把DNS验证结果绑定到最终socket，也不能保证第三方fetch provider每一跳redirect都按同一策略验证，因此不能声称完全防住DNS rebinding或所有redirect SSRF。

抽取后content必须非空，UTF-8大小<=**2 MiB**，标题<=**200字符**，见 `web_import.py:22/:133`。该2MiB限制作用于provider返回内容，不等于本应用控制第三方在远端抓取原网页的所有字节或费用。

#### 四种重复身份与保守L3

- URL身份：canonical_url优先，兼容旧source_url；数据库唯一约束及异常映射处理并发竞争，见 `documents/repositories/documents.py:38/:134`。
- L1：文件字节SHA-256，拒同字节上传；网页不同URL返回同Markdown字节时转为复用已有文档。普通上传重复409，与有同一幂等key的重放成功是两种语义，见 `admin_router.py:123`、`pipeline.py:398`。
- L2：归一化全文空白、lowercase后SHA-256，识别重新排版的文本重复。见 `documents/file_store.py` 的 normalized_content_hash，以及 `pipeline.py:413`。
- L3：网页文本>=**1200字符**才取头/中/尾区域，window=`min(2000,max(600,len//4))`，每区向量查全库top8，排除自己，仅保留cosine distance<=**0.05**的文档；所有区域候选的document_id取交集，按距离和选最近。见 `pipeline.py:291/:304/:319`。

L3试图避免仅共享开头或模板语句就删掉新政策；distance0.05约相似度0.95，但这只是保守启发式。ANN漏召回、短文、不同模型分数、某文档在同一次top8中多个chunks覆盖等都会影响结论；没有全库近重复ground truth评估。L2/L3应用于网页导入后的保留决策，普通文件上传不是每次都执行相同的删除去重。

网页被识别为重复则删除新文档并返回旧记录；处理异常会尽力清理新文件和记录；成功后显式站点/用户title覆盖生成title，避免LLM悄悄改名，见 `pipeline.py:421/:432/:440`。这是应用层补偿清理，不是跨数据库、文件系统、外部provider的一个真正ACID事务。进程在补偿之前崩溃仍可能留下中间状态。

#### 治理记录不等于自动更新爬虫

web_document_governance保存active/stale/archived、refresh_interval_days、last_fetched_at、next_review_at、last_refresh_error、created_by；导入成功后register_import更新抓取时间和下次review。见 `documents/repositories/web_governance.py:11`。service校验刷新间隔1–3650天，`documents/web_governance.py:38`。

管理员可按status/due_only查看并PATCH。archived将documents.approved=False，保留审计/历史数据，但普通用户dense/BM25/目录不再可见；恢复active/stale会设approved=True。见 repository `:62/:96`、`documents/admin_router.py:175/:188`。这涉及同一approved字段，不能把治理status与独立审批体系混为完全隔离。

当前未看到定时调度器自动重抓、正文diff/版本替换、到期自动stale、ETag/Last-Modified条件抓取或废止法规验证；due_only是查询条件，refresh_interval是治理安排，不是已执行的自动刷新承诺。归档文档管理员仍能include_restricted检索，这是角色边界，不是物理删除。

<a id="kb-07"></a>

## 07. 十月改造：数据库连接池与有界上传

### 为什么需要连接池，改的到底是什么

V1 的 Repository `get_connection()` 在每次访问时建立 psycopg 连接。V2 的 `7aaf075`（2026-10-15，Alem42）将其改成同进程共享 `psycopg_pool.ConnectionPool`。业务 Repository 仍使用上下文管理器借连接，但底层网络会话可以复用。正常退出提交、异常回滚，之后归还池；不是每次关闭底层连接。

默认配置是 min=1、max=5、借用等待 2 秒、最多 20 个排队借用者、建连超时 3 秒、启动等待 5 秒。池饱和产生 PoolTimeout／TooManyRequests／PoolClosed 时转换为 `DatabaseUnavailableError`，HTTP 返回 503 和 `Retry-After: 1`。管理员接口 `GET /api/v1/admin/database-pool` 返回每进程的配置和运行统计，不返回密码或 DSN。

五个连接不是五个用户，也不是每秒五次请求。一个请求可能多次借用，文档查询列表和数量还可能并行占用两个连接。后台任务与用户查询共享 Repository 池。SQL 的慢查询、锁等待和持有时间都会影响排队；借连接的 2 秒等待不是 SQL statement timeout。

LangGraph 的 `AsyncPostgresSaver.from_conn_string()` 使用另一条长期异步连接，库内部协调访问；项目保留的 SQLAlchemy 异步 session API 也有自己的管理。因此 max=5 不是整个进程访问 PostgreSQL 的总连接上限。多进程时还要乘以进程数，并为 checkpointer 和其他服务留预算。

核心代码：`backend/app/core/database.py:24–142`；`backend/app/core/config.py:27–44`；`backend/app/main.py:56`；`backend/app/modules/system/router.py`。Git 证据：`7aaf075` 修改 34 个文件，包含实现、配置、前端联动和测试；1561 行增加／108 行删除包含文档，不能直接当性能收益。

### 完整上传请求与内存边界

浏览器仍以 **一个文件一次 multipart POST** 上传。前端先获取 `/documents/upload-limits`，检查整批文件，防止第一份已上传才发现第二份超限。后端独立限制，不信任前端校验。

上传保护分三层：前端预检；ASGI middleware 根据 Content-Length 提前拒绝，并在接收过程中累计实际 body 大小；保存器检查实际文件大小和内容。默认文件上限 20 MiB，multipart 额外预算 256 KiB，保存缓冲 1 MiB。它不是浏览器分片上传，更没有分片序号、断点续传和服务端合并协议。

FastAPI 已将 multipart 文件放入 UploadFile／spooled file。应用保存阶段在线程池中分块读取这份文件，边写 `.part`、边累计大小和 SHA-256，并检查扩展名及文件内容特征。这样去掉应用阶段的整份 bytes 副本，不等于互联网链路上绝不缓存、也不等于大文件内存为零。合法完整文件才发布到目标目录；普通失败及重复路径清理暂存文件。

代码：`core/upload_limits.py`、`documents/file_store.py:49–150`、`documents/service/pipeline.py:197–295`、`frontend/src/api.js:211`、`frontend/src/components/DocumentUpload.jsx`。测试：`test_upload_streaming.py`、`test_database_pool.py`、`frontend/tests/upload.test.js`。

### 线程卸载的目的与限制

登录／注册的同步工作、文件保存、Repository 调用和部分模型客户端初始化改为在线程中执行，避免阻塞 FastAPI 事件循环。线程卸载改善的是异步服务的可推进性，不保证 CPU 密集 Python 代码变快；OCR、本地模型仍会争夺 CPU、RAM 和原生线程。连接池、线程池和文档 worker 是三种不同资源，不能混称“池里有五个解析 worker”。

<a id="kb-08"></a>

## 08. 十月改造：持久任务、租约、原子发布与幂等

### 从内存待办到 PostgreSQL broker

V1／第一阶段的 `processing_queue.py` 使用 `asyncio.Queue`，只保存在进程内；固定槽位可以限制本进程任务，但重启会丢失待办，多个进程无法共同协调同一任务。V2 的 `d52fdfc` 改成 PostgreSQL 持久任务，沿用了部分原类名作兼容，但底层不再把内存队列作为事实来源。

上传完成后，文档记录、处理任务和可选请求幂等登记在同一数据库事务中提交。worker 轮询数据库领取任务，`asyncio.Event` 仅用于本进程唤醒加速；即使通知丢失，下次轮询仍能找到任务。默认三个 worker／进程、1 秒轮询、30 秒租约、5 秒心跳、最多三次自动尝试、基础退避 2 秒、单次等待上限 300 秒。

持久任务类型是 ingest 和 reembed；rescan 是管理操作，重新登记 ingest 任务，不是独立的第三种 task_type。任务状态为 queued、running、succeeded、failed；文档状态则反映 uploaded、ocr、parsed、annotated、ready 等处理阶段。两种状态的用途不同。`processing_jobs` 是尝试日志，不是持久待办的替代品。

核心代码：`documents/repositories/tasks.py`、`documents/processing_queue.py`、`documents/worker.py`、`documents/upload_registration.py`、`documents/service/pipeline.py`。提交 `d52fdfc` 涉及 33 文件，1819 行增加／259 行删除；随后还有状态与日志修正提交，见历史章节。

### 如何避免两个 worker 同时领取同一任务

领取采用短事务：选择可执行 queued 任务，或者租约已过期且仍有尝试次数的 running 任务，通过 `FOR UPDATE SKIP LOCKED LIMIT 1` 锁定候选，再更新为 running，增加 attempts，记录 worker_id、随机 lease_token 和 lease_expires_at。其他 worker 跳过锁定行，继续找别的任务。

行锁只覆盖领取或提交阶段，不贯穿 OCR、Embedding 和模型网络调用。把这些长计算放在事务外，避免长时间占用数据库连接与行锁。`SKIP LOCKED` 帮助不同 worker 分担任务，不承诺严格全局 FIFO，也不是消息中间件的所有能力。

数据库时间 `clock_timestamp()` 用于租约判断，减少不同进程本机时钟差异。心跳仅在任务仍 running、lease_token 匹配且租约尚未过期时续租；已过期的旧持有者不能通过迟到心跳复活租约。相关代码：`repositories/tasks.py:48–127`。

### worker 挂掉后怎样恢复，旧 worker 为什么不能覆盖新结果

worker 挂掉后停止续租。租约到期，其他 worker 可重新认领并获得新 token；若已耗尽最后一次尝试，任务及文档被标记失败，并结束遗留的运行日志。claim、fail 和重试相关提交还修复了 reembed 状态以及上次尝试日志一直 running 的问题。

长计算结束前，发布结果进入 `owned(task)`，再次检查任务状态、token 和租约，并对任务行加锁。没有有效资格则抛 `LostTaskLease`，丢弃迟到结果。这是基于租约令牌的提交资格保护：允许异常边界出现重复计算，但阻止过期 worker 发布覆盖现有结果。

资格检查发生在发布事务入口，后续由该任务行锁保护提交，不是每条 SQL 都重新检查截止时间；短事务执行中租约时间可能经过，但其他认领者不能同时改掉这条受锁记录。因此“租约保护”不能说成到点强制中断数据库事务的硬实时机制。

**不能声称 exactly-once 执行。** 网络分区、长停顿和线程超时可能让两个尝试先后或短暂并行计算；框架取消 `asyncio.to_thread` 的等待不会强杀其底层线程。当前保证侧重“谁有资格提交”和结果收敛。默认三个 worker 是正常调度槽位，不能保证极端超时场景永远只有三个底层线程仍在算。

### 事务边界与原子发布

完整入库先在事务外抽取原文、生成元数据和 contextual header、分块并计算向量。最终在一个受租约保护的事务中替换页面、生成元数据、内容 hash、chunk 和向量，将文档标为 ready，结束 processing job，并将 task 标为 succeeded。中间步骤失败时，该次最终发布不留下“索引一半成功、任务已完成”的状态。

rescan 与 reembed 不同：rescan 重新解析／分块，会替换 chunk，可能使旧 chunk ID 失效；reembed 复用现有 chunk，只重建当前模型空间的向量。`8fe3487` 修复 reembed 失败重试时不应回到完整文件上传式生命周期。

Embedding 的 `snapshot()` 使用 ContextVar 固定单次尝试的配置和 provider；写向量时使用与该次计算一致的目标表／维度／模型，防止管理员切换模型后将旧向量写入新空间。它不提供跨进程配置广播；独立 worker 仍可能需要重启或后续版本通知机制。

数据库事务不能回滚已经完成的 HTTP 调用和文件系统动作。文件先发布后 DB 提交之间存在故障窗口。异常处理会查询注册结果，普通确认未注册时清理；如果 COMMIT 结果不确定，宁可保留可能已注册的文件。这里不能声称文件＋DB＋外部模型具有全局原子性。

代码：`pipeline.py:49–193`、`embedding/service.py:83`、`upload_registration.py:100–127`。

### 请求幂等、文件去重和处理幂等分别解决什么

| 机制 | 键／身份 | 解决的故障窗口 |
| --- | --- | --- |
| 文件去重 | SHA-256；Web 路径还可能有 canonical URL／正文 hash／语义相似检查 | 不同请求重复提供同一内容，防止重复文档。 |
| 上传请求幂等 | actor_id + Idempotency-Key；内容指纹包括文件 hash、文件名、元数据和来源 | 服务器已提交，但响应丢失，客户端重放同一业务请求。 |
| 任务执行收敛 | document/task 身份、活动任务约束、lease_token、替换式索引发布 | worker 崩溃、失联、重试、迟到结果。 |

`register_staged_upload()` 对 actor＋key 获取事务级 advisory lock，检查旧登记。同 key 同 fingerprint 返回原文档 ID 和 task ID；同 key 不同输入返回 409。文档、任务与请求映射在同一数据库事务内登记。同文档不能并存多个 queued/running 活动任务；不同类型活动任务冲突明确报错。

前端用 WeakMap 给选中的 File 对象保存 UUID，重试同一对象沿用 Key；刷新页面或重新选文件不保证沿用，因此不是跨浏览器持久请求日志。幂等重放仍可能需要重新传输文件并计算 hash，它保护业务登记，不自动节省网络传输。

手动重试对 queued/running 返回原任务，保持重复点击幂等；只有 failed 才重新排队并增加后续可尝试预算，succeeded 不允许重试。它不是无限自动重试。管理员可以查看任务列表与错误并操作 retry；接口主动去除 lease_token，避免将执行资格凭据下发前端。代码：`upload_registration.py:25–105`、`repositories/tasks.py:180–218`、`task_router.py`、`frontend/src/api.js:211–230`。

### 独立 worker、关闭与剩余限制

API 内默认运行三个 worker；设置 `DOCUMENT_TASK_WORKERS=0` 后，可用 `python -m app.modules.documents.worker --concurrency 3 --warmup` 启动独立进程。warmup 在领取任务前加载当前模型，避免首次加载耗时吞掉任务等待预算。每个进程有自己的 Repository 连接池；任务领取通过数据库协调，但多机器仍需要共享原文件存储。

停止时给 worker 最多 10 秒收尾，然后取消等待。未完成任务不会从数据库删除，依靠租约过期恢复。尚未实现对象存储、Redis、Celery、跨机故障调度、任务保留期和完整按租户限流。网页永久导入仍有直接调用处理函数的路径，不能把所有 Web Import 都称为已完整接入持久任务。

<a id="kb-09"></a>

## 09. 十月排障：迁移检查与可选模型等待预算

### 服务启动成功但 worker 一直报错的原因

2026-10-15 的已有故障记录表明，本机项目库有原用户和文档，却没有新任务表。连接测试正常不代表代码需要的 schema 已完整。旧启动过程启动 worker 后才出现 `UndefinedTable` 并不断重试，上传和任务管理也因此不可用。

`568ff2d` 增加 API 与独立 worker 的启动检查，缺 `document_tasks` 或 `document_upload_requests` 就停止并提示迁移命令。`python -m app.modules.documents.migrate` 读取与服务相同的配置，只执行 028 durable migration，在一个事务中完成 DDL、索引和未完成文档任务补登记，使用 advisory lock 串行化该迁移。设置局部 lock_timeout=5 秒、statement_timeout=30 秒，失败整体回滚。它不是通用的全部迁移管理器，也不检查所有历史 schema。

现有库不能重跑包含 DROP 的 `database/init.sql`。Compose 的 initdb.d 仅在新数据卷初始化时运行，重启已有卷不会自动补迁移。源码：`documents/schema.py`、`documents/migrate.py`、`main.py`；文档与证据：`docs/DATABASE_RUNTIME_REPAIR_2026-10-15.md`。

### 心跳正常不代表业务一定在推进

补齐表后，真实 PDF 上传能登记和被领取，心跳也持续续租，但处理长时间停在 parsed／annotated。历史诊断通过线程栈发现正在等待可选元数据和 contextual header 的远程模型，数据库连接反而空闲。因此调大连接池不能解决这次停顿。

`fc53841` 为两项可选增强增加独立预算：元数据网络超时 15 秒、模型阶段等待 30 秒、最大输出 1024 Token、自动重试 0；contextual header 每请求 10 秒、整批阶段等待 20 秒、输出 128 Token、重试 0。元数据使用共享三线程池；contextual header 每批最多六个并行子调用。

元数据失败退默认值；header 失败则空 header，继续用原 chunk 生成向量。已及时完成的 header 保留并保持 chunk 顺序。网络 timeout 与阶段 deadline 处理不同层级：前者约束网络操作等待，后者约束业务等待结果的时间。线程无法强杀，迟到结果被弃用；不能说未来任务取消已经硬终止所有请求。用户聊天客户端没有因此统一改成相同预算。

<a id="kb-10"></a>

## 10. 前端、身份认证、配置与Docker交付

### 前端如何承接研究流程

当前前端为 React 19、Vite 7、React Router 与 MUI。App 层协调身份、文档列表、选中文档和当前会话；文档库用于搜索与筛选，详情 drawer 查看元数据和 chunk；ChatPage 将资料篮、近期会话、工具轨迹、流式文本、引用和人工确认串起来。路由使用 lazy 页面加载，支持 `/chat/:sessionId`，便于返回指定会话。首页组件保留不意味着它仍是默认入口，当前 index 重定向到 chat。

引用面板展示来源标题、页码和 quote，并关联文档详情／文件；浏览器可复制或导出答案。显示来源信息是可核查性入口，不自动构成后端已验证每个 claim。管理端还提供模型 capability、Embedding、Reranker、分类、建议问题、Web Search、邀请与 V2 任务列表。

前端上传轮询用于展示业务状态，并不执行后台解析。V2 的 DocumentTasks 展示 queued/running/failed/succeeded 与重试；请求键由前端维护但真正幂等由后端事务保证。脚本 `frontend/tests/upload.test.js` 只覆盖上传边界和请求键，不是整个浏览器 UI 的端到端自动化。

### 认证实现与管理员邀请演进

密码使用随机盐与 PBKDF2-HMAC-SHA256、120000 次迭代；比较摘要使用 constant-time compare。访问 Token 是项目自定义的 `base64url(payload).base64url(HMAC-SHA256 signature)` 两段结构，载荷有 sub、username、role、exp，默认 24 小时。**它不是标准三段 JWT，也不是 OAuth2/OIDC 集成。** 服务端验签、验时效后重新查用户，使用数据库中的当前角色做授权。

应用签名密钥可由配置指定，否则首次运行随机生成并保存文件，重启后复用。前端 Token 存 localStorage，说明身份机制时可如实指出此实现，不能称已具备 HttpOnly Cookie、Refresh Token、细粒度 RBAC 或单点登录。

8 月曾引入邮件验证，但 8 月 10 日交付加固改为管理员单次邀请，不再要求邮件验证码；email 是可重复联系信息，username 唯一并用于登录。首个管理员由 host operator 执行 bootstrap 生成七天有效邀请；已有管理员后关闭 bootstrap。邀请在库中保存 hash，创建管理员与消费邀请在事务中完成。后续管理员可创建和撤销邀请。邀请凭证与用户上传请求的 Idempotency-Key 是不同机制。

代码：`auth/service.py:17–143`、`auth/dependencies.py`、`auth/invites.py`、`auth/repository.py`。关键提交：`417fe97`（历史邮件验证）、`1739b83`（Alem42，邀请注册）、`4ae674b`（管理端邀请）。

### 模型目录与密钥配置

项目把 provider 身份、模型／endpoint 元信息和运行 Key 分离。模型目录按 chat、embedding、rerank 等 capability 查询；管理员可添加兼容接口，聊天支持 `provider/model` 每消息选择，前端只列出当前有 Key 的 provider。目录 preset 在代码中，用户新增端点存数据库，运行密钥存部署的 settings 文件。迁移目录元信息不等于迁移 Key。

`settings/repository.py` 用进程内锁和缓存降低重复读文件，写入通过原子替换减少半文件问题。它不是跨进程事务存储；两个进程同时读改写仍可能丢失更新，独立 worker 的缓存也不自动收到管理员更新。V2 的单次 Embedding snapshot 解决本次任务中途切换问题，不能代替跨进程刷新机制。

### Compose、Caddy 与交付

Compose 编排 PostgreSQL 15/pgvector、Python 后端和 Caddy 静态前端。前端先在 Node 构建阶段 `npm ci && npm run build`，产物进入 Caddy 镜像；Caddy 将 `/api/*`、OpenAPI 和文档页面代理到 backend:8000，其余请求使用 SPA fallback。外部默认暴露 80，后端与数据库在 Compose 网络内互访，数据库卷和 backend/data 持久化。

健康检查及 depends_on 的 healthy 条件保证启动顺序，但不代表业务模型调用必定可用。当前 Caddyfile 使用 `:80`，不能说代码中已配置生产 HTTPS 证书。用户简历提及 Azure 云服务器；仓库能证明 Compose 交付方案，未看到云资源 IaC 或 Azure 托管检索服务的使用证据，不能扩展成 AKS／Azure AI Search 架构。

`/health` 当前返回的是进程持有的 database.status，不会每次执行 SELECT 检查数据库。因此部署探针主要验证 HTTP 活性，不能描述为持续验证数据库与外部模型的深度健康检查。原课程最后的 `408dd2b` 曾通过后移邀请表修复 fresh init 的外键顺序；V2 的 `7aaf075` 则把 app_users.id 改为内联主键并取消后置主键，以另一种方式解决同一初始化依赖问题，不能因未合并课程修复 SHA 就声称 V2 仍有该缺陷。

CI 工作流 `.github/workflows/lint.yml` 在 push/PR 时安装 Ruff、运行 lint 和 format check。**它目前没有自动跑 pytest、构建镜像或部署服务器。** 本地 README 的质量检查命令与 CI 实际自动运行范围要分开。

<a id="kb-11"></a>

## 11. 独立实验线：执行画像、RunEvents、评测适配与MCP

### 独立实验分支：canonical profile、capability 与 RunEvents

适用版本：VX／0b22809，未合并V1/V2。

本节全部基于 `0b22809` 的 Git blob，**不属于 HEAD/main 已合并功能**。

#### canonical profile 解耦什么

`0b22809:backend/app/modules/chat/domain/modes.py:14` 定义：

- workflow：quick_answer / research / deep_research；
- source policy：selected_only / library_allowed / web_with_approval；
- output format：adaptive / policy_brief。

旧三字段把“写给谁、知识边界、执行流程”混在一起，canonical 思路把呈现样式与权限隔离。legacy mapping 是 pure function：policymaker → research + selected_only + policy_brief；其他 direct → quick_answer，react → research；chat → web_with_approval，analysis → selected_only；student 保留兼容输入，归 adaptive。

模块自己说明“compatibility description, not a new router”。API 和持久化仍用旧字段；deep_research 只是可取类型，不代表实现深度研究执行器。`tools_for` 增加 source_policy 参数并支持 library_allowed，但 agent_node 实际还用 answer_mode 调工具，不能宣称全链路完成 canonical 权限迁移。

#### PolicySearchCapability 为什么值得抽

`0b22809:.../capabilities/contracts.py:14` 定义不可变请求：query、selected/library scope、identifiers、top_k、include_restricted、metadata_filters；把 library 映射成底层 full_corpus。`policy_search.py:18` 通过 RetrievalPort 协议依赖检索服务，`search()` 只委托。

好处是 Agent、MCP、脚本/测评可共享检索语义，各入口只处理传输/权限/上下文。它是薄适配层，不是另造了一个检索算法。测试可注入 StubCapability 检查 adapter 是否保留 citations、充分性和 filter notices。

#### run context 与版本标识

`0b22809:.../runtime/context.py:14` 的 AgentRunContext 为冻结 dataclass，包含 run_id/session_id/assistant_message_id/user_id/is_admin/profile/model/prompt_version/configuration_version。SSE run_id 取 assistant_message_id；resume 从 checkpoint 恢复同一 context，所以它是“一个逻辑请求”而非“每个 HTTP 连接”身份。

`runtime/versioning.py:12` 手工维护 PROMPT_VERSION；configuration 按稳定 JSON 排序再 SHA-256 前 16 位，不保存凭据 key。作用是粗粒度比较运行配置，不等于把所有影响行为的参数冻结成可重放快照。router 实际传入的配置范围有限，active tool limits/embedding/reranker/model版本仍可能变化；secret key 名启发式过滤也不是通用数据泄漏证明。

#### 事件契约与持久化

事件类型为 run_started/model_call_started/model_call_finished/tool_call_started/tool_call_finished/first_token/run_finished/run_failed；字段有 sequence、UTC occurred_at、node/tool、duration_ms、token_usage、status、error_type、白名单 public_metadata。原 prompt、工具参数、文档正文、私有思维不进这个事件 schema。见 `0b22809:.../runtime/events.py:9–73`。

允许 metadata 只有 modes、model、scope、citation_count、result_count、evidence_sufficient 等标量；token 只保留允许字段中的非负 int。Null、InMemory、Composite、Postgres sink 通过协议替换，emit_safely 捕获 sink 失败，观测失败不改变面向用户的执行结果。见 `runtime/sink.py:14–49`、`postgres_sink.py:19`。

DB 每次 append 根据 run_id 获取 `pg_advisory_xact_lock(hashtext(run_id))`，在事务内 `MAX(sequence)+1`，并有 `(run_id,sequence)` 唯一约束。这样跨 resume 的新 observer 即使内存序列重置，也由 DB 分配连续持久序号。见 `runtime/repository.py:39–75`。锁在这里是**事件追加序列化**，不是 Agent 同 session 执行互斥，不能拿来证明 resume 没并发竞态。

管理员接口 `GET /admin/agent-runs` 和 `/{run_id}` 受 require_admin 保护；普通 chat history 与此 sanitized telemetry 的数据职责不同。见 `runtime/router.py:13–30`。

#### 分支埋点的实际边界

该分支在 Direct / ReAct 应用驱动插入模型/工具起止和 first token。静态核实需指出：

1. ReAct 各决策 finished 事件没有各自 token_usage；最终 generation 事件放的是整轮 aggregate，不是最终一次模型的独立 token。Direct 仍没有传出生成 usage。
2. `tool_result_event` 返回 `tool` 与 `result_count`，观测代码却在 `0b22809:application/streaming.py:219,228` 读 `name` 与 `results`；`len(result_event.get("results") or [])` 会给 0，不能把该结果计数当真实召回数。
3. Resume 创建新的 RunObserver，start(resumed=True) 避免重复 run_started，但 perf_counter 从恢复请求重新计时。因此 duration/TTFT 没有覆盖暂停前计算和用户等待；应定义它测的是当前连接阶段还是逻辑 run。
4. prepare 工具后仍可能发 node_name=agent 的 model_call_started，最终 finished 记在 final_generation；模板拒答也可能出现这种模型阶段含义不对齐。它不是底层每次 HTTP 模型请求的精确 tracing。
5. 状态事件只含 started/succeeded/failed，没有专用 paused/resumed 契约；模型协议重试、gate veto、suggestions 不自动全部入账。
6. telemetry 失败隔离保证答案可继续，却也意味着事件可能丢失；每事件同步等待 sink 不是零开销异步批量日志系统。

#### 测试证明边界

foundation tests 覆盖 output format 不扩 selected 权限、source_policy 工具集合和 legacy adapter；runtime tests 覆盖 token/metadata 清洗、sink 失败隔离、事件顺序；streaming tests 用 mock graph/model验证 Direct trace 与 resume 不重复 run_started。这些验证很有价值，但不是实际生产流量下延迟统计完整性证明。

### 独立实验分支：FastMCP stdio 的真实能力和边界

适用版本：VX／0b22809，未合并V1/V2。

#### 服务形态与调用链

`0b22809:backend/app/mcp_server/server.py:7` 以 stdio 启动 FastMCP。客户端启动本地服务进程，通过 MCP initialize、tools/list、tools/call 使用能力。当前只暴露：

1. `get_policy_search_status`：查看来源政策、remaining calls、max_top_k、restricted=false；
2. `search_policy_documents`：返回 grounded citation excerpts、充分性、filter 状态。

调用链是 MCP tool → MCPPolicySearchRuntime → PolicySearchCapability → RetrievalService。没有把完整 LangGraph 对话/所有六种工具原样转成 MCP，也没有让项目内 ReAct 通过 MCP 网络再调用自己。MCP 是外部检索适配入口，项目内工具仍走 Python 直接调用。

Function calling 是模型输出函数名/参数的能力；MCP 是客户端与工具服务之间的标准发现/调用协议；两者可结合，不能混为同一个层次。stdio 是进程本地传输，当前不是暴露在 Azure 公网的 Streamable HTTP MCP endpoint，没有对应 OAuth/远程多租户鉴权实现。

#### 访问策略和预算

`0b22809:.../mcp_server/policy.py:29–51`：默认 selected_only、max_calls=10、max_top_k=12；环境变量可调整，calls 必须 1–1000、max_top_k 1–50。search 默认 top_k=6。selected 需要至少一个 identifier；library 仅 source_policy=library_allowed 允许；query trim 后不能为空；restricted 固定 false，客户端不能覆盖。

每个 runtime 使用 asyncio.Lock 在调用前扣预算，避免并发超支；失败也已经扣除，不退还。预算是服务进程生命周期总调用次数，不是每用户/每会话配额，也不是每分钟限流；status 不消耗搜索次数。见 `policy.py:82–98`。

selected_only 指客户端必须显式给文档标识，不表示这些 IDs 自动来自已认证网页用户的选中集。MCP context 的 user_id 固定为 `mcp:stdio-client`、session_id 为 `mcp:policy-search`；它不复用 FastAPI 用户登录，不应夸称细粒度企业租户 ACL。见 `policy.py:274–294`。

返回 citations 只允许 document_id/chunk_id/title/page/quote/source_url，剔除私有调试字段，并返回 remaining_calls 和 filter notice。见 `policy.py:224–255`。检索 gate 可能触发命名政策的 LLM veto，故“这个入口不生成最终答案”准确，“MCP 调用绝不产生任何模型成本”不准确。

#### MCP 测试做到哪一层

`0b22809:backend/tests/test_policy_mcp_server.py` 注入 RecordingCapability / InMemory sink，验证工具列表、请求映射、restricted=false、私有字段剔除、来源边界和预算。

`test_policy_mcp_protocol.py:12–44` 真正启动 Python stdio 子进程，执行 initialize/list_tools/status，并检查 structuredContent。它确实验证真实 MCP 协议链路，不是只调普通函数；但 status 不访问数据库，也没有端到端调用实际向量检索或最终答案模型。不能说这个测试证明线上检索质量与完整 Agent 集成都通过。

### 独立分支未来合并需处理的具体冲突

当前 HEAD 有 `backend/database/migrations/028_durable_document_tasks.sql`；实验 observability 分支有 `028_add_agent_run_events.sql`。同编号来自独立历史，集成时需要按项目迁移机制重编号/核对 init.sql 与 Compose 挂载，不能直接因两个 filename 不同就认为迁移顺序无风险。

此外实验分支基于旧的 DB/文档任务实现，当前 async to_thread、连接池和入库执行路径已演进；不能简单复制整个旧 streaming/router 覆盖当前文件。合并后还需回归旧 SSE schema、resume 身份/预算、完整 source_policy 传播、事件计数与 Token 口径。上述是集成建议，本知识库未执行合并或修复。

<a id="kb-12"></a>

## 12. 评测、测试、历史验证与效果结论边界

### 评测：当前脚本、未合并分支与历史live报告

适用版本：按小节区分V2脚本、VX评测与历史报告。

#### 当前HEAD的12条合成语义数据

`backend/scripts/evaluate_embeddings.py:27` 定义12条**全英文合成**query/relevant/lexical_distractor，主题包括电动车补贴、燃油车限制、能源账单、碳排放、数据保护等。它不是从真实客户查询独立采样的全库评测集。每条有一个相关passage与一个词面干扰passage。

embedding脚本测试每对relevant与distractor相似度margin、top1、向量finite/deterministic、固定384维contract，并用中文句子检查非零向量等。见 `evaluate_embeddings.py:154`。写死EXPECTED_DIMENSIONS=384意味着换成2048维模型时该contract不能直接视为模型错误；--enforce主要看semantic_pass，也不能把其退出码当所有contract都已通过。

`evaluate_retrieval_recall.py:9` 复用同12条，把12相关+12干扰组成**24 passages**，直接embedding并Python穷举cosine排序，不经过数据库、HNSW、BM25、RRF、reranker或证据gate。相关性靠case_name相同且kind=relevant判定，见 `:24/:42/:52/:63`。

\[
Recall@K(q)=\frac{|Rel(q)\cap TopK(q)|}{|Rel(q)|},\qquad
MRR=\frac{1}{Q}\sum_q\frac{1}{rank_q^{first\ relevant}}.
\]

本集每query只有1个正例，所以代码的Recall@K等于“正例是否进topK”的平均hit rate；不是多正例完整证据召回。脚本算@1/@3/@5与全排名MRR，见 `:70/:91`；没有chunk/page级真实政策qrels，也没处理多跳所需证据集合。

#### 当前reranker与threshold脚本的代表性限制

`evaluate_reranker.py:13` 默认模型 **Xenova/ms-marco-MiniLM-L-6-v2**，可用环境变量覆盖；在线默认却为 **BAAI/bge-reranker-base**。它对同24条合成passage的dense top3再cross-encode，统计candidate recall与reranker top1，见 `:17/:90/:107/:168`。这不是当前local/API RerankingService的完整端到端实验。

`evaluate_evidence_threshold.py:25/:30` 直接调用旧compat embedding和local documents.reranker，并固定vector/reranker阈值（reranker -7.0），而当前主路径provider-aware local默认-2/API0.99。它适合历史toy阈值分析，不能不加解释就代表当前provider动态门控。

`docs/BM25_HYBRID_RETRIEVAL.md:181` 提到借recall脚本manual A/B，但脚本现状没有BM25/RRF开关或对比路径。因此**当前没有由该脚本证明的hybrid提升百分比**；代码单测通过只能说明排序/融合/回退逻辑符合断言。

#### 未合并的15条真实政策smoke分支

分支 `feature/eval-smoke-runner@2a2bcb4` 的 `backend/evals/smoke_policy_search.jsonl` 有15条：11英文+4中文；12 selected retrieval、2library retrieval、1不足证据；依赖Australia、China、Singapore、SouthAfrica四个指定文件名。它通过该分支的PolicySearchCapability调用共享检索，不跑HTTP或完整LangGraph Agent。

该分支 `backend/app/modules/evaluation/runner.py:97` 比较：evidence.sufficient是否符合expected、引用数是否达到minimum、expected_source_contains是否在所有citation来源字段拼接字符串中出现。passed是三者AND；额外报告mean latency、pass_rate。citation_quality在`:135`只检查quote和至少一种来源字段存在，不校验引用原文正确、页码正确或claim蕴含。

这15条不计算Recall/MRR，未标注所有相关chunk，也不评answer generation、web search、interrupt/resume和多步Agent strategy；该分支README明确声明边界。可复用的基础是同一检索接口，不等于full-agent评测已经做完。

对应Git：`dcfc783`定义数据集、`0dee968`新增并发Runner/报告、`2a2bcb4`文档，作者Alem42，原始作者日期均2026-08-15。它们不属于当前HEAD祖先，不应与2026-10-15当前分支的migration028文档任务混称已经一起合并。

#### 2026-10-13历史live结果：可讲排障，不能讲本次验证

本地ignored报告 `backend/eval-results/policy-search-108269d3-60ba-4591-8f28-48cc7bf049ed.json` 记录开始时间 **2026-10-13 01:21:46+08:00**，15条 **0/15**、平均 **3107.39ms**。历史探测环境为7文档/186chunks，API embedding-3 2048维、API rerank。所需Australia与SouthAfrica原文件名缺失，7条FileNotFoundError；其余8条进入检索但证据gate拒绝。不能将0/15全归因“算法无法召回”，数据先决条件和provider契约有不同问题。

同期历史单例Singapore检索8个raw候选distance约0.308–0.371，均过0.5门槛，词法覆盖约0.857–1.0；reranker_score却全0。历史小型provider探测看到原请求HTTP200但results=[]；仅加`top_n=len(documents)`后有2条结果，见 `backend/eval-results/interview-rerank-shape-probe.json`。当前源码仍不传top_n，也仍会把空results补零，这是静态可见风险；**本次没有重新调用API，不能保证今天服务端行为仍完全相同**。隔离探测不是已合入的修复。

同批历史 `synthetic-recall-6c90d1c0-555b-477c-80f8-87102ae7cf52.txt` 保存：24 passages、Recall@1 **7/12=58.3%**、Recall@3/5 **12/12=100%**、MRR **0.7917**。该txt自身没有完整实验配置快照或独立时间字段；它是10/13会话保存的历史小样本输出，不是本次10/17运行，也不能归因BM25/RRF/reranker。

这组经历最有价值的表述是：“我区分了依赖数据缺失、HTTP成功但schema/语义结果异常、候选召回与证据门控失败，避免只调阈值掩盖provider契约问题。”不能说已经修复并回归通过。

#### 10月15日提交的工程验证报告

当前跟踪的 `backend/docs/verification/durable-tasks-2026-10-15.json` 记录真实解析/本地embedding、worker强杀恢复、重试和多用户文档读。报告明示未调用远程chat模型，读并发不是LLM吞吐，小规模不代表生产容量。

`backend/docs/verification/database-repair-2026-10-15.json` 另记录真实上传1页/1chunk、embedding-3 2048维1向量、27.75秒、optional_metadata_fell_back=true、临时用户/文档清理。它可以佐证当日上传持久化闭环，但没有证明15条政策问答质量、hybrid收益或完整Agent联网恢复。这些均为**已存历史报告**，本次未重跑其中359/352等历史测试数量。

### 现有测试覆盖、真正该怎么做质量实验

适用版本：按小节区分V2脚本、VX评测与历史报告。

#### 当前代码中的相关测试，不冒充本次运行

| 文件 | 断言重点 | 能证明/不能证明 |
| --- | --- | --- |
| `tests/test_pdf_extractor.py:42` | 原生页不OCR、低文本页恢复、混合页、引擎缺失退化 | 处理分支契约；不证明真实扫描集OCR准确率 |
| `tests/test_docx_extractor.py:43` | 段落、空段、表格、single page | 内容抽取形状；不证明Word真页码 |
| `tests/test_chunker.py:16` | tokenizer依赖注入、模型计数、默认实例 | 计数路径正确；不证明480/120最优 |
| `tests/test_keyword_search.py:24` | 中英token、BM25、RRF、LRU、异常回退、distance补算 | 算法契约；不证明hybrid相对dense在真实语料提升 |
| `tests/test_reranker.py:24` | 顺序、空输入、非法text、score数量不符 | 本地接口行为；不覆盖所有真实厂商兼容性 |
| `tests/test_document_service_reranking.py:57` | 检索调用rerank/异常fallback | glue逻辑；不证明API200空results安全 |
| `tests/test_retrieval_service.py:11` | context/citations/evidence一致、弱子集回退、地区覆盖、拒无关页面引用 | 核心业务规则；不证明答案语义准确 |
| `tests/test_metadata_filters.py:40` | 显式标签/年份/别名、来源语言、zero-match通知 | 规则case；不覆盖任意中文时间表达 |
| `tests/test_web_import_service.py:44` | URL规整、原/最终URL校验、空/超限内容 | 应用入口边界；不等于完整SSRF实网验证 |
| `tests/test_web_import_ingestion.py:10` | byte重复复用、title持久化、失败清理 | 补偿逻辑；不证明所有崩溃窗口无残留 |
| `tests/test_web_governance.py:50` | lifecycle/interval校验、admin路由 | 治理接口；不证明有自动刷新调度器 |
| `tests/test_contextual_header_budget.py:14` | 慢header不拖住主流程、metadata deadline、SDK不重试超时 | 阶段预算契约；不证明所有外部调用总耗时上界 |

本次只读测试源码和历史报告，未声称这些测试在本次10/17已执行。实际执行应由主审记录当次命令与输出。

#### 面试中可以提出的下一步实验，明确未做

首先建立客户真实query与独立标注qrels：按document/page/chunk标注相关性，区分单证据、多证据、跨地区、中文/英文、词项/语义改写、时效约束、无答案、OCR错误。训练/开发/测试分离，固定文档快照和评测版本，避免靠同一15题反复手调过拟合。

再做消融：dense、BM25、RRF、dense+rerank、RRF+rerank；固定embedding、chunk、C与最终K，并记录版本。报告Recall@K、MRR/nDCG、跨地区证据覆盖、answerability precision/recall、拒答误拒/误答，而不是只报一个通过率。

端到端另评：引用正确/完整、claim被支持比例、答案正确性、工具选路与预算、中断恢复成功率、P50/P95延迟、外部调用/Token与费用。模型judge可辅助，但需人工抽检和错误类别分析，不能把judge结论当真值。

性能实验先分段计时：PDF/OCR/metadata/header/embedding、DB dense、BM25冷/热缓存、reranker、evidence veto、generation。单独看ANN recall相对exact search，再调ef_search等，避免把OCR或provider网络慢错归DB。当前没有这套完整结果；这是建议，不是项目既有业绩。

### 验证分类

逻辑测试使用受控 provider 或 mock，验证路由、状态、排序、协议与故障分支。PostgreSQL 集成测试通过显式 `TEST_DATABASE_URL` opt-in，fixture 不回退到项目 `.env` 的业务库。独立进程验证脚本使用隔离测试数据库、真实 PDF 和本地向量模型，故意杀掉自己的 worker 进程来观察恢复。真实外部 API 验证单独记录。

本次知识库整理没有重新运行收费模型、迁移、业务数据写入或大规模压力测试。下列数字来自已提交的 2026-10-15 脱敏报告，应以日期和范围引用，不能说成 2026-10-17 又测得相同结果。

### 持久任务报告的具体证据

`backend/docs/verification/durable-tasks-2026-10-15.json` 记录：当时后端 352 项、前端 4 项通过，Ruff、前端 build 和 Compose 配置检查通过；真实提取与本地 Embedding 场景下，API 重启后请求映射仍在、心跳阻止正常任务被接管、强杀 worker 后第二次尝试成功恢复。多账号场景包含四个读取账号、两个上传账号、八份 PDF 与 120 次目录／聊天历史读取，读取全为 200，P50 15 ms、P95 32 ms。缺失文件耗尽三次后恢复文件、手动重试，第四次成功。

这些指标只代表小规模本地读取和后台处理并行，**不包含收费 LLM 多用户 Token 吞吐，不是生产 QPS／P95。** 报告明确浏览器 UI 验证未完成。脚本 `backend/scripts/verify_durable_tasks.py` 只管理自己创建的 API/worker 子进程，并要求一次性测试库。

### 迁移修复与实际库上传报告

`backend/docs/verification/database-repair-2026-10-15.json` 记录：后端测试 359 项通过；通过前端开发代理的实际 HTTP 登录为 200、上传为 202、相同幂等键重放得到相同文档与任务 ID。上传期间 8 并发共 24 次文档库读取全为 200；一个小型实际 PDF 首次尝试成功，约 27.75 秒，提取原文标识和预算数字保留，产生一 chunk 与一条 2048 维 `embedding-3` 向量，下载摘要匹配。元数据模型超时后使用默认值，仍完成索引。

报告还核对迁移及清理后原有六用户、七文档内容不变，临时账号和文档已清理。该验证没有操作浏览器页面，只经过 Vite 代理做 HTTP 请求。27.75 秒是单个小文件的功能验证，不是一般入库延迟承诺。

### 面试如何表达验证

可以说“为上传幂等、租约接管、旧 worker 提交资格、迁移回滚以及可选模型超时写了回归，并用真实解析、向量和进程故障脚本验证”。如果被问指标，要同时给出测试对象、数量、环境和日期。不能只说“359 个测试全部通过，所以生产不会丢任务”，也不能把 mock 的模型结果称为真实 LLM 的答案质量评测。

### 测试资产如何解释，避免把 mock 说成真实上线验证

适用版本：V2与VX测试范围分开。

当前 HEAD 的相关测试可检索入口：

- `backend/tests/test_agent_tools.py:133`：跨 checkpoint 的每轮引用重置；`518–656`：权限/模式/预算/token；`673`：隐藏旧轮工具轨迹；`731–923`：不可用工具、漏工具调用、多工具裁剪和 fallback；`925–1016`：显式 prepare、analysis 拒答；`1078`：tier 首轮门控；`1116`、`1173`：编号规则。多数模型/网络通过 mock，引用重置可用内存 saver，不代表真实 PG 恢复全链路。
- `test_chat_turn_service.py:55–95`：先读历史再写当前问题、归属失败不写入、同步文档范围。
- `test_chat_resume_router.py:17,31,52`：越权、无暂停 409、发出 interrupt 后关流不误标失败。
- `test_chat_router.py:15–154`：紧凑结果映射、实际引用来源 badge、当轮 token 汇总。
- `test_chat_rag_modes.py`：不同风格/边界、弱证据分流、英文词覆盖和命名政策 veto/fail-open。
- `test_chat_policymaker_mode.py`：后端兼容与强制文档边界，说明 UI 移除不等于协议删值。
- `frontend/tests/upload.test.js`：当前看到的前端自动测试重点在上传，不能拿它当 Chat 浏览器中断恢复的证据。

本轮没有重新运行测试；不能给出本轮“全部通过”数字。Git 某个提交消息记录的 350 backend tests 等，是该提交作者记录的当时验证，不等于今天由本次审计重现。

<a id="kb-13"></a>

## 13. Git发展史：从原型、课程交付到两条后续支线

### 先确定究竟在讲哪个版本

#### 当前各分支的事实

下面日期按提交 AuthorDate 转为北京时间（UTC+08）。六至八月历史提交多数原为 UTC+10。提交时间是 Git 元数据，不是实际开发耗时或云端部署时间。

| 版本/引用 | 当前 SHA | 北京时间 | 可达提交数 | 应如何描述 |
|---|---|---|---:|---|
| 原课程仓库 `course-audit/main` | `117f6c9` | 2026-08-11 16:25 | 359 | 原课程仓库最终 main，PR #63 合并 develop 的版本。它才是本次抓取到的课程最终主分支。 |
| 原课程仓库 `course-audit/develop` | `b56be8d` | 2026-08-11 16:20 | 355 | 原课程最终 develop；与课程 main 的 tree 完全相同，但 commit 图不同。 |
| 个人仓库 `origin/main`、`origin/develop`，以及本地 `main`、`develop` | `65e58ad` | 2026-08-10 02:37 | 349 | 本人 finalhandover 分支的 source head，后来经原课程 PR #62 合并。个人仓库保留于此，没有课程最后的十个提交对象。 |
| `legacy/course-main` | `35de168` | 2026-06-26 15:55 | 6 | 原课程 main 的保存引用，停在第二个 PR 合并处。不能因为名字叫 course-main 就把它当完整课程交付版本。 |
| `legacy/course-develop` | `9c78815` | 2026-08-10 00:47 | 342 | 旧保存点，不是原课程最终 develop；个人 origin/main 比它多七项 finalhandover 功能提交，原课程最终 develop 比它多十三个提交对象。 |
| 当前 `HEAD` / `feature/durable-document-tasks` | `2a45d2a` | 2026-10-15 12:44 | 358 | 从 `65e58ad` 分出的连接池、上传和持久任务支线；领先远端 main 九项提交。 |
| `feature/backend-pool-upload` | `7f6a519` | 2026-10-15 11:13 | 351 | 当前持久任务分支的前两项提交，连接池及有界上传基础。 |
| `feature/agent-foundation` | `65e58ad` | 2026-08-10 02:37 | 349 | 只是指向 main 的起点，不能据分支名认为已包含 foundation 改造。 |
| `feature/agent-foundation-contracts` | `bef38b9` | 2026-08-15 10:55 | 355 | 从 main 分出的另一个方向，领先 main 六项提交，包含执行画像、能力抽取、上下文与事件契约。 |
| `feature/run-observability` | `136cf86` | 2026-08-15 11:15 | 359 | 接续 foundation，领先 main 十项提交，增加持久运行事件和管理查询。 |
| `feature/eval-smoke-runner` | `2a2bcb4` | 2026-08-15 12:02 | 362 | 接续 observability，领先 main 十三项提交，增加能力级 smoke runner 和报告。 |
| `feature/mcp-and-mode-simplification` | `0b22809` | 2026-08-15 12:23 | 366 | 接续上述支线，领先 main 十七项提交，包含 FastMCP、MCP 运行事件及学生模式移除。 |
| `Demo1.2_ZZP` / `codex/rebuild-Demo1.2_ZZP` | `30cc929` | 2026-07-29 18:01 | 215 | 历史演示/整合分支，已在 main 祖先中；不能当另一个新增功能集合重复计算。 |
| `backup/Demo1.2_ZZP-rewritten-history` | `1310829` | 2026-07-29 18:01 | 210 | 保存的另一套重写历史；其树与 `30cc929` 完全相同，但 commit 图不同。 |

最容易说错的一点：**8 月 15 日的 MCP、统一 Agent Run 事件和能力评测支线，没有合并进当前 10 月 15 日的持久任务分支，也没有合并进 `origin/main`。** 当前工作区文件出现与否，必须按具体 ref 检查。不能在介绍当前 HEAD 时把所有 feature 分支能力加在一起。

可以把两个后续方向画成：

```text
课程 develop 的旧保存点 9c78815
  └─ 8/10 七项 finalhandover 功能 → 65e58ad（个人 origin/main/develop）
       ├─ 原课程 PR #62 合并 → 末期修复/回退/lint → PR #63 → 课程 main 117f6c9
       ├─ 8/15 foundation → observability → smoke eval → MCP 0b22809
       └─ 10/15 连接池/上传 → durable tasks 2a45d2a（当前 HEAD）
```

图为简化后的功能分叉关系：课程 main 还包含更早的三次 develop→main 发布合并对象。`origin/main...course-audit/main` 为 `0 / 10`；`HEAD...course-audit/main` 为 `9 / 10`。当前持久任务分支和课程最终 main 从 `65e58ad` 分叉，双方都有对方未包含的提交。两者不能只按日期新旧判断谁完整包含谁。

个人 origin/main 与课程最终 main 相比，课程末尾净变化涉及 39 个文件，课程→个人方向为增加 226 行/删除 151 行，反过来个人→课程方向为增加 151 行/删除 226 行。主要包括 fresh-init 外键顺序、页面标题和 lint 修整，没有新增 MCP。

“main 已合并”只是一项源码状态。必须区分个人 main 与课程 main。是否为答辩时/客户访问时的云端部署版本，仍需实际部署记录、镜像 tag、运行服务器版本证明。

#### 为什么不能说“我们一共做了 594 项提交”

在本次获取原课程 refs 之前，`git rev-list --all --count` 为 594；补齐课程最后十个提交对象后为 **604**。它包含两套镜像初始历史、重写备份、各条 feature 分支，以及 `refs/stash` 的对象，不是某个交付分支独立完成的工作量。

在补齐课程 refs 后的 **604 对象快照**中重新计算，按“完全相同的 tree + AuthorDate + subject”分组，共找到 210 个重复组、215 个冗余 commit 对象。这只能证明对应快照、日期和说明一致，并非通用的语义等价判定。进一步对非 merge 提交计算 `git patch-id --stable`，得到 318 种稳定 patch，存在 166 个重复组、173 个重复 patch 对象。不同口径不同结果，原因包括空改动、合并对象和相同补丁落到不同父提交之上。

`origin/main` 自身有 349 个可达提交，其中 286 个非 merge、63 个 merge。非 merge 补丁有 285 种稳定 patch：`3508888` 与 `7a13223` 两个部署修复的 patch 相同。它们不是“部署性能提高了两次”的证据。新增/删除行数会受搬文件、格式化、锁文件变化影响，也不能作为个人绩效排名。

原课程最终 main 则为 359 个可达提交，291 个非 merge、68 个 merge。GitHub 一共 63 个 PR 编号，但只有 **52 个 merged、11 个 closed without merge**。不能把 63 直接当成功合并次数，更不能用“非 merge commit 数、merge commit 数、PR 个数”三者相加计算功能量。

#### 历史改写中的作者对应

主干保留的 `ZZP` 50 个提交、`Demo_ZZP` 32 个提交（其中 23 个非 merge、9 个 merge），**每个都能在其他历史引用中找到作者为 Alem42，且 tree、AuthorDate、subject 完全一致的对应快照**。这为旧版本定位提供了明确证据；不是应该再算一次的新增开发。

| main 历史 SHA / 作者标签 | 镜像 SHA / 作者标签 | 实际代码事项 |
|---|---|---|
| `c470517` / ZZP | `ed2a153` / Alem42 | 初始文档服务 |
| `0faae82` / ZZP | `df4a6f0` / Alem42 | 初始线性 LangGraph RAG 图 |
| `2bf9088` / Demo_ZZP | `62e60a3` / Alem42 | 避免阻塞事件循环、后台处理反馈 |
| `845b592` / Demo_ZZP | `c843aac` / Alem42 | PostgreSQL 聊天历史和会话管理 |
| `96d78e4` / Demo_ZZP | `f7e709f` / Alem42 | 两级分类、标签匹配和 contextual chunks |
| `c238a96` / Demo_ZZP | `7270af0` / Alem42 | 可切换 Embedding Provider、按模型向量表 |
| `39134ab` / Demo_ZZP | `2ee3eac` / Alem42 | 本地/API Reranker 抽象及统一设置 |

这个审计结论是“同一份代码快照在历史重写前后可对应”。它不自动证明线下每一行由谁编写，但原课程 GitHub 的 PR #18、#22、#35、#37、#41、#42、#44、#46 等，明确由 **Alem42** 提交 `Demo1.2_ZZP` 或相关整合分支，head SHA 对应上述旧标签代码。因此，本人的这些历史版本关联已有 Git 快照和 PR 账号两类证据，不是只凭 ZZP 三个字母猜身份。个人讲述仍应区分“本人实现的模块”“本人发起的整合交付”和“组员原始实现”。如果公布个人 commit 数，只选一条主线统计，不能叠加两个 SHA，也不能把 PR 包含的组员代码全归 PR 提交者。

### 从 proposal 到代码的真实演变

#### 方案阶段与实现阶段必须分开

已读取 `proposal.pdf`。封面日期为 2026-06-20，写明六人团队和 Scrum 角色。其技术方案曾包含 React + Next.js、模板约束的 RAG 而非不受约束的 Agent、section-aware chunking 等。当前代码最终使用 React + Vite，Direct 与 ReAct 并存，分块以段落、句子和 token 预算为主。

正确说法是：“项目最初按可控的政策检索问答设计，随后根据多轮研究、联网补证、用户澄清和交互确认需要扩展为 Agentic RAG。”

不正确的说法是：“最初方案已经实现了最终所有 Agent 能力”，或者“proposal 写了 section-aware，所以代码一定准确识别了所有政策文件的章节”。方案只证明当时的设计意图。

#### 2026-06-24：项目骨架和爬取入库基础

组员 A 的 `e6506ad` 创建后端骨架；`ec4af53` 加配置、数据库与实体基础；`374620f` 加 source/job API 和爬取入库服务，后续增加 crawler 错误报告和测试。此时更接近“政策文档采集与存储骨架”。

这里的爬取系统后来确实被移除。它是阶段性方案，不应把如今已删除的批量 crawler 模块继续当作当前交付的核心能力。

#### 2026-06-25：首个完整 RAG MVP 已经出现

旧作者标签 ZZP、镜像作者 Alem42 的一组提交，依次加入本地 PostgreSQL schema、运行设置、认证、文档服务、元数据抽取、向量工具、答案生成、LangGraph 图、API 与 React 页面。例如：

- `79dfc1c`：本地数据库 schema。
- `b32a6e5`：认证服务。
- `c470517`：初始文档服务，单文件增加 1,082 行，承担文件处理、页面抽取、清洗、chunk、存储与检索等大量责任。
- `acc72c6`：确定性的 token hash 向量工具，模型标签是 `local-hashing-v1`，这是跑通链路的占位实现。
- `8097872`、`ed082ce`、`0faae82`：生成、图节点、图编排。

`0faae82` 的真实图是：

```text
START → load_documents → retrieve_context → generate_answer → END
```

它使用 `StateGraph`，但没有工具循环，没有 checkpoint 编译参数。**用了 LangGraph 不等于已经有 ReAct Agent，更不等于已经支持 interrupt/resume。** 面试要把三件事说清：图编排框架何时引入、Agent 自主决策何时引入、持久中断恢复何时引入。

这些初始模块大量提交集中在数秒内。可以证明最终历史被拆成了模块级提交，不能推断开发者在数秒内从零编写了全部代码，也不能反推出真实工时。

#### 2026-06-26 至 06-28：第一次明显的后端架构重构

组员 A 先把 crawled 与 processed 文档的数据模型/仓库区分开，再进行两次有实际代码变化的重构。

`56771cb`，北京时间 06-27 19:13，21 个文件、增加 1,298 行/删除 1,498 行：从大文档服务中抽出文件存储、PDF 抽取、chunker；将 SQL 和持久化分别移到 document/embedding/processing-job/settings/user repositories；将鉴权依赖独立出来。它解决的是“业务流程和存储实现混在一起”。

紧随其后的 `435fca8` 按 auth、crawling、documents 拆分实体模型。

`1e1503e`，北京时间 06-28 06:02，106 个文件、增加 1,146 行/删除 897 行：从横向的 `api/routes`、`services`、`repositories`、`schemas` 改为 `modules/auth|chat|crawling|documents|settings|system`；文档仓库进一步拆为 catalogue/content/documents 等职责；补 document access/id contract 测试。

这是按业务域做模块化，不是把单体改成多个微服务。运行上仍是同一 FastAPI 应用，模块之间主要是进程内调用。

同期 `2bf9088`（旧作者标签 Demo_ZZP，镜像 Alem42）修复同步重任务堵住异步请求的问题：上传接口先保存并返回，由 `BackgroundTasks` 执行同步处理；部分操作用 `asyncio.to_thread`；前端显示异步处理进度。它将“等待整个 PDF 处理完成”改为“请求返回后继续处理”。这一版仍是进程内后台任务，**不具备进程崩溃后自动恢复任务的能力**。

#### 2026-06-28 至 06-29：前端框架与检索模型升级

组员 B 的 `b20b57c` 调整页面逻辑、AdminDashboard 和导航，`834bc2a` 使聊天只使用所选文档。组员 A 的 `a1b5db4` 引入页面路由，`cb9fc18`（北京时间 06-28 22:03）将界面迁到 MUI，新增 theme 并改造主要页面和组件。其 4,138 行增加中包含 2,345 行 package lock 变化，不能全部算新业务逻辑。

组员 C 的 `9758c3d`（北京时间 06-29 13:21）才真正把 hash embedding 替换为 FastEmbed 的 `BAAI/bge-small-en-v1.5`：新增 `passage_embed` / `query_embed` 的区分、批处理、维度/非有限值校验和模型缓存。

同一天 `d1a15fd`、`ea51059` 增加 embedding 质量与 recall 评测。`0c68c36`（北京时间 21:18）加入基于 `TextCrossEncoder`、`BAAI/bge-reranker-base` 的 cross-encoder 重排及测试。初始稠密召回与初始 reranker 的代码作者应归组员 C，不能因本人后来抽象 Provider 就声称最早的实现也是本人独自完成。

一个标题与真实 diff 不一致的例子：`ee046b1` 标题写“replace hash embeddings with semantic embeddings”，实际只新增 `backend/scripts/evaluate_reranker.py` 212 行。真正替换 embedding 的证据是 `9758c3d`。这也是本知识库不能只看标题归功的原因。

组员 D 的 `506830c` 在固定 RAG 图中加入 `check_evidence` 分支和 `insufficient_evidence` 拒答节点。它发生在 ReAct 之前，说明“证据不足不直接编答案”的控制并不是联网 Agent 才新增的。

未核实历史作者的 `7f1ed1e` 加入引用证据面板。功能作者与合并 PR 的人需要分开标注。

#### 2026-07-09 至 07-22：多轮研究工作台逐步成形

`97b8b20`（旧标签 Demo_ZZP，镜像 Alem42）初步增加多轮历史输入字段、引用呈现方法、LLM Provider 配置与 tiktoken。本人提交的 PR #18 描述明确说多轮上下文“目前还没完全实现”，不能把 7 月 9 日直接称作完整多轮闭环。该 PR 到北京时间 **07-19 06:04** 才合入 develop，作者日期和集成日期相隔约十天。这时的多轮输入与后来数据库会话不是一件事。

`845b592`，北京时间 07-19 20:29，才加入数据库聊天会话和消息历史：`history_repository.py`、`history_router.py`、SQL 表、HistoryPage 与相关测试。`72da3f0` 随后把历史交互整合进 ChatPage 侧栏。可以说“从前端多轮输入升级为后端持久化会话”，不能把浏览器保存聊天与 LangGraph Checkpointer 混为一谈。

`8001f66` 调整低证据检测，把向量距离和 reranker 阈值纳入证据决策，并展示 UI 指示。其注释记录了特定语料上的经验阈值，不能说是所有模型或所有政策库通用的校准值。

组员 A 的 `b1fb2f5`、`d631f0e`、`bca8c3e` 修复 chunk 大小与 embedding 模型 tokenizer 不一致的问题，增加超长段落拆分与相关测试。它的核心是避免“以字符粗估 token，却被 embedding 模型静默截断”导致证据丢失，不是训练了新的 tokenizer。

同一阶段组员 A 的 `189c645` 增加扫描 PDF 页 OCR：先用 pypdf 抽文本，低文本页才渲染成图，用 Tesseract；`d4e66e6` 补镜像依赖；`0106ccb` 引入 DOCX/TXT/Markdown 抽取分发。DOCX 没有稳定的 PDF 物理页码：此时抽取器将内容作为逻辑页/文本单元处理，不应承诺和 Word 打印预览页码完全一致。

组员 B 的 `8c76849` 修改学生分析提示词、扩大上下文字符预算；`60a2d4a` 等加入 lint CI。组员 C 的 `d079901` 实现文档约束的 policymaker 模式。组员 D 的两个提交区分写作风格和回答目的。历史上曾有 student/policymaker 等模式，但并非所有模式都保留到后续版本。

`d15c6ed`，北京时间 07-22 00:24，实际 diff 除整合 OCR/多格式支持之外，还加入 `/chat/stream`、`StreamingResponse`、SSE token/citations/done/error 事件和流式生成。标题主要写 merge，并不能因此忽略这次提交新增的 SSE 实现。这个阶段已经流式回答，但还不是后来的 ReAct 流式工具执行与 resume 流程。

#### 2026-07-27 至 07-29：第二次核心重构——把模型能力从文档服务中抽成可替换模块

`96d78e4`（镜像 `f7e709f`），北京时间 07-27 20:27，22 个文件、增加 1,131 行/删除 68 行：加入两级 policy taxonomy、标签 embedding 匹配、语言检测和 contextual header。其目的在于给短 chunk 补文档上下文、使分类规范化；标签相似度匹配不是人工精确标注，contextual header 的存在也不代表其内容可无条件当作原文证据。

本人 [PR #41](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/41) 还明确把 structure-aware chunking 列为 TODO。这一点直接支持“proposal 提出的结构感知切分没有在此阶段完整落地”。同一 PR 说明 contextual sentence 仅加在 embedding 输入前，存储/展示的 chunk 原文不被替换，生成头保存在 metadata；这是为了检索补上下文，同时保留引用原文。

`5de9b2d` 增加基于 SHA-256 的精确重复上传拒绝。后来网页入库再加入规范文本/语义等去重路径，二者的对象和返回行为有演变，不能说一开始就有全部去重层。

`c238a96`（镜像 `7270af0`），北京时间 07-29 03:35，28 个文件、增加 2,537 行/删除 937 行：

1. 将 embedding 从 documents 内部固定实现抽为独立 `modules/embedding`，区分 Provider、设置、服务与 API。
2. 提供本地 FastEmbed 和 OpenAI-compatible 接口实现。
3. 根据 active model 和 dimension 选独立向量表，避免同一表里混入不同维度的向量；增加建表和 HNSW 索引路径。
4. 支持重新 embedding，保留原始 chunk。
5. 将前端设置集中到 Manage hub 的分区界面。

收益是更换模型和接入不同接口不再要求到处改文档处理代码；但不能从“按模型向量表”直接推导“已经做了无停机版本切换、完整双写和原子迁移”。切模型后的已有文档是否在 active table 可检索，仍依赖重建向量等实际流程。

`39134ab`（镜像 `2ee3eac`），北京时间 07-29 14:40，19 个文件、增加 764 行/删除 68 行：把 reranker 抽为独立 `modules/reranking`，本地/API 两条实现、可开关和阈值设置，提取共享 `settings_store`。这项工作是本人对应历史对模型基础设施的统一，初始 cross-encoder 接入依然是组员 C 的贡献。

`d525869` 至 `450e1ce` 的模型目录/Provider registry 系列，把供应商、endpoint、模型目录与共享密钥设置统一，移除旧模型 override API，后续生成和元数据抽取按 catalog 解析目标。**收益是配置来源收敛和各模块模型解析一致，不是模型本身变聪明。** `cc5f282` 的标题曾标注某供应商模型版本，但这种历史标题不能作为供应商真实当前型号的外部事实来源。

#### 2026-07-30 至 08-02：从固定 RAG 到持久化 ReAct Agent

这部分最容易错误归功。具体初始实现主要来自组员 A：

| SHA | 北京时间 | diff 证明的变化 |
|---|---|---|
| `a74aa45` | 07-30 01:31 | WebSearchProvider 与 Firecrawl 搜索实现。 |
| `e38cf22` | 07-30 01:32 | 为 Agent 增加全库向量检索。 |
| `4dd8cae` | 07-30 01:40 | 网页导入以及新增去重路径。 |
| `a6e6da5` | 07-30 01:42 | FastAPI 生命周期打开 `AsyncPostgresSaver`，调用包自己的 `.setup()`，在退出时关闭。 |
| `2c73aa7` | 07-30 01:49 | `agent → tools → agent` 工具调用循环，ToolNode、AgentState、工具及策略提示词。 |
| `b917e5d` | 07-30 02:00 | 将 Agent 接入 `/chat/stream`，新增 `/chat/resume`。 |
| `282b0a1` | 07-30 02:07 | 前端确认与 resume 交互。 |
| `662b5fd` | 07-30 04:53 | 工具门控的最终答案流式生成。 |
| `fbb2b74` | 07-31 04:41 | ReAct 与 Direct 推理模式开关。 |
| `da1f8ee` | 08-01 06:46 | 每轮/工具模型 token 用量跟踪与显示。 |

`2c73aa7` 的代码明确保留旧的线性 RAG 图，新增另一张 Agent 图，模型通过 `bind_tools` 选择工具。非管理员的模型 schema 不暴露网页导入工具，工具节点仍有服务端权限检查的必要。引用经 reducer 累积去重，messages 经 `add_messages` 合并。Agent 图延迟编译，以避免 import 阶段 checkpointer 尚未初始化。

`a6e6da5` 的 checkpointer 用已有 session id 作 thread id，是图状态持久化；`845b592` 的 chat_messages 是产品聊天历史。两种持久化目的不同，表和生命周期也不同。

在后续提交里，组员 A 继续做工具预算重置、ask_user 多种交互、停止生成、来源分层、避免重复证据记账、web chunk 后再 embedding/rerank、过度搜索控制与多主题查询。它体现了 Agent 落地后对边界条件的迭代。

**这个功能分支的主要合并点是 `ebf0062`，北京时间 08-02 17:18，PR #50。** 因此可说“7 月底实现，8 月初整合进 develop 主线”；不能把 7 月 30 日的作者时间直接当成已上线给客户的时间。

本人对应的 Alem42 在同一阶段的 `eaf716c` 与后续 suggestion 提交，主要是证据验证后的推荐追问及延迟优化。它不同于 Agent 的 ask_user：前者在答案后生成建议，后者在任务执行中向用户澄清/确认。

#### 2026-08-03：第三次核心重构——统一检索和网页入库，拆开对话生命周期与流式驱动

这一组为 Alem42 提交，有具体问题清单、相互配合的 diff，以及保留 API 的迁移策略，是本人最适合讲的架构重构案例之一。

现有 `backend/docs/CHAT_REFACTOR_STRATEGY.md` 记录的起点为 `fbc5d96`。当时的问题包括：Admin 与 Agent 的网页导入校验不同；标题只用于文件名却未可靠保存在 metadata；去重各层返回不一致；chat router 同时处理 HTTP、会话/消息、SSE、用量、引用、编排和 suggestions；ReAct 工具直接调用 Direct 图节点；搜索放在 chat.rag 之下但文档管理也需要用。

关键实现：

- `5128b35`：把 web search 提升为独立模块的规范服务。
- `544926f`：统一 WebImportService，收拢 URL 校验、内容限制、标题覆盖、去重和失败处理。
- `8abc5ef`：集中检索、证据判定与上下文构造，Direct 与 ReAct 调用共享 RetrievalService。
- `16ead37`：抽 Agent 工具策略和 web evidence 模块，减少 tools/graph 的交叉责任。
- `2b024f5`：抽 ChatTurnService、应用模型、SSE 编码、token 聚合与 Direct/React 编排入口；16 个文件、增加 491 行/删除 282 行。
- `fd738fc`：将流式执行器从 router 移至 `application/streaming.py`；router 删除 450 行、streaming 增加 362 行。这主要是职责迁移，不是性能提升数字。
- `9b13625`：推荐追问复用检索校验，避免第三套相似逻辑。
- `989ce8f`：工具协议错误恢复，7 个文件、增加 370 行/删除 15 行；真实 diff 增加对协议异常的处理、允许工具约束下的有限重试/回退，而不是让错误无限循环。

重构后的依赖方向是：

```text
HTTP routes → chat application/turn lifecycle → Direct/React orchestration
                                               ├─ retrieval service
                                               ├─ generation
                                               └─ web search

Admin import / Agent import → common web import service → ingestion
```

这和 6 月 28 日的 feature modules 重构不重复：前者把代码按业务域摆放，后者解决 Chat 域内逐步膨胀出的流程耦合、入口行为不一致和服务复用问题。

文档记录的具体缺陷与修复包括：向量尺度导致误拒答；工具拿到的片段被截到 500 字导致 chunk 后部期限丢失；索引文档不相关时不应伪装成 page fallback 引用；当前问题重复插入模型上下文。讲这些比单说“分层架构更优雅”更有说服力。

该文档历史记载“232 passed、5 skipped”及前端 initial JS 从 1,149.60 kB 到 491.91 kB；这是当时的工程记录，本次审计未重跑，不能包装成本次亲自测得或等同于线上 P95 延迟收益。

#### 2026-08-04 至 08-10：删旧路径、混合检索和交付收敛

`10ed6d9`，北京时间 08-04 13:55，由 Alem42 删除 legacy crawling 子系统，67 个文件、增加 110 行/删除 4,616 行，包括 crawler/adapters、对应接口和旧表定义；把仍需的 URL 安全能力保留到 web_search。其结果是聚焦上传政策文件与受控网页导入，不能继续同时宣称旧 OECD source crawler 已是当前在用能力。

`b8e6acd`，北京时间 08-04 21:27，增加进程内 `asyncio.Queue`，默认三个 worker，去重活动/排队文档并通过 `to_thread` 执行处理。它限制单进程并发，仍不是分布式持久队列；10 月才再次升级。

`fbfa781`，北京时间 08-06 04:00，由 Alem42 实现 BM25 + dense 的 RRF 融合：新增双语 tokenize、Okapi BM25、scope cache、chunk 文本仓库、融合函数及测试/说明。**BM25/RRF 是八月初新增的，六月的 embedding benchmark 不代表当时就有混合检索。** 相关 PR #60 的主干整合点为 `2cb57f5`，北京时间 08-06 23:51。

`889bd34`，北京时间 08-06 04:20，将 documents 大 service 再拆为 library/retrieval/pipeline 的 package。它应描述为“围绕文档服务的三个稳定职责拆分”，而非说整个平台重写了三遍。第一次解决 SQL 混杂，第二次抽 Provider，第三次把不断膨胀的入库、目录和检索流程解耦。

`46726e3` 等在 Open Discussion 对检索 tier 做固定阶梯控制；这说明“ReAct 让模型做工具决策”与“工程端存在权限/顺序/预算护栏”可以并存。不应声称所有步骤都由模型自由决定。

`9c78815`（北京时间 08-10 00:47）移除 policymaker 的界面入口，后端保留旧会话/API 兼容，是本地保存的旧 course-develop 点。其后的 `1739b83`、`4ae674b`、`d856e10`、`0535bc6`、`178df2a`、`c79f5d3`、`65e58ad` 七项，为管理员邀请、管理界面、Compose 自包含、Vite 端口、依赖刷新、全库搜索默认预算和 Docker 交接文档。

这七项属于课程 finalhandover：本人以 Alem42 账号发起 [PR #62](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/62)，head=`65e58ad`，于北京时间 **08-10 15:31:54** 合入原课程 develop，合并点 `895a380`。因此不能称它们“从未进入课程交付的个人新增”。

随后原课程还有五个非 merge：`408dd2b` 将 `admin_invites` 建表移到 `app_users` 主键建立后，解决全新初始化时内联外键无法找到唯一约束的问题；`d78bd3a` 修改网页标题；`97c2d76` 调整注释/提示词措辞，但被 `d4b8324` 整体回退；`b56be8d` 作 lint 修整。不能把已经 revert 的改动继续当最终能力。

**当前持久任务分支并非仍保留同一个 fresh-init 缺陷。** 它没有合并 `408dd2b`，但 `7aaf075` 已独立将 `app_users.id` 改为建表时的 inline `PRIMARY KEY`，同时取消后置的 ADD PRIMARY KEY，因此 `admin_invites` 的外键引用在创建时已有主键。课程分支采用“后移 admin_invites”，当前分支采用“前置 app_users 主键”，两者是针对同一依赖顺序问题的不同修复。不能据此说两分支已互相合并，也不能只因缺少原 SHA 就断言当前仍有该 bug。

本人又以 Alem42 发起 [PR #63](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/63)，将 develop 于北京时间 **08-11 16:25:47** 合入原课程 main，合并点 `117f6c9`。此时才是本次抓到的课程最终 main，tree 与 `b56be8d` 相同。个人 origin/main 停在 finalhandover source head，没有自动包含这五项末期改动和发布 merge。

#### 2026-08-15：能力复用、运行事件、MCP 的独立后续支线

这十七项提交均为 Alem42，接在 main 上，互相串联，但未合并 main/当前 durable 分支：

对这十七项逐一比对后，**AuthorDate 与 CommitDate 全部一致**，记录区间为北京时间 2026-08-15 10:46:20 至 12:23:47（原始 offset 均为 +10:00）。这能准确描述 Git 对象记录的日期，但 Git 时间字段可由环境设置，不能据此断定真实开发工时，也不能把第一项至最后一项间隔称为“整个改造仅耗时 97 分钟”。远端 feature ref 存在只能证明抓取时可访问这些提交，不提供首次 push 时间；当前祖先关系明确它们没有合入所审计的个人 main、课程 main 或 durable HEAD，所以也没有可以报告为“8 月 15 日已合入主干”的 merged_at。

1. `db8cf39`、`bf8d21c`：执行画像、抽共享 Policy Search capability。
2. `949a4d6`、`f714732`、`bef38b9`：稳定 RunContext、事件契约和行为契约测试。
3. `c4ba4fe`、`4a573c7`、`aeac2b0`、`136cf86`：经过脱敏的运行事件落库、Direct/ReAct instrument、管理端查询和 migration。
4. `dcfc783`、`0dee968`、`2a2bcb4`：能力级 smoke dataset、并发 runner、报告和文档。
5. `dd993d8`、`e6f7861`、`0316d93`、`0b22809`：退休 student 模式、FastMCP、前端 trace 可视化与 MCP 运行事件。

写简历时可以描述“后续实现了 MCP 接入与能力级观测”，但回答“当前 main 是否开箱支持 MCP”时必须交代需要相应 feature 分支。运行事件体系也不等于七月底已有的 UI 工具 trace/token 展示；不能把后者直接说成早已具备完整独立 RunEvent 数据模型。

#### 2026-10-15：当前分支的工程可靠性升级

这部分晚于简历项目周期 2026.06—2026.08，若纳入项目讲述，应明确说“课程交付后继续演进”。

- `7aaf075`：实际 Repository 从每次 `psycopg.connect()` 变为进程内 `psycopg_pool.ConnectionPool`；有限 pool size/max_waiting/timeout、池生命周期和健康检查、容量异常转换；上传改为有界读取/限制；同时将 app_users 主键移为 inline 定义，独立解决邀请表 fresh-init 的外键顺序问题。不要把此前 SQLAlchemy engine 的 pool 配置说成已经覆盖所有同步 Repository。
- `7f6a519`：主要为已有 Python 的 Ruff 格式整理，不应算独立业务能力或可靠性功能。
- `d52fdfc`：33 个文件、增加 1,819 行/删除 259 行，任务持久表、claim/lease、worker、上传注册幂等及任务查询 UI/测试，将原进程内队列升级为可恢复的数据库任务系统。
- `8fe3487`：保证 reembed 重试仍走 embedding 生命周期。
- `5749fab`：重试结束时关闭被打断的 attempt log。
- `6107d4b`：说明多用户与任务幂等边界。
- `568ff2d`：任务 schema 校验和原子 migration 命令。
- `fc53841`：给可选 metadata/contextual header 生成设置边界。
- `2a45d2a`：记录数据库修复与 live upload 验证。

可以说“当前源码已实现数据库任务租约和幂等上传机制”，不能因此声称实现了所有外部副作用的 exactly-once。能证明的范围要落到任务 claim、唯一性约束、租约校验和写入保护的具体代码；模型/HTTP 调用重试仍可能发生，任务持久化也不等于 SSE token 能按 Last-Event-ID 原样重放。

<a id="kb-14"></a>

## 14. 团队分工、个人贡献与原课程PR集成史

### proposal 所证明的是角色，不是代码归属

proposal 封面确认六人：一位 Product Owner、一位 Scrum Master、四位 Dev Team。本人 Zhanpeng Zhu 在 proposal 中的角色是 Dev Team。简历写“开发负责人/后端核心”可以描述实际技术工作和用户本人承担的管理责任，但**不能直接改口说 proposal 将本人任命为 Product Owner 或 Scrum Master**。

客户沟通、需求梳理、任务分配、进度推进和答辩表现不可能仅由 Git author 验证。可以结合本人真实经历、会议纪要、Jira/看板、客户反馈或展示材料举例，不能根据 commit 数硬推“谁是项目经理”。

proposal 中其他角色姓名不在对外稿展示。其成员与 Git 作者的映射只有部分可证：组员 B 的姓名及学术身份信息能够与 Git 中精确相同的作者身份匹配；组员 A 的作者姓名一致，且其账号别名与同一 Git 身份信息相联。Proposal 中 Product Owner 的英文称呼是否对应 Git 中拼写相近的作者，不能猜；其他人的拼音缩写、PR 分支名也不足以做实名证据。

### 建议在面试知识库采用的匿名映射

| 匿名标记 | 可核实的主要贡献 | 证据与边界 |
| --- | --- | --- |
| 本人：Zhanpeng Zhu／Alem42 | MVP工作线、后续Provider/catalog统一、Chat与检索黑盒重构、协议恢复、BM25/RRF、服务拆分、交付加固；VX和V2后续方向 | 用户确认身份，具体SHA、历史镜像及本人PR交叉佐证；不能把组员初始实现全归本人。 |
| 组员 A | 初期骨架、业务域模块化、MUI/路由、OCR/DOCX/tokenizer、初始WebSearch/ReAct/checkpointer/resume及后续交互改进 | 作者名与历史账号可通过共同Git身份信息关联；merge不等于全部功能作者。 |
| 组员 B | 前端逻辑、所选来源、无障碍/导航、部分提示词与lint工作流 | 指已核实的作者身份；课程末期另外两个相似作者标签记U1/U2，未确认与B为同一人。 |
| 组员 C | 首次真实语义Embedding与评测、Reranker与评测、文档约束的policymaker模式 | 作者名和历史账号可关联；不强行映射Proposal中的某个英文昵称或Scrum角色。 |
| 组员 D | 初始回答模式、evidence gating、写作风格与回答目的拆分 | 历史账号与unknown可由共同身份信息关联；unknown不是无人负责。 |
| 待完整映射的其他作者 | 引用面板`7f1ed1e`、会话所有权与测试`f793f89`等记录；另有合并账号 | 用户允许以组员E代称，但目前不足以确认这些标签是否同一人，故保留E1/E2等历史记录，不虚构实名归并。 |

六人团队由 proposal 和用户陈述支持；“Git 出现 16 个作者名”并不说明有 16 个成员，也不允许凭猜测把 16 个标签完全压成 6 个人。

### 原课程 PR 史：实现时间、集成时间、发布点分别记录

GitHub 原课程仓库为 `unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread`。本人个人仓库当前没有 PR，并不代表课程开发没有 PR。本次通过 GitHub API 取到 63 条原课程 PR 元数据，保存于 `tmp/interview-kb-course-prs.json`；下表 merged_at 均转换为北京时间，不把 closed_at 当 merged_at。

| PR | 北京时间 merged_at | 目标分支 | 真实变化/历史作用 | 代码定位 |
|---|---|---|---|---|
| [#5](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/5) | 06-28 06:06:40 | develop | 组员 A 的业务域模块化及文档 ID 对齐 | `1e1503e`，head `5f22905` |
| [#8](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/8) | 06-28 15:03:34 | develop | 回答风格和初始 evidence gating；PR 账号与组员 D 功能分支对应 | `506830c` |
| [#13](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/13) | 06-29 16:25:22 | develop | 组员 C 的真实语义 embedding 与评测 | `9758c3d`，head `ee046b1` |
| [#14](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/14) | 06-29 22:19:54 | develop | 组员 C 的 reranker，稠密候选扩大和失败回退 | `0c68c36` |
| [#18](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/18) | 07-19 06:04:19 | develop | 本人：引用、tiktoken、Provider 和初步多轮字段；作者提交 07-09，直到 07-19 才合入 | `97b8b20` |
| [#19](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/19) | 07-19 20:26:56 | main | 早期写作风格与回答目的拆分先入 main | `221b01c`，GitHub历史merge [96ef729](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/commit/96ef7295a4994b570f56bab37fa9f02ac79123e3) |
| [#21](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/21) | 07-20 20:11:15 | develop | 同类模式拆分再向 develop 整合 | `0c7dd2a` |
| [#22](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/22) | 07-20 21:14:54 | develop | 本人：会话/引用面板和双信号证据判定；PR 写明解决多个冲突 | `845b592`、`8001f66`，merge `cc50430` |
| [#27](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/27) | 07-21 10:59:22 | develop | 组员 A：模型 tokenizer 分块、聊天布局和 Library 编辑/详情 | `bca8c3e`，head `6c8f106` |
| [#30](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/30) | 07-21 15:25:20 | develop | 会话所有权校验及独立 router 测试 | `f793f89` |
| [#35](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/35) | 07-21 23:14:20 | develop | 本人整合 Demo1.2 修复批次与组员 C 的 policymaker 模式 | `e1ff9cf`、`d079901`，head `b48f9e6` |
| [#36](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/36) | 07-22 00:09:14 | develop | 组员 A：扫描 PDF OCR 和多格式上传 | `189c645`、`0106ccb` |
| [#37](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/37) | 07-22 00:57:28 | develop | 本人：SSE 实时回答、引用保留、模式选择器交互 | head `d15c6ed` |
| [#41](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/41) | 07-27 20:57:51 | develop | 本人：两级分类、标签语义归一、contextual chunks；结构感知切分明确 TODO | `96d78e4` |
| [#42](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/42) | 07-28 02:37:02 | develop | 本人：SHA-256 去重；PR 明确 UNIQUE(sha256) 是竞态兜底，L2/L3 当时仍 TODO | `5de9b2d` |
| [#44](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/44) | 07-29 17:55:19 | develop | 本人：Embedding/Reranking Provider 和 Manage 界面整合 | `c238a96`、`39134ab` |
| [#45](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/45) | 07-29 17:56:28 | main | 本人发起 Version 2.1 发布合并 | `56ea44f` |
| [#46](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/46) | 07-29 18:22:07 | develop | 本人：模型目录/API 配置等 Demo1.2_ZZP 后续整合 | head `30cc929` |
| [#47](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/47) | 07-29 18:23:21 | main | 本人发起 Version 2.2 发布合并 | `4da55ea` |
| [#48](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/48) | 07-30 01:18:49 | develop | 本人：目录驱动的模型设置收敛 | `450e1ce` |
| [#49](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/49) | 08-01 06:47:15 | develop | 本人：答案后推荐追问及其优化 | head `cd1af0b` |
| [#50](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/50) | 08-02 17:18:14 | develop | 组员 A：ReAct/WebSearch/PG checkpointer/resume 主体 | `2c73aa7`、`a6e6da5`、head `da1f8ee` |
| [#51](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/51) | 08-03 03:53:40 | develop | 本人：共享检索/网页导入及 Chat 应用边界第一批 | `5128b35`—`4a768b3` |
| [#52](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/52) | 08-03 20:41:06 | develop | 本人：流式驱动拆分、过滤与治理、协议恢复和检索修复 | `fd738fc`、`989ce8f`，head `d4ad453` |
| [#54](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/54) | 08-04 13:54:35 | main | 本人发起阶段发布合并 | `82ac297` |
| [#55](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/55) | 08-04 14:02:51 | develop | 本人：删除 legacy crawling | `10ed6d9` |
| [#58](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/58) | 08-04 21:31:14 | develop | 本人：文档并发处理队列 | `b8e6acd` |
| [#60](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/60) | 08-06 23:51:49 | develop | 本人：BM25/RRF、documents service 拆分和一批边界修复 | `fbfa781`、`889bd34` |
| [#62](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/62) | 08-10 15:31:54 | develop | 本人提交 finalhandover；管理员邀请、Docker 与交接 | head `65e58ad`，merge `895a380` |
| [#63](https://github.com/unsw-cse-comp99-3900/capstone-project-26t2-9900-w11c-bread/pull/63) | 08-11 16:25:47 | main | 本人发起最终 develop→main；由前端成员账号执行最终合并 | head `b56be8d`，merge `117f6c9` |

这些 PR 主要证明“什么内容通过哪个分支、在何时整合”。PR 提交者不等于 PR 内所有原始 commit 的作者。#35 最有价值：PR 正文明确分清本人修复批次与组员 C 的 policymaker，并说明两个冲突的解决方式。`document_ids` / `filenames` 不能回退到混用的 identifiers，否则会复发检索失败；restoreSession 需要同时保留 answer mode 恢复和 policymaker 强制 analysis。这是可拿来说明团队协作与回归风险的具体案例。

另外，closed-without-merge 不等于功能被废弃。11 条未直接 merged 的 PR 为 #10、#20、#23、#24、#25、#26、#28、#29、#33、#34、#56；其中九条的 head commit 已经通过其他整合路径成为课程 main 的祖先。#28/#29 的同一个 head 对象本地未获取，本审计不推断其最终是否采用。比如 #34 与实际合入 develop 的 #35 对应同一整合 head，不能把两条 PR 当两次开发，也不能因 #34 关闭就说其功能没交付。

PR 正文里的性能/质量自述应另行验证：#14 写过 Recall@3=100%、重排 Top-1=75%，#37 写过检索完成后约 1—2 秒见到首 token。这些是当时作者在特定环境中的描述，不能脱离评测集规模、模型、硬件和请求分布，在简历上改写成平台普遍 SLA 或全量数据效果。

<a id="kb-15"></a>

## 15. 大规模重构案例与面试讲述方式

### 案例 1：为什么已经分模块，还要继续重构

可以这样答：“6 月底按 auth/chat/documents 等业务域拆模块，解决目录和领域边界问题。随着 ReAct、Direct、推荐追问同时出现，检索和证据决策在三个入口重复，Agent 还直接调用 Direct 图节点。8 月我把这些能力提到共享 RetrievalService，同时将会话生命周期、SSE 编码和流式执行从 router 拆开。这两次重构处理的是不同层次的问题。”

证据：`1e1503e` 对比 `8abc5ef`、`2b024f5`、`fd738fc`；动机清单在 `CHAT_REFACTOR_STRATEGY.md`。收益是复用、一致行为、故障定位和无 HTTP 的服务测试；没有测得数字就不要报“延迟降低 50%”。

### 案例 2：为什么先固定 RAG，再引入 Agent，而没有从第一天做多 Agent

可以这样答：“最初只是从所选政策文件找依据，用固定图更可控。后来出现文档不足需要扩到全库、用户要求联网、确认是否把网页入库等多步流程，才在七月底加 ReAct。原 Direct 保留，简单问答不用承担每轮工具规划的额外成本。工具调用又受到权限、预算和检索层级规则约束。”

证据：`0faae82`、`506830c`、`2c73aa7`、`fbb2b74`、`46726e3`。需要承认初始 ReAct/checkpointer 主要由组员 A 落地，本人后续做共享能力、工具策略与协议恢复等工作。

### 案例 3：Provider 抽象解决了什么，而没有解决什么

可以这样答：“最初 embedding/reranker 是固定本地模型。后来要接 API 模型和按管理设置切换，我们抽 Provider、运行配置和目录解析，并把向量数据按模型/维度隔开，减少更换模型对业务流程的侵入。”

证据：`9758c3d`、`0c68c36` 到 `c238a96`、`39134ab`、`450e1ce`。需要继续解释模型切换后的向量兼容性、重建和阈值变化；Provider 接口本身不会保证新旧 embedding 在同一个语义空间，也不会自动给所有模型产生可比较的 reranker 分数。

### 案例 4：为什么把网页入库集中起来

可以这样答：“最初管理端和 Agent 各自走导入逻辑，URL、标题、内容限制与去重返回不同。这样会出现一个入口拒绝、另一个入口接受的情况。我收敛到同一个 WebImportService，再让权限和用户确认保留在各自入口。这样公共 URL 安全校验、永久文档处理和去重结果一致。”

证据：`4dd8cae` → `544926f`、`364a49e`、`3e2fb15`。避免声称只靠 system prompt 就完成权限控制，也不要把网页实时搜索结果和永久导入后政策库中的文档视为同一个生命周期。

### 案例 5：为什么后台任务又从 BackgroundTasks 变为队列，再变为数据库任务

可以这样答：“第一阶段主要防止 PDF/OCR 阻塞请求，所以先转后台；后来批量上传要限制 OCR 和模型并发，八月加了单进程三个 worker 的队列；交付后继续做可靠性时，发现进程重启会丢内存任务、多进程也不能靠一个内存 set 去重，十月改成数据库持久任务、lease claim、重试与幂等注册。”

证据：`2bf9088` → `b8e6acd` → `7aaf075` / `d52fdfc`。这个叙述能解释工程约束如何逐步变化。不要把十月实现倒写成六月就有，不要声称 CPU 密集 OCR 通过 async 语法本身就变快。

### 案例 6：为什么删掉数千行 crawler

可以这样答：“项目早期有来源配置、批量爬取和附件采集链路。后来交付核心转到研究人员上传文档、Agent 必要时联网找证据，再经确认永久入库。旧 crawling 子系统和新路径重叠且带来依赖与维护成本，所以八月删除，保留新搜索/导入仍需的 URL 安全能力。”

证据：早期 `374620f`、`56771cb`、`1e1503e` 与 `10ed6d9`。真实收益是收窄产品范围与维护面；Git 删除 4,616 行并不能证明已自动消除了所有安全问题或云成本。

### 为什么保留 Direct 和 ReAct

一次检索能够回答的问题，固定流程更便宜、更容易预测和测试；需要澄清、扩展证据或用户确认的任务才需要工具循环。ReAct 的优势是根据观察决定下一步，代价是额外模型轮次、协议错误、状态管理与安全边界。项目没有必要把每个问题都变成长链 Agent。

### 项目中的四种“恢复”不能混用

LangGraph interrupt/resume 恢复的是人工暂停的图任务；文档 task lease 恢复的是 worker 失联后的后台处理；上传 Idempotency-Key 处理的是响应丢失后的业务重放；SSE 重连处理的是浏览器流传输。实现了其中一项，不代表其他三项自动成立。尤其当前上传不支持网络分片续传，SSE 也没有完整的 event-id 断点重放。

### 项目中的四种“并发上限”不能混用

Repository 池上限约束借出的 DB 连接；文档 worker 槽位约束正常调度的业务任务；header 六线程约束单批可选模型调用；工具预算约束一轮 Agent 可接受的动作次数。它们都不是全站用户数或 QPS 限制；增加进程会放大连接、模型和 CPU 资源占用。

### 可用于个人经历回答的重构案例

个人经历优先采用有 Alem42 提交证据的案例：8 月的 Chat 路由／生命周期／检索黑盒拆分；BM25＋RRF 与文档服务分层；V2 连接池和有界上传；持久任务、租约与原子发布；迁移缺表诊断和可选模型等待预算。每个案例讲“旧代码怎么出问题、边界如何重划、兼容如何保持、用什么故障验证”。

模型训练、完整多租户、高可用和大规模检索调优没有相应实现或验证证据，不应当成个人已完成经历。其他成员最初实现的 OCR、真实向量／reranker、ReAct 等功能可以作为团队技术背景，再准确说明本人后来接手的协议、分层和工程优化。

### Git 演进：能解释动机的重构故事

下表日期取 Git AuthorDate 的日历日，7–8 月原时区为 +10:00；10 月为 +08:00。若展示小时，应统一换算 Asia/Shanghai。SHA 与作者只证明仓库记录；口述个人职责仍需要本人确认。

| 提交 | 日期 / 作者 | 变化与可讲的工程动机 | 当前 HEAD 是否包含 |
|---|---|---|---|
| `a6e6da5` | 2026-07-30 / 组员 A | 应用启动接入持久 Postgres checkpointer，为跨请求暂停/恢复提供状态基础 | 是 |
| `b917e5d` | 2026-07-30 / 组员 A | ReAct 接入 /chat/stream，新增 /chat/resume | 是 |
| `282b0a1` | 2026-07-30 / 组员 A | 前端确认对话框与 resume 交互闭环 | 是 |
| `da1f8ee` | 2026-08-01 / 组员 A | 每轮与每工具决策 token 展示/保存；需解释统计口径 | 是 |
| `16ead37` | 2026-08-03 / Alem42 | 从 Agent graph 提取 policy，把网页证据处理从 tools 拆到 agent_tools/web_evidence | 是 |
| `2b024f5` | 2026-08-03 / Alem42 | 提取 StartTurnRequest/StartedTurn、ChatTurnService、Direct/React facade、SSE helpers、token/citation helpers | 是 |
| `fd738fc` | 2026-08-03 / Alem42 | 将 Direct/ReAct 流驱动从 router 移到 application/streaming，HTTP router 不再持有执行循环 | 是 |
| `4e76edd` | 2026-08-04 / 组员 A | 工具预算改成管理员配置，prompt/绑定策略需同一快照 | 是 |
| `ae4c53f` | 2026-08-06 / Alem42 | 删除 AUTO_FINALIZE backstop，显式 prepare 成为正常退出路径 | 是 |
| `46726e3` | 2026-08-06 / Alem42 | 固定 tier ladder 的首轮工具可见性约束；不要夸为所有授权都有硬 guard | 是 |
| `663c348` | 2026-08-07 / 组员 A | 从 session 网页历史解析 import 目标，避免模型凭记忆拼 URL | 是 |
| `9c78815` | 2026-08-10 / Alem42 | UI 删除 policymaker 选项并保留旧会话兼容；同一提交修复收到 interrupt 后过早关流/重复 resume 的时序，不能仅看标题理解范围 | 是 |
| `c79f5d3` | 2026-08-10 / Alem42 | 默认全库搜索预算改为 1；仍可管理员调大 | 是 |
| `db8cf39` | 2026-08-15 / Alem42 | canonical execution profile；权限、执行、表现三维解耦的兼容基础 | 否，独立分支 |
| `bf8d21c` | 2026-08-15 / Alem42 | 抽 PolicySearchCapability，为 Agent/eval/MCP 复用提供稳定入口 | 否 |
| `949a4d6` | 2026-08-15 / Alem42 | run context 和配置/提示版本标识，跨 resume 保留逻辑请求身份 | 否 |
| `f714732` | 2026-08-15 / Alem42 | provider-neutral 事件契约与 sink | 否 |
| `bef38b9` | 2026-08-15 / Alem42 | foundation 行为测试，新增 canonical source_policy 工具过滤 | 否 |
| `c4ba4fe` | 2026-08-15 / Alem42 | sanitized run event 的 PG 持久化和序号治理 | 否 |
| `4a573c7` | 2026-08-15 / Alem42 | Direct/ReAct 应用驱动埋点 | 否 |
| `aeac2b0` | 2026-08-15 / Alem42 | 管理员 run trace 查询 API | 否 |
| `136cf86` | 2026-08-15 / Alem42 | Compose 挂载 run event migration | 否 |
| `e6f7861` | 2026-08-15 / Alem42 | FastMCP governed policy search stdio server 与协议测试 | 否 |
| `0b22809` | 2026-08-15 / Alem42 | MCP 检索接入 run events | 否 |
| `d52fdfc` | 2026-10-15 / Alem42 | durable document tasks 主变更同时清理 async 中同步设置/模型构造路径，降低 event loop 饥饿风险 | 是 |

#### 如何说明 8 月 Chat 重构

“原 router 同时管 HTTP、会话写入、LLM/工具循环、流式转换和数据库回写，需求一变容易改动整块。先提取可替换的生命周期服务和 facade，再提取 stream driver 与 SSE mapper，把会话归属、历史读取顺序、trace 格式和暂停语义固定下来。重构保留公开协议，测试重点围绕这些行为。”

证据不仅是提交标题：`16ead37` 的 diff 把 graph 中工具集合/预算筛选搬到 policy；`2b024f5` 新建应用 dataclass 和 service，用 service 替换 router 内直接 repository 操作；`fd738fc` 将大量流循环从 router 移到 streaming。不要说只是“为了文件小一点”，也不要把 alias facade 薄包装吹成复杂调度引擎。

#### 为什么显式 prepare 而不自动 finalize

强制 prepare 保留一个清楚的研究完成动作，UI trace 可显示计划与引用号，最终生成不再和研究节点输出混用。但代价是多一次决策调用、模型协议依赖和额外 latency/token。代码用预算/协议纠正/fallback 降低卡死风险；不能说不存在成本。

#### 独立分支未来合并需处理的具体冲突

当前 HEAD 有 `backend/database/migrations/028_durable_document_tasks.sql`；实验 observability 分支有 `028_add_agent_run_events.sql`。同编号来自独立历史，集成时需要按项目迁移机制重编号/核对 init.sql 与 Compose 挂载，不能直接因两个 filename 不同就认为迁移顺序无风险。

此外实验分支基于旧的 DB/文档任务实现，当前 async to_thread、连接池和入库执行路径已演进；不能简单复制整个旧 streaming/router 覆盖当前文件。合并后还需回归旧 SSE schema、resume 身份/预算、完整 source_policy 传播、事件计数与 Token 口径。上述是集成建议，本知识库未执行合并或修复。

<a id="kb-16"></a>

## 16. 能力边界、技术术语与面试问题索引

1. 六至八月的课程交付和八月十五日/十月的个人继续开发分开讲；后一部分可以展示技术深度，但不能冒充客户最初验收时的能力。
2. 初始语义 embedding/reranker 与初始 ReAct/checkpointer 有明确组员代码证据。本人可以讲统筹架构、整合、后续重构和优化，但不能说所有实现都是本人从零独立编写。
3. 所有 feature 分支不能合并想象成一个运行版本；尤其当前 durable HEAD 与 MCP 支线是兄弟方向。
4. proposal 的技术选型是设计方案；具体实现以对应 commit tree 为准。Next.js、section-aware chunking、模板约束 Agent 等应当解释为方案和后续选择之间的差异。
5. “用 LangGraph”“有 Agent”“有 checkpoint”“有业务聊天历史”“有 SSE 重连重放”“有持久任务”是六个不同层面的事实，不能互相代替。
6. Commit author、committer、PR merge 发起人、实际代码设计者和团队角色可能不同；不要以 merge 数确定功能所有权。
7. 本次没有审核云服务器版本与部署流水线，不能从 Compose/Dockerfile 推导“每个提交都已部署 Azure”。
8. 文档里记载的测试数量、前端包体数字、阈值经验和 live verification 是历史记录；本次只是审计，不假装重新测量。没有可重复的检索 benchmark 对照，就不应编造 Recall/MRR 提升百分比。

### 面试表述的分界与可以继续深入的技术点

| 可以直接说 | 应当加条件/不能直接说 |
|---|---|
| LangGraph 实现模型决策—工具执行的 ReAct 循环 | 多 Agent 自主协作、完整 planner/executor 系统 |
| PostgreSQL checkpoint 支持人工澄清和入库确认的跨请求恢复 | 所有网络断线、Stop 和进程崩溃都 exactly-once 自动继续 |
| 可用工具按角色、模式、单轮次数过滤 | 所有网页授权都由硬状态机保证，模型违规也无影响 |
| 服务端生成文档/页码/片段与引用编号 | 每条答案事实都做过逐句蕴含验证、坐标级引用 |
| ReAct 保存步骤与 provider reported token 汇总 | 当前 HEAD 有全链路 run events、所有模型成本与耗时完整统计 |
| 后续分支实现 governed MCP 检索服务 | 当前 main 已部署 MCP，六种 Agent 工具全都走 MCP |
| canonical profile 为解耦建立兼容模型 | 新 profile 已替换 API/数据库并实现 deep_research |
| 把同步 DB/配置访问放入工作线程减轻事件循环阻塞 | to_thread 等于 CPU 无限并行、wait_for 能杀死底层线程 |
| 有针对权限、预算、引用、恢复和协议的单元/契约测试 | 所有测试都是生产数据库、真实模型、浏览器端到端测试 |

可用于准备的深入概念：workflow 与 agent 决策权区别；LangGraph state channel / reducer / checkpoint；tool call ID 与 ToolMessage 配对；LLM tool schema 与执行鉴权的信任边界；at-least-once 重放下的幂等和 outbox 思路；SSE 断线重放与业务 resume 的区别；请求级 deadline 与线程取消的区别；相关性与答案忠实度的区别；TTFT、整轮 latency、用户等待和恢复阶段的计时口径；日志脱敏白名单、event sequence 与 execution concurrency 的区别。

这些概念中未落地的部分，应以“如果继续做生产化，我会……”说明，再明确当前缺口；不能把改进方案倒写成简历已有成果。


### 核心术语速查：帮助面试 Agent 解释原理

| 术语 | 在本项目中的准确含义 |
| --- | --- |
| RAG | 从外部资料检索证据，构造上下文再生成答案。解决知识接入与来源范围，不自动保证无幻觉。 |
| Agentic RAG / ReAct | 模型根据工具观察选择后续动作；本项目是单研究 Agent 加最终 writer。 |
| LangGraph StateGraph | 用节点、条件边、状态及 reducer 编排；固定工作流与 Agent 图都能使用它。 |
| Function calling | 模型输出结构化动作参数；应用负责执行、权限与预算。 |
| MCP | 外部 host/client 与工具 server 的发现和调用协议；VX 采用 stdio，不等于 Function calling 或普通公网 REST。 |
| Bi-encoder | 查询和文档独立编码，文档向量可预计算；适合大集合召回。项目调用已有模型，没有训练 encoder。 |
| Cross-encoder | 联合读取查询与候选进行匹配，通常用于小候选集精排；项目使用本地库或 API。 |
| Dense / sparse | Dense 使用连续向量；本项目 sparse 是词项倒排 BM25，不是训练的 SPLADE 模型。 |
| TF / DF / IDF | TF 是词在某 chunk 的次数，DF 是含该词的 chunk 数，IDF 下调常见词的区分力。 |
| BM25 k1 / b | k1 调整词频饱和，b 调整文档长度归一化；当前默认 1.5/0.75，没有大样本最优性证明。 |
| RRF | 按多个排序中的名次累计倒数贡献，避免直接混加不同比例的原始分数；默认平滑常量60。 |
| Top-K | 返回的结果数；与 RRF 的平滑常量和 HNSW 的 ef_search 不同。 |
| HNSW | 分层近邻图索引；本项目固定 cosine ops，未提供大规模调参或每次查询一定走索引的证明。 |
| IVFFlat | 聚类分桶的近似检索方法，是可比较方案，不是本项目当前采用的索引。 |
| Evidence gate | 检索相关性、长度、专名与地区覆盖约束；不是逐 claim 的事实蕴含验证。 |
| Citation / grounding | 引用标记及来源映射／基于给定证据生成；字段存在不代表来源支持全部结论。 |
| Checkpoint | 图状态与执行恢复点；与界面聊天历史、文档后台 task 不同。 |
| interrupt/resume | 人工暂停后以同 thread 继续，节点会重跑相关前缀；不是恢复任意 Python 栈。 |
| Lease / heartbeat | 限时任务执行资格及续期；失联后可接管，不保证外部计算只运行一次。 |
| Fencing / owned | 通过 token、状态、租约及行锁检查发布资格，阻止旧持有者覆盖新结果。 |
| Idempotency | 相同业务请求重复执行后效果收敛；文件 hash、请求键和任务发布保护分别处理不同故障窗口。 |
| SSE | 单向服务器事件流；当前浏览器用 POST fetch 读取，业务 resume 是另一次请求。 |
| TTFT | 首 Token 延迟；VX 事件测量当前驱动阶段，不能自动覆盖人工暂停之前与等待期间。 |
| P95 | 样本中95%请求不超过的耗时；必须说清接口、样本、环境与时间，不能把目录读取P95当模型回答P95。 |
| Connection pool | 重用数据库连接并约束借用等待，不是文档 worker 或用户连接数。 |

### RRF 手算与现场编码思路

如果 dense 为 A、B、C，BM25 为 B、D、A，平滑常量60，则 B=1/62+1/61≈0.032522，A=1/61+1/63≈0.032266，D=1/62≈0.016129，C=1/63≈0.015873，结果为 B>A>D>C。缺席某一路不贡献分数，不能把其 rank 当0。项目按 chunk_id 合并，保留 dense distance 并补 sparse score，非按文档去重。

现场实现可用哈希表累积分数，输入总量N、不同候选数U，完整排序约O(N+U log U)、额外空间O(U)。若只要K且K远小于U，可用容量K的堆，约O(N+U log K)，最后明确并列规则。同一路异常重复项应先去重，避免重复加分；当前产品实现假设两路各自返回的chunk唯一，并没有完整处理所有恶意输入。RRF只看排名会丢失原始分数差距，不能声称它永远优于经过标注校准的加权融合。

### 对此前16道面试问题的检索索引

| 题目方向 | 推荐检索章节 | 回答中必须保留的事实 |
| --- | --- | --- |
| 项目价值、个人贡献和为什么Agent | 00、01、02、14、15 | 六人团队；本人Alem42；Direct/ReAct并存；原始模块与本人重构分开。 |
| ReAct、LangGraph、终止与错误 | 05 | 五业务节点、六工具、显式prepare、有限协议纠正、预算。 |
| Schema、权限、提示注入 | 05、06、16 | 后端注入身份；工具可见性与执行权限区分；联网有部分prompt依赖。 |
| Checkpoint和resume幂等 | 05、08 | 图恢复不等于exactly-once；文档任务lease不等于会话互斥。 |
| MCP与Function Calling | 11 | 仅VX；stdio检索入口；不是六工具全部MCP化。 |
| PDF/DOCX/OCR和chunk | 03 | 物理页、DOCX page1、默认英文OCR、token/段落/句子切块。 |
| Embedding、距离、pgvector | 03、04 | 每模型空间隔离；cosine/HNSW；新模型缺向量才需重嵌入，已有模型空间可复用。 |
| BM25 | 04、16 | chunk粒度、k1/b、CJK bigram、进程内scope索引。 |
| RRF和TopK手撕 | 04、16 | rank融合、chunk_id、完整排序/堆复杂度、非独立sparse兜底。 |
| Reranker | 04 | 召回与精排分工；API空结果和真正异常不同；回退可能是RRF顺序。 |
| 证据充分性和引用 | 03、04、05 | 有引用不保证蕴含；页码/quote/多地区覆盖的具体边界。 |
| Recall、MRR、消融评测 | 12 | 当前12英文合成集与VX15中英文smoke不同；没有同集hybrid收益结论。 |
| FastAPI异步与SSE | 05、07、09 | to_thread目的；abort、interrupt、重连不是一回事。 |
| Token、成本和延迟 | 05、11、12 | 当前trace不等于统一事件；usage有遗漏；历史小样本不是生产指标。 |
| 百万级/多用户/多租户 | 07、08、16 | 已做连接/任务约束；未做完整租户、对象存储、外部限流和规模验证。 |
| 技术难题、重构与团队协作 | 13、14、15 | 用问题、前后diff、兼容、测试讲；不要只列目录或把合并者当全部作者。 |

### 给面试辅助 Agent 的回答约束

优先回答已经实现的机制，再补一句影响结论的实际边界。不要在每个回答开头泛泛否定整个项目，也不要为迎合面试官而编造训练、规模、效果或个人独占贡献。使用第一人称时，只将用户确认的个人职责及有本人工作线证据的改动转为“我”；组员原始实现保持“团队／组员先完成，我后续负责某部分整合”。

如果问题涉及版本，先声明V1、V2、VC或VX。涉及实验结果时给出日期、数据集、接口、模型与样本范围。涉及Document Analysis质量时，测试问题应先能从所选文档回答，优先依据数据库chunk选择；缺少文件或provider响应异常先判为前提／集成问题。需要追问用户本人经历的内容包括具体客户沟通、某项取舍由谁拍板、答辩结果和云部署过程，知识库不能替用户补写没有证据的故事。

<a id="kb-17"></a>

## 17. 证据索引、Git复核命令与后续维护

以下命令故意不输出邮箱：

```powershell
git log -1 --format="%h | %aI | %an | %s" HEAD
git log -1 --format="%h | %aI | %an | %s" origin/main
git rev-list --left-right --count origin/main...HEAD
git rev-list --left-right --count origin/main...feature/mcp-and-mode-simplification
git merge-base origin/main HEAD
git log origin/main --first-parent --reverse --format="%h | %aI | %an | %s"
git shortlog -sn --no-merges origin/main
git shortlog -sn --merges origin/main
git show --format= --stat 1e1503e
git show --format= 9758c3d -- backend/app/modules/documents/embeddings.py
git show 0faae82:backend/app/rag/graph/workflow.py
git show 2c73aa7:backend/app/modules/chat/rag/agent/graph.py
git show a6e6da5:backend/app/modules/chat/rag/checkpointer.py
git show --format= d15c6ed -- backend/app/modules/chat/router.py
git show --format= --stat 2b024f5
git show --format= --stat 10ed6d9
git show --format= --stat d52fdfc
git rev-parse Demo1.2_ZZP^{tree}
git rev-parse backup/Demo1.2_ZZP-rewritten-history^{tree}
```

注意：PowerShell 中带特殊字符的 rev 参数可按实际 shell 加引号。`git show SHA:path` 展示的是历史文件，不必为了检查历史去 checkout 或覆盖当前文件。


### 项目证据入口与复核范围

| 证据 | 本知识库用它证明什么 |
| --- | --- |
| 当前受Git跟踪的310文件、295文本文件索引 | 代码范围与目录，不把缓存／ignored报告当主线实现。 |
| 个人仓库origin及原课程course-audit refs | 两个仓库真实分支祖先、兄弟实验线与最终课程版本。 |
| 原课程63条PR metadata、关键diff | 开发者与合并者、功能引入和整合时间、冲突与回退。 |
| 历史PR #19的merge对象96ef729 | 本地现有ref不含该对象，已另外通过GitHub commit API核对，不能据此把它当当前HEAD祖先。 |
| 关键PR #35/#50/#52/#60/#62讨论 | 附加复核；除#50一条简短确认外，接口未返回完整技术评审讨论，不能据空列表编造review内容。 |
| 原课程Issue查询 | 当前接口返回独立Issue列表为空；任务主要参考Jira与PR，不推断项目从未有过线下问题。 |
| proposal.pdf（37页） | 六人/Scrum角色、业务需求、最初设计；不是功能完成证明。 |
| 工作区旁JiraStory.xml（36项） | 六月下旬用户故事分工与当时状态；不是最终验收或代码作者清单。 |
| CHAT_REFACTOR_STRATEGY.md | 八月重构问题、依赖方向、兼容阶段与当时验证记录。 |
| BM25_HYBRID_RETRIEVAL.md | 混合检索设计意图；若与实际脚本能力冲突，以代码为准。 |
| CONNECTION_POOL_AND_UPLOAD_GUIDE.md / DURABLE_DOCUMENT_TASKS_GUIDE.md | 十月阶段性实现、机制解释和验证；第一阶段的内存队列描述不能当第二阶段最终状态。 |
| DATABASE_RUNTIME_REPAIR_2026-10-15.md及verification/*.json | 故障、修复和当日脱敏验证；不是本次重新执行。 |
| 后端README、API_CONTRACTS、GIT_WORKFLOW | 安装/API/协作入口；出现旧路径、旧默认值或master命名时，以对应当前代码/ref为准。 |
| 输出演示指南和样例PDF | 演示材料与业务背景，不代表整个样例目录都已入部署数据库。 |

### 主要代码定位地图

| 位置 | 适合核对的内容 |
| --- | --- |
| backend/app/main.py | lifespan、schema检查、队列、上传middleware、503handler。 |
| backend/app/core/config.py / database.py / upload_limits.py | 默认预算、进程池、请求体限制。 |
| backend/app/core/ai/chat_models.py | provider/model解析、兼容客户端与可选timeout/retries。 |
| backend/app/modules/documents/service/{library,pipeline,retrieval}.py | 文档管理、入库/重扫/重嵌入、混合召回。 |
| backend/app/modules/documents/{file_store,processing_queue,worker,upload_registration}.py | 暂存、worker、lease生命周期、上传原子注册。 |
| backend/app/modules/documents/repositories/{tasks,content,embeddings}.py | 任务持久化、页面元数据、向量与最终提交。 |
| backend/app/modules/documents/ingestion/ | metadata、taxonomy匹配、contextual header、语言。 |
| backend/app/modules/{embedding,reranking,retrieval}/ | provider、距离／阈值、BM25/RRF、统一证据语义。 |
| backend/app/modules/chat/{router,application,orchestration,api}/ | HTTP、会话生命周期、流驱动、编排和SSE。 |
| backend/app/modules/chat/rag/agent/ | ReAct图、状态、工具、prompt、策略。 |
| backend/app/modules/chat/rag/{checkpointer,generation}.py | 图状态持久化与模型生成。 |
| backend/app/modules/{web_search,documents/web_import.py,documents/web_governance.py} | 搜索、URL安全、永久导入与治理。 |
| backend/app/modules/auth/ | 自定义HMAC token、PBKDF2、邀请与角色依赖。 |
| frontend/src/{App.jsx,router.jsx,api.js,pages/ChatPage.jsx} | 全局来源、路由、传输协议与对话状态。 |
| frontend/src/components/{DocumentUpload,DocumentTasks,DocumentDrawer,CitationList}.jsx | 上传/任务反馈、资料详情和引用。 |
| compose.yaml / Caddyfile / backend/Dockerfile / frontend/Dockerfile | 实际单套服务交付及持久化边界。 |
| VX: backend/app/mcp_server/、chat/domain/、chat/capabilities/、chat/runtime/、modules/evaluation/ | 仅用git show对应实验ref阅读，当前HEAD不存在这些文件。 |

### 资料更新规则

将来合并MCP与durable分支后，需要更新版本表、迁移编号、依赖清单、启动/测试结果及本文件中“当前不存在”的描述；不能只把一行状态改成已合并。新增性能数字必须保留原始报告及数据集/配置。成员身份进一步确认后可以更新匿名映射，但不要据此改写他人提交原始事实。

本文件未收录秘密配置、数据库备份或用户对话正文。普通数据库表只按职责介绍；精力集中在AI链路、行为边界、事务/恢复、真实重构和团队协作。
