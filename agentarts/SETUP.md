# AgentArts 接入说明

项目使用库存、客户、现金和经营统筹四类 Managed Agents。角色提示词位于 prompts/，应用负责阶段编排、工具执行、版本校验及证据记录。

## 配置与调用

安装 requirements-agentarts.txt，参照 config/agentarts.managed.example.json 配置自己的网关和运行时地址，并通过对应环境变量提供调用密钥。Managed Agents 适配器使用加密 WSS 和 chat.send 协议；出站模型凭据与入站智能体凭据不能混用。

先运行 agentarts_check.py 检查单角色连接，再从应用发起已确认的云端任务。调用可能产生费用；出错时明确失败，不用规则结果冒充云端分析。

## MCP 工具

方案约束核验已封装为独立 MCP Server，以 ARM64 容器部署于 AgentArts 运行时。应用侧将智能体 proposal_evaluate 动作转换为 MCP 调用并回传证据；这是应用侧桥接，不是 Managed Agents 控制台原生绑定，也未发布原生 Skill。

设置 REBIRTH_MCP_CREDENTIAL_FILE 为本机入站配置文件的绝对路径可启用桥接；未设置时使用原有本地计算。配置文件包含 api_key 字段，不得提交到仓库。MCP 服务配置、部署和验收步骤见同目录 MCP接入与验收.md。

真实云端工具验收及智能体引用闭环记录见 testing/mcp-cloud-acceptance.json 和 testing/mcp-agent-live-acceptance.json。数据为合成案例，不能据此宣称真实经营收益或多智能体普遍优于单智能体。

## 网站部署

start_public.py 提供本机预览，默认关闭云调用；页面支持移动尺寸，但这不等于已发布长期公网网站。render.yaml、Dockerfile 和 deploy/ 提供部署参考，需使用自己的持久存储、域名或平台入口，并核对费用。

## 官方参考

https://support.huaweicloud.com/qs-agentarts/agentarts_04_0003.html
https://support.huaweicloud.com/highcode-agentarts/agentarts_10_069.html
https://support.huaweicloud.com/highcode-agentarts/agentarts_10_067.html
