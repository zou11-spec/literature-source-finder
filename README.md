# Literature Source Finder

一个面向 Codex 的新闻传播学文献来源发现 skill。它可以根据一段研究结论、质性研究发现、论文讨论段落或尚未添加引用的学术文本，寻找可能相关的英文开放学术文献，并输出谨慎的 evidence map。

这个工具的定位是 **candidate source discovery**，不是自动证明工具。它会帮助你发现可能相关的文献，但正式引用前仍然需要阅读原文。

## 适合什么场景

- 给新闻传播学、媒体研究、平台研究相关结论寻找英文文献。
- 将一段中文或英文论文段落拆成可检索的 claim。
- 区分候选文献是理论支持、经验相似、方法相关、背景相关，还是弱相关。
- 为论文写作、文献综述、质性研究 findings/discussion 阶段生成初步阅读清单。

示例输入：

```text
短视频平台通过日常生活化、情感化叙事强化了用户对城市身份的认同。
```

## 安装到 Codex

把这个仓库克隆到本地 Codex skills 目录：

```powershell
git clone https://github.com/zou11-spec/literature-source-finder.git C:\Users\zouzou\.codex\skills\literature-source-finder
```

如果你已经安装过旧版本，可以先删除旧目录，或进入目录后拉取更新：

```powershell
cd C:\Users\zouzou\.codex\skills\literature-source-finder
git pull
```

安装后新开一个 Codex 对话。可以显式调用：

```text
Use $literature-source-finder 帮我给这段新闻传播学结论找英文文献：
短视频平台通过日常生活化、情感化叙事强化了用户对城市身份的认同。
```

也可以自然语言描述需求：

```text
帮我给这段质性研究结论找英文文献，重点是新闻传播学、平台研究和城市传播。
```

## 命令行测试

进入项目目录：

```powershell
cd C:\Users\zouzou\Documents\review\literature-source-finder
```

离线测试 claim 拆解和 query 生成，不调用外部 API：

```powershell
python .\scripts\find_sources.py --text "Short-video platforms reshape city identity through everyday affective storytelling." --limit 5 --no-network --format markdown,json
```

使用 Semantic Scholar 做真实检索：

```powershell
python .\scripts\find_sources.py --claim "Algorithmic visibility shapes news consumption on social media platforms." --limit 5 --source semantic-scholar --format markdown
```

使用多个 claim：

```powershell
python .\scripts\find_sources.py --claim "Short-video platforms reshape city branding through everyday narratives." --claim "Affective storytelling strengthens place identity." --limit 10 --source semantic-scholar --format markdown,json
```

## 可选 API 配置

脚本默认可以无 key 运行，但开放 API 可能限流。建议按需配置：

```powershell
$env:S2_API_KEY="your-semantic-scholar-api-key"
$env:OPENALEX_API_KEY="your-openalex-api-key"
$env:OPENALEX_POLITE_EMAIL="you@example.com"
```

支持的数据源：

- OpenAlex：广泛开放学术元数据检索。
- Semantic Scholar：论文元数据、摘要、链接和引用信息。
- Crossref：可选 DOI 元数据校验。

## 输出内容

默认输出 Markdown evidence map，包括：

- 拆解出的 claims
- 检索策略和 query
- 候选文献列表
- 文献关系类型
- 简短相关性解释
- 引用前需要人工核查的事项
- APA 格式参考文献草稿

也可以输出 JSON，方便以后接入网页、插件或 SaaS：

```powershell
python .\scripts\find_sources.py --text "Affective publics shape crisis communication on social media." --format json
```

## 文献关系类型

关系类型定义见：

```text
references/evidence_relation_types.md
```

核心类型包括：

- `direct_support`
- `theoretical_support`
- `empirical_parallel`
- `methodological_relevance`
- `contextual_relevance`
- `counterpoint`
- `weak_match`

第一版会保守分类。除非摘要或元数据非常明确，否则不会轻易标成直接支持。

## 学术安全边界

- 返回的是候选文献，不是已经被证明可引用的文献。
- 不把理论相关误写成实证支持。
- 不虚构作者、题名、期刊、DOI 或摘要。
- 对弱匹配和 API 失败明确给出 warning。
- 正式写入论文前，请阅读原文确认其是否真的支撑你的 claim。

## 开发验证

检查 Python 脚本语法：

```powershell
python -m py_compile .\scripts\find_sources.py
```

校验 Codex skill 结构：

```powershell
python C:\Users\zouzou\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\zouzou\Documents\review\literature-source-finder
```

成功时会看到：

```text
Skill is valid!
```

## 当前限制

- 第一版只面向英文开放学术文献。
- 不解析 PDF，不提供页码级原文证据。
- 中文 CNKI、万方、维普等数据库未接入。
- API 可能限流；OpenAlex 遇到 429 时建议配置 `OPENALEX_API_KEY` 或稍后重试。
- 关系分类是保守启发式判断，最终引用判断需要研究者人工确认。
