import json
import os
from typing import Any

import akshare as ak
import anyio
from dotenv import load_dotenv
import requests

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    create_sdk_mcp_server,
    tool,
    AgentDefinition
)


load_dotenv()

os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
os.environ.setdefault("ANTHROPIC_MODEL", "deepseek-v4-flash")
os.environ.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "deepseek-v4-flash")
os.environ.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-flash")
os.environ.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "deepseek-v4-flash")
if api_key := os.getenv("ANTHROPIC_API_KEY"):
    os.environ.setdefault("ANTHROPIC_API_KEY", api_key)


async def main():
    @tool(
        "bochasearch",
        "使用 Bocha AI 进行网络搜索",
        {"query": str},
    )
    async def bochasearch(args: dict[str, Any]) -> dict[str, Any]:
        try:
            # 从环境变量中获取 API 密钥
            bochakey = os.getenv("BOCHA_API_KEY")
            # Bocha AI 网络搜索 API 端点
            ep = "https://api.bochaai.com/v1/web-search"

            # 设置请求头
            headers = {
                "Authorization": f"Bearer {bochakey}",
                "Content-Type": "application/json",
            }

            # 构建请求数据
            data = {
                "query": args.get("query", ""),  # 搜索关键词
                "summary": True,  # 返回摘要
                "count": 10,  # 返回结果数量
            }

            # 发送 POST 请求到 API
            response = requests.post(ep, json=data, headers=headers, timeout=30)
            res_data = response.json()

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"result: {res_data}",
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {"type": "text", "text": f"Bocha 搜索失败: {e}"}
                ],
                "is_error": True,
            }

    @tool(
        "getbalance",
        "获取沪深A股公司的资产负债表，并保存到文件中，其中参数stock_code是带市场标识的股票代码，比如SH600600，参数year是年份",
        {"stock_code": str, "year": str},
    )
    async def get_balance_sheet_A(args: dict[str, Any]) -> dict[str, Any]:
        try:
            stock_code = args.get("stock_code", "SH600600")
            year = args.get("year", "2025")
            df_balance_sheet = ak.stock_balance_sheet_by_yearly_em(symbol=stock_code)

            # 只取REPORT_DATE是{year}-12-31的数据
            df_balance_sheet = df_balance_sheet[
                df_balance_sheet["REPORT_DATE"] == f"{year}-12-31 00:00:00"
            ]

            # 获取项目根目录
            project_root = os.getcwd()
            # 创建完整的文件路径
            filepath = os.path.join(
                project_root,
                "data",
                "financial_statements",
                f"{stock_code}_{year}_资产负债表.csv",
            )

            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # 使用指定目录保存文件
            df_balance_sheet.to_csv(filepath, index=False, encoding="utf-8-sig")

            return {
                "content": [
                    {"type": "text", "text": f"资产负债表已保存到: {filepath}"}
                ]
            }

        except Exception as e:
            return {
                "content": [
                    {"type": "text", "text": f"获取资产负债表失败: {e}"}
                ],
                "is_error": True,
            }

    # Create SDK MCP servers
    websearch_server = create_sdk_mcp_server(
        name="websearch",
        version="1.0.0",
        tools=[bochasearch],
    )

    tools_server = create_sdk_mcp_server(
        name="tools",
        version="1.0.0",
        tools=[get_balance_sheet_A],
    )

    

    # Use it with Claude. allowed_tools pre-approves the tool so it runs
    # without a permission prompt; it does not control tool availability.
    # options = ClaudeAgentOptions(
    #     mcp_servers={
    #         "websearch": websearch_server,
    #         "tools": tools_server,
    #     },
    #     allowed_tools=[
    #         "mcp__websearch__bochasearch",
    #         "mcp__tools__getbalance",
    #     ],
    # )

    # async with ClaudeSDKClient(options=options) as client:
    #     await client.query("获取 SH600600 的2025年度资产负债表")

    #     # Extract and print response
    #     async for msg in client.receive_response():
    #         print(msg)
    def financial_analyzer_agent() -> AgentDefinition:
        return AgentDefinition(
            description="财报分析助手",
            prompt="你是一个财报分析助手",
            tools=["Read", "Grep", "Glob", "Bash", "Write", "Edit"],
            skills=["financial-report-analyzer"],
            model="kimi-k2.6",
        )
    agents_config= {
        "financial-analyzer": financial_analyzer_agent(),
    }

    options=ClaudeAgentOptions(
        include_partial_messages=True,
        mcp_servers={"websearch": websearch_server},
        allowed_tools=["Read", "Grep", "Glob", "Agent", "AskUserQuestion", "mcp__websearch__bochasearch"],
        agents=agents_config
    )
    prompt2="""基于当前可用的工具，分析中国平安（601318.SH）2023年和2024年的资产负债表，并进行比较分析。1. 使用“获取资产负债表”工具获取平安2023和2024年的资产负债表数据。2. 使用提供的工具对数据进行分析和比较。3. 总结中国平安财务状况的变化趋势，包括资产、负债和所有者权益等主要项目的变化情况。"""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt2)

        # Extract and print response
        async for msg in client.receive_response():
            print(msg)


if __name__ == "__main__":
    anyio.run(main)