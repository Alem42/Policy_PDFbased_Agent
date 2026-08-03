# ReAct 演示资料与问题清单

更新日期：2026-08-03

这份清单用于演示 Chat/ReAct 的主要路径。四份新增资料均已通过管理员上传 API
进入本地数据库并完成 OCR、分块、metadata 和 embedding，而不是手工插表。

## 已导入的演示文件

| 文件 | 数据库 ID | 地区 / 年份 | 页数 | 适合演示的能力 |
|---|---|---:|---:|---|
| Policy for the Responsible Use of AI in Government v2.0 | `fb59b1a7-0c70-4aeb-ad54-a60581dcd722` | Australia / 2025 | 22 | 普通 RAG、强制要求、生效日期、精确引用 |
| Model AI Governance Framework for Agentic AI v1.5 | `88f53fd0-512a-4721-b588-aa5fa6d83dda` | Singapore / 2026 | 53 | Agentic AI、人类问责、较长 PDF |
| 人工智能安全治理框架 1.0 | `f9475515-bb28-45bc-9281-2d3faa8f942e` | China / 2024 | 20 | 中文文件、跨语言问答、跨地区比较 |
| Withdrawal of Draft South Africa National AI Policy (OCR Demo) | `89d9b0d1-9a60-452a-a6ae-feab3077b436` | South Africa / 2026 | 1 | 无文本层扫描件、OCR、政策状态边界 |

本地下载副本位于 `backend/data/demo_sources/`（该目录被 Git 忽略）。南非 OCR
版本由官方一页 PDF 栅格化得到，原生文本字符数为 0，因此会确定性触发 OCR；
数据库中的 OCR 结果成功提取出 `withdrawn in its entirety`、Notice 3880 和日期。

官方来源：

- Australia: <https://www.digital.gov.au/sites/default/files/documents/2025-12/Policy%20for%20the%20responsible%20use%20of%20AI%20in%20Government%202.0_0.pdf>
- Singapore: <https://www.imda.gov.sg/-/media/imda/files/about/emerging-tech-and-research/artificial-intelligence/mgf-for-agentic-ai.pdf>
- China: <https://www.cac.gov.cn/rootimages/uploadimg/1727568303900999/1727568303900999.pdf>
- South Africa: <https://www.gov.za/sites/default/files/gcis_document/202606/54840gen3978.pdf>

## 推荐演示顺序

### 1. 普通选中文件回答

选择 Australia 2025 文件，使用 Document Analysis：

> Under Australia's Policy for the Responsible Use of AI in Government v2.0,
> which entities must apply it, when did it take effect, and what are three
> mandatory governance requirements?

预期：一次 selected-document search 后回答；应提到 NCEs、2025-12-15，以及
accountable officials、use case owners/register 或 impact assessment；只引用该文件。

### 2. OCR 文件

只选择 South Africa OCR Demo，使用 Document Analysis：

> According to this notice, was South Africa's draft National AI Policy adopted
> or withdrawn, and which earlier government notice and publication date does it
> reference?

预期：回答 `withdrawn`，引用 Government Notice 3880 和 2026-04-10。这个答案完全
来自 OCR 后的一条 chunk。

### 3. 跨语言、跨地区、跨文件比较

同时选择 Australia、Singapore、China 三份文件，使用 Document Analysis：

> 请用中文比较三份文件各自把最终问责责任放在谁身上：澳大利亚政府政策的
> accountable officials/use case owners、新加坡框架的 human accountability、
> 中国框架的责任主体。指出它们分别是强制政策、治理框架还是技术指引，并分别
> 引用三份文件。

预期：最终引用集合必须同时出现三个标题。系统会识别中文地区别名，但“请用中文”
只控制回答语言，不会错误地把来源限制为中文文件。实测第一次聚焦查询证据不足，
第二次补齐三个地区后回答；最终没有 tool protocol error。

### 4. Metadata Filter 是软约束

只选择 Singapore 2026 文件：

> Filter files published before 2025. What four areas does Singapore's 2026
> Agentic AI framework use to organise risk management?

预期：年份限制与问题目标冲突，因此回退到原 selected scope；回答前显示明确警告，
随后仍正常列出四个维度，不报错。

### 5. 当前选中文件不匹配，自动遍历 Library

只选择 South Africa OCR Demo，切换到 Open Discussion：

> What mandatory requirements does Australia's 2025 responsible AI government
> policy set for accountable officials and AI use case impact assessments?

预期工具路径：

`search_internal_documents (insufficient) -> search_full_corpus (sufficient) -> answer`

最终只引用 Australia 2025 文件，evidence tier 为 `full_corpus`。实测总 token 约
14.3k。南非文件不能仅因“同属 AI 政策”而通过 Evidence Gate。

### 6. Low evidence / 不可回答问题

只选择 South Africa OCR Demo，使用 Document Analysis：

> What exact civil penalty amount does Australia's 2031 Quantum AI Act impose
> for lunar data-centre violations?

预期：一次 selected search、0 citation、`evidence_sufficient=false`，然后输出标准
Insufficient Evidence 文本；实测约 1,548 token，不编造金额。

### 7. 文件与实时网页对照

选择现有的 `Voluntary AI Safety Standard`（2024），使用 Open Discussion：

> Compare the selected 2024 Voluntary AI Safety Standard with the latest
> information on the web. Has Australia replaced or updated it, and what is
> current as of 2026?

预期工具路径：

`search_internal_documents -> search_web -> answer`

最终 evidence tiers 同时包含 `internal` 和 `web`。实测能够说明 2025 Guidance
for AI Adoption 已演进/取代 VAISS，并将选中文件内容与实时网页结果分开引用。

### 8. 原始故障回归

选择 `Voluntary AI Safety Standard` 与 `Winning the Race: America's AI Action Plan`：

> I wanna know the newest AI Safety Standard in Australia, especially after
> year 2026. filter the files which published before 2026

预期：`before 2026` 被解释为 `year <= 2025`；如果 provider 未返回工具调用，系统
会先重试，再使用确定性安全动作，不再输出 `The agent did not choose a required
tool action`。时效问题会完成一次网页核查，然后生成回答。

## 演示时应强调的边界

- Metadata Filter 是检索偏好，不是回答开关；零匹配或过滤后证据弱时会放宽并警告。
- 地区属于实体正确性边界：明确问 Australia 时，South Africa metadata 或正文中
  完全未出现 Australia 的文件不能让 Evidence Gate 通过。
- 明确比较多个地区时，每个地区都必须有证据；Top-K 不能只返回最容易匹配的一国。
- 不充分的探索性结果不会进入最终 citation 集合。
- Document Analysis 不访问 Library/Web；Open Discussion 才会按 selected → library
  → web 的层级升级。
- `latest/newest/current` 属于时效对照意图；成功的 web evidence 后由代码保证停止，
  避免模型重复搜索。
