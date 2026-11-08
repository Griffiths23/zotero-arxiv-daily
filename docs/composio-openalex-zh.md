# GitHub Actions + Composio + OpenAlex

此改动在 GitHub Actions 中运行，不依赖本机常驻进程。

## 配置

1. 在 Composio 控制台选择一个项目，创建项目 API Key，并在**同一项目**连接个人 OpenAlex 账号。ChatGPT 插件中的连接不保证能被自己的项目 API Key 访问，必要时在项目中重新连接。
2. 在 GitHub Settings → Secrets and variables → Actions → Secrets 添加：
   - `COMPOSIO_API_KEY`：Composio 项目 API Key（不是 OpenAlex API Key）。
   - `COMPOSIO_OPENALEX_ACCOUNT_ID`：该项目内 ACTIVE 的 OpenAlex connected account ID。
   - `COMPOSIO_OPENALEX_TOOL_VERSION`：可选，指定已验证的工具版本；默认 latest。
3. 保留 `ZOTERO_ID`、`ZOTERO_KEY`、`SENDER`、`RECEIVER`、`SENDER_PASSWORD`。QQ 密码须使用 SMTP 授权码。
4. 在 Variables 新建 `CUSTOM_CONFIG`，粘贴 `config/composio-example.yaml` 全文。
5. 在 Actions 启用工作流，手动运行 Test。测试会实际调用 Composio，并向 RECEIVER 发送邮件（如有带摘要的匹配论文）。OpenAlex 使用配置的日期窗口，不使用旧版 arXiv 的五篇测试模式。
6. 成功后，由 Send emails daily 每日 22:00 UTC（北京时间次日 06:00）执行。

## 行为和限制

- 按发表日期检索最近七天，缓解索引延迟；OpenAlex 并不保证实时收录所有预印本。
- 按 DOI 或 OpenAlex ID 去除同一次运行的多查询重复结果。七天窗口可能导致不同日期邮件重复出现论文；未实现跨日发送历史。
- 每个查询最多两页、每页五十篇；超过上限会记录警告，不声称穷尽检索。可缩小主题或调整上限。
- 没有摘要的记录跳过；现有 Zotero 文献库决定相似度排序，关键词仅控制候选集合。
- 默认关闭 LLM，邮件展示原始摘要，不会自动生成中文译文。没有单独 GPT API Key 也可使用此配置。启用中文摘要需配置 llm.enabled、api 和 generation_kwargs。
- 仅检索元数据，不自动下载论文 PDF 或执行 PDF 内的指令。
- Composio 和 OpenAlex 各有额度与费用限制，以你的账户为准。
- 密钥仅放 Secrets，不放 CUSTOM_CONFIG。不要将 API Key 上传仓库。

接口依据：https://docs.composio.dev/reference/v3/api-reference/tools/postToolsExecuteByToolSlug
