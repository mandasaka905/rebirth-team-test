# 经营方案约束核验 MCP

## 当前状态

已实现官方 Python MCP SDK 的 Streamable HTTP 服务，入口为 `/mcp`。
本地已通过 SDK 握手、工具发现、真实超预算计算、错误参数和未授权请求验收。
已部署于 AgentArts ARM64 运行时，并通过应用侧 MCP 桥接完成真实智能体请求、云端工具计算及结论引用验收。此实现不是 Managed Agents 控制台原生绑定，未发布原生 Skill。

## 工具与数据

工具名：`evaluate_proposal_constraints`。
输入：`ledger`（完整经营底账）、`proposal`（单份候选方案）。底账字段参照 `examples/merchant.synthetic.json`，方案参照 `config/contracts.json` 的 `proposal_example`。
输出：`evaluation`（预算、库存、工时、三种销量情景的逐日现金、未知项）、`input_sha256`（输入核对摘要）、`tool_version`、`execution_authorized=false`。

复用 `rebirth.tools.evaluate`，没有独立复制财务计算公式。未知成本保持未知，工具通过不代表经营方案获准执行。输入摘要不证明数据真实性。
接口不接受文件路径，不读取账号数据库，不提供采购、付款或发布操作。

## 本机运行

在项目根目录执行：

```powershell
python -m pip install -r requirements-mcp.txt
python -m rebirth.mcp_server
```

默认仅监听 `127.0.0.1:8000`。该地址不能由华为云访问。

```powershell
python -m unittest discover -s tests -p test_mcp_adapter.py -v
python tests/mcp_http_acceptance.py
```

## 托管准备

提供 `Dockerfile.mcp`，默认端口8000。对外监听必须设置环境变量 `REBIRTH_MCP_TOKEN`，由部署环境私密注入，不写入镜像、源码或截图。
请求头为 `Authorization: Bearer <工具专用令牌>`，不是模型调用密钥。服务端不需要模型密钥。
部署时使用受保护的 HTTPS 地址；在 AgentArts 自定义 MCP 配置中填写实际服务地址 `/mcp` 与鉴权头，再发现工具。
ARM64 容器及真实云端调用已验收；使用者需自行配置运行时、网络及凭据，费用以自己的云端账单为准。

## 智能体绑定提示词

将以下要求加入独立联调智能体，验收后再合并到现金角色与统筹角色：

> 收到完整底账与候选方案时，先调用 evaluate_proposal_constraints。使用本次调用返回的预算、现金情景和未知项作答，保留 input_sha256 供核对。constraint_pass=false 时逐条说明失败条件；unknowns 非空时说明待核实事项，不得将未知费用视为零。禁止自行覆盖工具计算、推断已获执行授权或声称实际盈利。工具调用失败时明确告知未完成核验，不编造返回值。

## 云端验收顺序

1. MCP 工具列表显示真实工具名及两个输入字段。
2. 输入合成底账与有效方案，保存 AgentArts 工具调用记录及返回结果。
3. 将方案首个商品 variable_cash_cost 改为400.00，确认本次工具返回 BUDGET_EXCEEDED，智能体结论保留阻断原因。
4. 将方案使用商品的 unit_cost 设为null，确认完整毛利为null，智能体要求补证。
5. 传入空底账，确认报错且不生成经营结论。
6. 比较智能体引用的输入摘要与本次工具结果；截取调用过程、返回值和最终结论，遮去令牌。

只有完成上述云端步骤后，才能写“已通过 MCP 接入 AgentArts 并由智能体实际调用”。

## 官方依据

- https://support.huaweicloud.com/highcode-agentarts/agentarts_10_126.html
- https://support.huaweicloud.com/lowcode-agentarts/agentarts_05_01301.html

当前 Skill 官方说明为暂不支持在智能体中调用，因此本次采用 MCP 路线；不把上传 Skill 包计作实际工具接入。
