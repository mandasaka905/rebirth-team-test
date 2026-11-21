# AgentArts接入说明

## 当前采用的新版 Managed Agents 路径（2026-11-02）

用户已在控制台创建 coordinator、inventory、customer、cash 四个 Managed Agents 并填入项目提示词；尚未核验实际调用。它们不是下文旧版低代码工作流，不能套用工作流HTTP请求。

新版官方快速入门目前使用 WebSocket `chat.send`，开始节点 `inputs.request` 不适用。可复制 `config/agentarts.managed.example.json` 配置真实运行时名称、网关域名和各角色独立的凭证环境变量；仅在本机设置密钥，不写进文件或命令参数。可选依赖为 `requirements-agentarts.txt`。

适配器要求 `wss://` 加密传输。官网示例中的 `ws://` 不直接照搬；需先验证实际网关支持WSS，否则保留阻塞，不通过明文发送密钥。出站MaaS密钥与智能体入站调用密钥不同。

当前完成的是假连接协议测试，未证明实际网关、身份、模型额度或输出契约可用。云端权限请求和补充问题不会被客户端自动同意或代选；运行异常即失败，不回退规则。一次本地请求上限不能限制云端内部模型迭代次数或保证费用。

官方协议依据：https://support.huaweicloud.com/qs-agentarts/agentarts_04_0003.html 及该页面链接的官方 managed_agents_client.py（仅读取参考，未运行其自动授权逻辑）。

下方工作流说明供旧接口兼容参考，当前四个Managed Agents应采用上述路径。

## 2026-11-02 公网接入状态

网站计划使用 Render 提供的 HTTPS 地址，无需购买域名。`render.yaml` 是部署声明，包含单实例、1GB持久磁盘和30个练习账号名额；创建前必须以控制台实际报价确认费用。目前尚未创建托管服务，也没有公网网址。

新版 AgentArts 使用 `Authorization: Bearer <API Key>`；示例配置已更新，旧版 X-Auth-Token 仍兼容。请求明确指定 `X-Invoke-Mode: published`。四个工作流开始节点仍须定义字符串 `request`，不能把单智能体示例的 `query` 直接替换到本项目工作流。

官方说明：API调用不能使用平台赠送的免费Token，需接入可用的MaaS模型或自有外部模型。还需在真实账号中创建、发布四个工作流并验证结束节点输出；本地假HTTP检查不能代替云端联调。

目前公网网关仍关闭云调用。待真实端点、凭证、云端额度和账号调用权限配置后才能开放；不能把密钥放进网页，也不能在开放注册时直接开放无限计费调用。

官方参考：https://support.huaweicloud.com/bestpractice-agentarts/agentarts_06_0021.html
Render配置参考：https://render.com/docs/blueprint-spec

## 接入方式

项目采用“AgentArts专业角色工作流＋本地协作宿主”的开发结构。平台的多智能体控制器提供路由，但交叉质询、方案版本、约束校验及修订循环由本项目代码实现。**本地测试成功不等于平台原生多智能体应用已搭建或云端调用已通过。**

创建四个独立工作流，分别作为coordinator、inventory、customer、cash。每个工作流的输入输出契约一致，但系统提示词和职责不同。此文档是手动配置指南，不是可直接导入AgentArts的DSL；没有伪造导入包。

## 每个工作流的节点

1. 开始节点：添加必填字符串变量`request`。
2. 大模型节点（或合适的Agent节点）：系统提示词使用`prompts/`下对应文件；将开始节点`request`作为输入。该字符串是包含角色规则和context的JSON信封。
3. 结束节点：指定回复直接映射模型输出的JSON文本，不加自然语言总结。必须包含一个`action`对象。
4. 测试工作流能返回工具请求JSON，再发布部署。

工具动作由本地程序解释并执行。工具结果放进下一次请求的`context.observations`，同一角色保持独立会话ID。本地没有公网地址时，云端不能反向访问127.0.0.1，所以首版不配置云端HTTP节点访问本机。后续可将工具服务部署到受认证保护的端点，再注册为平台工具。

