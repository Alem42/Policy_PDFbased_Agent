# Qwen 本地模型、测试语料和评测：实现与验证记录

> 后续已执行分块／阈值实验、全量重建和 token 预算控制；当前配置与结果请看 [RAG 实验与成本记录](RAG_EXPERIMENTS_AND_TOKEN_BUDGET.zh-CN.md)。本文中的 512/64 和 27 题结果是历史起点。

验证日期：2026-10-23。适用分支：`feature/qwen-evaluation`。本文记录已经实现的功能和真实测量结果，并单独列出后续参数实验方案。512 token、64 token overlap 和各项阈值是本轮起点，不是已经证明最优的参数。

## 1. 本次交付与边界

Management 保留原来的 Embedding model / Reranker 设置，新增 Qwen 本地模型选项、切块 overlap、GPU 空闲释放时间，以及并列的 **Evaluation & scoring** 页面。既有的 Save Embedding Setting、Re-Embed Library 和 Rescan all documents 继续调用原有服务与持久化任务队列。新模型接入 embedding/reranking 的 provider 层；评测通过既有检索和回答接口调用实际系统，没有另写一套“评测专用检索器”。

评分页支持保存评测设置、导入官方测试 PDF、启动/查看/取消评测、导出完整 JSON，以及逐题保存人工评分和理由。评测队列独立存放运行记录、配置快照、案例、检索结果、输出和人工 review，不把测试污染成用户的聊天记录。管理员接口均要求现有管理员身份。

本轮不改写 Agent 工具循环、聊天记忆、网页搜索和数据库主体结构。评测基线固定为 Document Analysis：限定已选文件、无聊天历史、无网页搜索，证据门控不通过时直接返回原系统的不足证据消息，不调用回答生成模型。它验证的是文档问答链路，不代表 ReAct 工具选择、中断恢复和 SSE HTTP 链路都完成了同等规模的实时评测。

## 2. 已安装的模型和运行方式

| 项目 | 本机验证值 |
| --- | --- |
| GPU | NVIDIA GeForce RTX 5070 Ti，约 16 GB 显存 |
| PyTorch | 2.11.0+cu128，CUDA 可用 |
| Transformers | 4.57.6 |
| Embedding | Qwen/Qwen3-Embedding-0.6B，1024 维 |
| Reranker | Qwen/Qwen3-Reranker-0.6B |
| Embedding 权重版本 | 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 |
| Reranker 权重版本 | e61197ed45024b0ed8a2d74b80b4d909f1255473 |

项目根目录 `.venv` 已安装真实 CUDA 依赖；权重位于 `backend/data/model_cache/huggingface`。权重首次使用时下载，随后复用磁盘缓存。卸载是结束模型子进程、释放显存，不删除磁盘权重或反复卸载 Python 包。默认空闲 120 秒释放；设为 0 会在每次模型调用结束后释放，代价是下一次调用重新加载模型。评分页也提供手动释放按钮。

`app/modules/local_models` 用一个独立进程管理两种模型，进程内按模型名缓存，调用通过进程通信串行执行。这样文档处理的多个线程不会同时无界地争抢 GPU；退出进程也能释放 CUDA 上下文。请求失败或超时会丢弃工作进程，旧的空闲计时器不会卸载已被新请求使用的进程。切换回 API 或原有 fastembed 模型仍保留原路径。

GPU 使用 BF16 权重，Embedding 的最终向量转换到 float32 并做 L2 归一化。小样本同时加载两种模型后，记录的 CUDA 已分配量约 2.23 GiB；这是一次测量，不能当作任意批量和长文本下的峰值上限。Reranker 只保留末位置 logits，减少不必要的词表输出内存。模型输入连同模板有显式 8192 token 上限，超限报错，不静默截断证据。

Embedding 文档侧编码原文/已有 contextual header；查询侧添加 `Instruct: …\nQuery: …`，实现非对称编码。左填充后取最后一个有效 token 的隐层向量并归一化。Reranker 使用 Qwen 的指令、query、document 模板，读取末位置 yes/no 两个 logits，经 softmax 得到 yes 分数。这个分数不等同于已经校准的“答案可回答概率”。原 BGE 的负数 logit 阈值不能直接搬给它；Qwen 的设置范围为 0–1，本轮从 0.5 开始。

实现依据：[Qwen Embedding 模型说明](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)、[Qwen Reranker 模型说明](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)。

### Windows 启动

