"""
mcp_tools.py — Model Context Protocol (MCP) server definitions exposing standard tools to Claude Agents.
"""

import os
import subprocess
from typing import Any, Dict
from claude_agent_sdk import tool, create_sdk_mcp_server

try:
    from .sandbox import SandboxProvider
    from .guardrails import BadDepsStore, DependencyType
except (ImportError, ValueError):
    from sandbox import SandboxProvider
    from guardrails import BadDepsStore, DependencyType


def create_sandbox_mcp_server(sandbox: SandboxProvider, server_name: str = "sandbox"):
    """Creates an SDK MCP server exposing sandbox command execution capabilities."""

    @tool(
        "sandbox_exec",
        "在隔离的虚拟机/沙箱环境中执行 Shell 命令，用于构建、启动服务、运行测试或查看日志",
        {
            "cmd": str,
            "work_dir": str,
            "timeout_seconds": int
        }
    )
    async def sandbox_exec(args: Dict[str, Any]) -> Dict[str, Any]:
        cmd = args.get("cmd", "")
        work_dir = args.get("work_dir")
        timeout = args.get("timeout_seconds", 60)

        result = sandbox.exec_command(cmd=cmd, work_dir=work_dir, timeout_seconds=timeout)

        return {
            "content": [
                {
                    "type": "text",
                    "text": result.full_output()
                }
            ],
            "is_error": not result.is_success
        }

    @tool(
        "sandbox_reset_env",
        "重置沙箱环境至干净状态",
        {}
    )
    async def sandbox_reset_env(args: Dict[str, Any]) -> Dict[str, Any]:
        success = sandbox.reset_environment()
        return {
            "content": [{"type": "text", "text": "Environment reset successful" if success else "Reset failed"}],
            "is_error": not success
        }

    return create_sdk_mcp_server(
        name=server_name,
        version="1.0.0",
        tools=[sandbox_exec, sandbox_reset_env]
    )


def create_guardrail_mcp_server(store: BadDepsStore, server_name: str = "guardrails"):
    """Creates an SDK MCP server exposing static bad-dependency scanning and memory bank recording."""

    @tool(
        "scan_bad_dependencies",
        "快速扫描目标项目代码库，检测是否存在已知无法解析或已下架的坏依赖",
        {"project_root": str}
    )
    async def scan_bad_dependencies(args: Dict[str, Any]) -> Dict[str, Any]:
        proj_root = args.get("project_root", "")
        hit = store.check_project_for_bad_deps(proj_root)
        if hit:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"FOUND_BAD_DEPENDENCY: {hit.id} (Reason: {hit.reason})"
                    }
                ]
            }
        return {
            "content": [{"type": "text", "text": "NO_BAD_DEPENDENCY_FOUND"}]
        }

    @tool(
        "record_bad_dependency",
        "将新发现的坏依赖记录到持久化规则库中（自动进行官方仓库核验）",
        {
            "dep_type": str,   # maven, npm, pip
            "dep_name": str,   # e.g. org.apache.poi:poi-ooxml-schemas or package-name
            "reason": str
        }
    )
    async def record_bad_dependency(args: Dict[str, Any]) -> Dict[str, Any]:
        dep_type_str = args.get("dep_type", "").lower()
        dep_name = args.get("dep_name", "").strip()
        reason = args.get("reason", "").strip()

        try:
            dep_type = DependencyType(dep_type_str)
        except ValueError:
            return {
                "content": [{"type": "text", "text": f"Invalid dep_type: {dep_type_str}. Must be maven, npm, or pip."}],
                "is_error": True
            }

        success, msg = store.add_bad_dep(dep_type, dep_name, reason, verify_online=True)
        return {
            "content": [{"type": "text", "text": msg}],
            "is_error": not success
        }

    return create_sdk_mcp_server(
        name=server_name,
        version="1.0.0",
        tools=[scan_bad_dependencies, record_bad_dependency]
    )


def create_patch_mcp_server(server_name: str = "patch_tools"):
    """Creates an SDK MCP server exposing safe code patch application and rollback."""

    @tool(
        "apply_patch",
        "将 Git Diff 或补丁代码应用到目标项目目录中",
        {
            "target_dir": str,
            "patch_content": str
        }
    )
    async def apply_patch(args: Dict[str, Any]) -> Dict[str, Any]:
        target_dir = args.get("target_dir", "")
        patch_content = args.get("patch_content", "")
        patch_file = os.path.join(target_dir, ".temp_agent_patch.diff")

        try:
            with open(patch_file, "w", encoding="utf-8") as f:
                f.write(patch_content)
            
            proc = subprocess.run(
                ["git", "apply", "--ignore-whitespace", ".temp_agent_patch.diff"],
                cwd=target_dir,
                capture_output=True,
                text=True
            )
            if os.path.exists(patch_file):
                os.remove(patch_file)

            if proc.returncode == 0:
                return {"content": [{"type": "text", "text": "Patch successfully applied."}]}
            else:
                return {
                    "content": [{"type": "text", "text": f"git apply failed: {proc.stderr}"}],
                    "is_error": True
                }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Error applying patch: {str(e)}"}],
                "is_error": True
            }

    return create_sdk_mcp_server(
        name=server_name,
        version="1.0.0",
        tools=[apply_patch]
    )