## 配置本地连接

复制`config/agentarts.example.json`为根目录`config.local.json`。把四个工作流控制台提供的完整调用路径分别填入，路径不能使用文档中的示例域名。账号区域、运行时路径和工作流类型可能不同，以控制台生成的调用示例为准。

当前适配器发送：

```json
{"inputs":{"request":"包含instruction和context的JSON字符串"}}
```

这是本项目定义的开始节点变量，不是AgentArts内置固定字段。若你的控制台使用不同接口或请求体，必须先调整适配器和开始节点映射，不能直接猜测。

`auth_header`按调用示例选择`X-Auth-Token`或`Authorization`。Token只通过本机`AGENTARTS_TOKEN`环境变量传入；Authorization模式自动加Bearer前缀。不要把密钥写进URL、配置或聊天。尚未实现IAM自动刷新，Token过期会失败。

准备后执行：

```powershell
python -m rebirth run sample_clothing --mode agentarts --config config.local.json
```

该CLI操作会发送经营数据至配置的云服务并可能计费，不属于当前本地验收。每角色每阶段最多8步、最多2轮修订；CLI默认任务96次调用。网页默认64次、可设1—96次；输入2MB、输出300KB、总时长180秒、HTTP单次20秒，无自动重试。达到上限即失败留痕，不回退规则。字节不是Token、次数不是人民币额度，取消不能撤销在途费用，仍须云侧设额度。

## 下一次需要用户提供的内容

- AgentArts是否已开通并能创建工作流。
- 工作流调用方式的非敏感示例，尤其请求体字段和返回结构。
- 四个工作流发布后的调用路径，可在本机配置。

无需向聊天提供Token、AK/SK或密码。项目尚未在真实账号下联调，响应解析仅做了本地协议样例测试。

## 已核对的官方文档（2026-10-24）

- 创建多智能体应用：https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0106.html
- 多智能体执行范式：https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_0105.html
- 调用工作流/智能体：https://support.huaweicloud.com/api-agentarts/InvokeRuntime.html
- 结束节点：https://support.huaweicloud.com/lowcode-agentarts/end_node.html

上述文档可能随版本变化；接入时核对你的区域及控制台生成的调用示例。平台路由能力本身不能替代本项目的协商与计算校验机制。

## 0.4接入预检与数据确认

配置需增加allowed_hosts，填写四个端点的真实主机名。适配器要求HTTPS，拒绝URL账号密码、查询参数、片段与重定向；凭证不进入网页或审计。

“经营概览→模型接入预检”只读本地配置，检查端点、域名、认证头、凭证存在性和服务开关，不发网络请求，不证明Token、工作流或额度有效。当前启动脚本关闭云调用。

未来显式启动 python -m rebirth serve --config config.local.json --allow-cloud，网页仍需每次确认经营数据与费用。出站店名和商户标识匿名化、来源说明留本机，并匹配常见电话；经营数字、观察、检索文段、原因卡和工具结果仍可能敏感，无法保证自由文本完全脱敏，须人工核查。CLI直接云运行是开发者明确发起的真实调用，不适用网页同意界面。

新增只读工具business_diagnostics、knowledge_search(query)、investigation_history。工具由宿主白名单执行，文字资料不能注册新工具。传输、独立会话、认证头和最小化已用假HTTP验证；四个真实工作流尚未创建或发布，没有平台DSL导入包，原生应用编排与部署需后续核验。


## 0.7接入前已准备的新增契约

宿主会在调用信封的output_contract附带新模式草案、模式审查及补货字段说明，云模型无需访问本地文件路径。四角色提示词已补充model_drafts、model_reviews、supply_analyze和model_draft_evaluate的要求。真实接口尚未联调，不能把这些准备描述为已发布的平台应用。