当前系统 Python 启动的旧后端已经替换为项目虚拟环境。新版 uvicorn 在 Windows 上的默认事件循环与 psycopg 异步 checkpointer 不兼容，因此提供在创建事件循环之前选择 Selector 的启动器。项目根目录执行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m scripts.run_backend
```

不要用系统全局 `uvicorn.exe` 启动这个 Qwen 环境。从 `backend` 执行 `python -m scripts.run_backend` 时，启动器会在系统 Python 下自动选用项目根目录的 `.venv`（其次为 `backend/.venv`），已经激活的虚拟环境则保持不变。2026-10-24 的 `No module named 'torch'` 就是全局 uvicorn 绕过项目环境导致；本机 `.venv` 中的 CUDA 依赖和已缓存权重本身正常。新机器需先按原 README 安装后端依赖，再安装 `local-models` extra；Windows CUDA 轮子应按 [PyTorch 官方安装页](https://pytorch.org/get-started/locally/)选择适合显卡的源。本次实际安装的是官方 cu128 轮子。Docker 的现有默认镜像未扩大为 CUDA 镜像；容器要使用 Qwen，需要安装该 extra，GPU 加速还需要配置 GPU 访问。

## 3. 数据库到底更新了什么

三类操作必须区分：

| 操作 | 文档解析/页面 | chunk 文本与 ID | 向量 |
| --- | --- | --- | --- |
| 保存设置 | 不变 | 不变 | 不主动重算；切换活动模型对应的向量表 |
| Re-Embed Library | 复用现有内容 | 保留现有 chunk | 删除并重写活动模型中对应的向量行 |
| Rescan all documents | 重新读取文件、OCR、解析、生成元数据 | 重新切块，新 ID 替换旧 ID | 与新 chunk 一起写入活动模型向量 |

原项目已经将全文处理的发布放在事务里：页面、元数据、chunk、向量和任务成功状态一起提交。耗时的模型计算在事务外完成。全文重处理删除旧 chunk 时，外键级联删除所有模型表中依赖旧 chunk 的向量；因此不能在改变切块之后继续复用其他模型的旧向量。Re-Embed 则不删除 chunk，不影响其他模型中仍匹配这些 chunk 的向量。

本轮实际通过现有 HTTP 接口保存设置、导入、全库 Rescan，再运行一次全库 Re-Embed，并直接查询 PostgreSQL 核验：

- 原有 7 份文件，186 个 chunk；导入后共 19 份文件。
- 全库 Rescan 后，19 份全部 ready；原有文件 ID 和 SHA256 保留，原来 186 个 chunk ID 剩余数量为 0。
- 当前共有 835 个 chunk 和 835 条活动向量；chunk ID 集合与向量所属 chunk ID 集合完全相同。
- 所有活动向量的模型标记为 Qwen/Qwen3-Embedding-0.6B，实际维数为 1024。
- 再次 Re-Embed 后，835 个 chunk ID 保持不变；通过 PostgreSQL 行版本事务号确认 835 条向量行均重新写入。
- 每份文件另抽取一个 chunk，连同其存储的 contextual header 用真实 Qwen 重新推理；19 个样本与库内向量的最低余弦相似度为 0.9996738，符合 BF16/批量差异下的 0.999 验证下限。
- 12 份测试文件均保留 `test-corpus` 标签；浏览器 Library 页面已实际显示标签和 ready 状态。

完整证据位于 `backend/eval-results/qwen-upgrade/`：`before.json`、`after-rescan.json`、`database-verification.json`、`before-reembed.json`、`reembed-verification.json`、`model-probes.json`。该目录属于本机验证产物，默认不进入 Git。保留的原聊天若引用旧 chunk ID，不能据此假设这些旧 ID 仍可定位；本次按授权替换旧索引。

## 4. 自带测试语料

资源在 `app/modules/evaluation/data/corpus-v1/`，包含原始 PDF、SHA256、官方来源链接、下载日期、版本、页数和使用说明。共 12 份、558 页，覆盖 AI 治理、隐私与数据安全、气候与能源、社会住房、网络安全与事件响应、生物安全，含中国、美国、英国和澳大利亚文件。

既有相似主题，也有明显不同的领域。相似主题用于测试检索器是否混淆政策名称、框架版本和类似术语；不同领域用于测试限定文件后能否拒答。每个文件的具体清单和来源见 manifest，PDF 内的原有声明完整保留，复用说明见 NOTICE。当前用于本机研究测试；没有将“公开可下载”视为所有用途下的再分发许可。

安装前先校验整包哈希。导入使用现有上传注册和持久化任务服务，按文件 SHA256 复用已有文件；重复导入不会多建相同文档或重复排入已有导入任务。给已有文件追加测试标签时保留用户标签与已审阅元数据。测试文件作为普通 Library 文件展示，评测通过独立映射把稳定语料 ID 转成当前文档 UUID。

## 5. 27 条案例和自动指标的准确含义

案例定义在 `data/cases-v1.json`。P01–P12 是每份文件一条正例；N01–N12 把某个有明确出处的问题放到不包含所需事实的另一份已选文件中，要求拦截；C01–C03 是双文件比较/组合问题。正例和跨文档题有人工指定的文档、PDF 物理页码和原文锚点，脚本逐页校验这些锚点存在。物理页码从 1 开始，不等于文档印刷页码。

| 指标 | 本轮定义 | 能证明什么/不能证明什么 |
| --- | --- | --- |
| 高证据放行率 | 正例中 gate 放行数 / 完成的正例数 | 只证明路由放行，不证明完整回答 |
| 低证据拦截率 | 反例中 gate 拦截数 / 完成的反例数 | 不把生成模型自己口头拒答当成 gate 拦截 |
| Balanced gate accuracy | 上述两种率的平均值 | 不受正反例数量不完全相等的直接影响；不是内容总分 |
| Evidence Recall@K | top-K 经 gate 保留的 chunk 中，命中的固定原文锚点数 / 标注锚点数 | 必须同时匹配文件、页码跨度和规范化片段；是固定锚点召回，不是穷尽语义证据召回 |
| MRR | 第一个命中锚点的 chunk 排名的倒数，未命中为 0 | 测首个相关结果排名；不能代表多义务完整覆盖 |
| Citation integrity | 回答引用编号中，能匹配允许范围内真实 chunk、页码、原文片段的比例 | 验证引用来源与格式，不验证该引用是否蕴含旁边的每一句话 |
| Latency | 检索、生成、首段文本、总耗时，另汇总中位数/P95 | 总耗时包含冷加载；不是完整浏览器/SSE 网络端到端时间 |
| 人工评分 | 1–5 分及理由，单独持久化 | 需实际检查正确性、完整性和引用支持；未评分不填假分 |

没有引用时 Citation integrity 为 N/A，不是 100%；负例没有 gold recall 时为 N/A；异常单列，不算通过。当前流式生成封装不返回 Token usage，所以该字段为空，没有拿字符数假装账单 Token。

每次运行固定当时的案例全文和配置，保存模型、切块、阈值、检索开关与文档索引指纹。每题运行前后检查设置和索引，期间发生变更则终止并要求新建评测，防止把两套参数的结果混在一次实验中。后台任务采用数据库租约；重启后续跑尚未完成的题。取消会撤销发布权，但已在执行的远端请求可能仍会完成并产生调用成本。

## 6. 首轮真实测量结果

运行 ID：`2507c785-095f-46a0-8746-9cbfd98cd00e`。生成模型：`deepseek/deepseek-v4-flash`。Embedding：512 token budget / 64 overlap / 精确模型 tokenizer。Top-K=6；dense/BM25 候选经 RRF 和 Qwen Reranker 排序。距离阈值 0.45，reranker floor 0.5。27 题全部完成，0 个执行错误。

| 指标 | 结果 |
| --- | --- |
| 高证据放行 | 15 / 15，100% |
| 低证据拦截 | 11 / 12，91.67% |
| gate 混淆计数 | 正确放行 15，错误拦截 0，正确拦截 11，错误放行 1 |
| Balanced gate accuracy | 95.83% |
| 固定锚点平均 Recall@6 | 86.67% |
| 平均 MRR | 0.658 |
| 无效引用编号 | 0 |
| 放行但没有引用的输出 | 0 |
| 总耗时中位数 / P95 | 3.782 秒 / 9.238 秒 |
| 最大总耗时 | 25.480 秒，首题包含模型冷加载 |

这些结果只针对这一小组用例。不能从 12 个反例推导生产环境已有 91.67% 的稳定安全保证，也不能把 15/15 放行写成“15 个答案完全正确”。完整文本、原始分数、证据和逐题时间已保存在 `evaluation-results.json`，评分页可查看与导出。

### 必须保留的失败与测量局限

**N10：主题相关不等于足以回答。** 选中 CSF 2.0，询问 AI RMF 的四个核心函数。检索到了提及 AI RMF 结构的交叉引用，最高 reranker 分数约 0.9924、对应距离约 0.3928。gate 放行，但文本没有列出所问四项。生成模型随后明确说明材料未列出这些函数。这减少了编造，却仍然不满足“低证据在生成之前就 block”的要求，因此按错误放行保留。

**C02：跨文档问题缺少覆盖保证。** 问题同时要求未成年人信息处理同意、数据分类分级依据。top-6 都偏向个人信息保护法，漏掉数据安全法的关键片段；gate 仍因一部分相关证据而放行。输出承认第二项材料不足，但并未完成完整任务。其锚点 recall 为 0.5。说明需要“所有显式子问题均有证据”的契约，仅有相关 chunk 不够。

**P03 和 C01：固定页码锚点可能漏计等价证据。** 英国 AI 白皮书在多处重复五项原则，P03 取到物理第 32 页的等价完整列表，而 gold 指向第 12 页，严格指标计 0。C01 的 CSF 函数列表也存在多处重复。因此 86.67% 不能直接解释为 13.33% 的答案缺证据。下一版应给同一事实登记多个可接受证据位置，保留本轮原始标签与结果，不能为了分数好看事后悄悄改 gold。

## 7. 怎么确定 chunk 大小、overlap 和阈值

### 7.1 先明确约束，再优化平均分

客户要求优先减少 false allow。建议用约束式选择：在正例放行率达到业务可接受下限的条件下，使低证据错误放行尽量少；并同时报告跨文档完整覆盖率。也可以用 `10 × false_allow + 1 × false_block` 等风险损失比较候选，但权重应由业务确认，10 只是示例。不要用一个平均总分掩盖风险。

“反例 0 次失误”也要附带样本量。12 题全过仍不足以宣称极低失误率；例如用 rule-of-three 的粗略估计，零失误时 95% 上界约为 3/n。要证明很低的错误率，需要显著更多、覆盖真实分布的负例。

当前文件中的 calibration/validation 是实验组织标签，尚未用于选参数。问题在跨文件负例中会复用，不能把当前划分声称为严格无泄漏的最终测试集。正式调参前应按事实/问题家族分组，让改写与同一事实的正负配对留在同一集合；另留整类政策/文档做领域外验证。跨文档诊断集单独报告。

### 7.2 切块实验：先只跑检索，再少量真实生成

推荐第一阶段比较 budget `{256, 384, 512, 768}` 与 overlap 比例 `{0, 0.125, 0.25}`，得到 12 组。每一组都必须真正重新切块并生成对应向量索引，不能只改设置后复用原向量。为避免反复破坏日常 Library，可在隔离数据库或独立实验索引中跑，最后只将胜出配置全库发布一次。

固定文档版本、模型 revision、query instruction、contextual header 策略、候选数量、reranker、Top-K、上下文上限。原项目会为 chunk 生成 contextual header；改变切块会改变 header 和 LLM 调用数，实验必须把这项成本和随机性记录下来，不能把它混成纯粹切块收益。

先测检索：gold evidence recall、MRR、每个跨文档要求的覆盖、检索延迟、索引大小、chunk 数量、上下文重复率和最终送入 LLM 的字符/token。淘汰明显差的组合，再对两三组候选运行真实回答和人工/模型 judge，节省 API 费用。对改写题成组统计，必要时按问题组 bootstrap 比较置信区间，不把很小的随机波动当成改进。

Overlap 的作用是避免句子、条款或定义恰好切在边界时丢失关系。增加 overlap 也会重复召回证据、增大索引与上下文成本。原 chunker 按段落/句子尽量携带尾部内容，且把 overlap 限制为 budget 一半；64 是目标上限，不代表每两个 chunk 一定共享精确 64 个 token。应该记录实际共享文本比例。512/64 只是便于比较的起点，不能说“业界规定必须 480/512”。

### 7.3 阈值实验：检查实际 gate，不只看分数

本项目的规则并非简单“距离小于阈值即可”：距离通过仍需 reranker 通过；距离未通过时，词项匹配达到条件可作为补充信号；此外还有最短上下文、显式政策名称检查。reranker 失败时原服务会回退到 dense，门控行为也会改变。因此应记录是否真实获得 reranker 分数、是否回退，并对最终 gate 画混淆矩阵。

固定索引和候选集，先保存所有原始分数。用校准集探索 distance `{0.30, 0.35, 0.40, 0.45, 0.50}` 与 reranker floor `{0.2, 0.4, 0.5, 0.6, 0.8, 0.95}`。如果只重放局部分数规则，应明确称作诊断代理；最终候选必须重新经过完整门控，因为政策名称检查和其他条件不能省略。冻结参数后，再一次性跑保留测试集。

N10 的 reranker 已经给出 0.9924，说明把 floor 从 0.5 稍微抬高并不能解决所有问题。例如可回答的 P10 最高分只有约 0.9797，单靠抬高 floor 排除 N10 也会拦截 P10。模型分数衡量相关性，业务要求的是“是否足以回答每一个事实要求”，两者需要分别建模。

## 8. 后续机制的对比和建议顺序

| 机制 | 适用问题 | 代价与局限 | 建议 |
| --- | --- | --- | --- |
| 原文锚点评测 + 人工 review | 建立可靠基线、定位故障 | 标注成本；单一锚点可能漏掉等价证据 | 本轮已实现，先扩充可接受证据组 |
| 跨文档候选配额/保底 | C02 这类一个文件占满 Top-K | 改动较小，可能引入弱相关片段；有文档不等于有答案 | 下一步优先做诊断实验 |
| 显式子问题拆解与覆盖契约 | 比较、列表、多个地区或多个义务 | 需要定义每个要求的支持状态；可能增加检索/模型调用 | 与候选配额一起，检查“每项要求均有证据” |
| 严格 answerability 判定 | N10 这类交叉引用冒充可回答内容 | 可用一次小模型结构化判断；需防误判，超时/格式失败要定义 fail-closed | 比盲调一个更高阈值更贴合客户需求 |
| 生成后 claim→evidence 校验 | 相关材料下仍有无依据的细节 | 增加延迟与 judge 成本，必须在正式输出前缓冲或允许撤回 | 严格证据场景再加，不把已流出的内容当已 block |
| RAGAS 等模型 judge | 大批量 faithfulness、context recall 评估 | judge 会误判，需要人工校准与固定 judge 版本 | 扩样后加入，保持人工复核样本 |
| GraphRAG/语义切块/复杂记忆 | 更复杂关系、多跳研究或长期个性化 | 改动与维护成本较大，不能自动解决证据不足 | 当前不优先 |

RAGAS 的 faithfulness 关注回答与检索上下文的一致性，不能代替所问任务的完整性和原始来源验证；它与本轮引用 integrity 是不同维度。[RAGAS 指标文档](https://docs.ragas.io/en/v0.4.1/concepts/metrics/available_metrics/)；检索模型还应按不同领域分别测，而非只看单个平均值，[BEIR 论文](https://arxiv.org/abs/2104.08663)提供了异构任务评测的参考。

最小可行的后续顺序是：补齐等价 gold 和困难负例 → 在现有模块中增加显式跨文档覆盖检查 → 引入可失败关闭的 answerability 判定 → 再做切块和阈值对比。后两项是下一轮建议，本次没有把它们假称为已经实现。当前也没有修改 gate 来专门迎合 N10。

## 9. 复现和回归

新数据库需要 migration 029；Compose 的新卷初始化序列已经包含该迁移，现有卷仍需手动应用迁移。模型依赖是可选 extra，原 API/fastembed 模式不要求加载 Qwen。

```powershell
# backend 工作目录；这些是显式修改本机 Library 的验证命令
..\.venv\Scripts\python.exe -m scripts.check_qwen_local
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library prepare
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library configure
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library import
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library rescan
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library wait
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library verify
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library reembed
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library verify-vectors
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library evaluate
..\.venv\Scripts\python.exe -m scripts.verify_qwen_library report
```

`verify` 用首次保存的 before 快照核验原有 chunk 已替换；`reembed` 检查本轮 chunk ID 不变与向量行版本更新。`prepare` 只应用 029，不会用初始化 SQL 覆盖日常数据库。报告不输出 API key、数据库密码或用户聊天历史。

新增测试覆盖模型输入和向量校验、query/passage 指令差异、分数尺度、GPU 进程释放与计时器竞争、空输入、语料哈希/页码锚点、指标分母和 N/A、接口鉴权、运行续跑、索引变化保护、真实数据库租约撤销与人工 review，以及重复导入保留文档/标签/元数据。

完整数据库回归使用 `scripts.test_with_local_postgres` 启动只监听本机的独立临时 PostgreSQL 实例，初始化的是该临时实例，不使用也不清空用户的 Library。普通 pytest 在未显式配置独立测试数据库时保留原项目的安全跳过行为。最终测试数量与结果见本机 `eval-results/qwen-upgrade/pytest-postgres.txt`。

最终结果：独立数据库完整回归 **384 passed，0 skipped**；`ruff check app tests` 通过；前端现有测试 4 项通过，生产构建通过。另构建 wheel 并检查压缩包内容，确认实际包含 12 份 PDF 和案例 JSON。空闲释放在真实运行后也已确认：模型进程消失、runtime 报告 unloaded，权重仍在磁盘缓存。
