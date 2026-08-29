import os
from typing import Dict, Optional
from pathlib import Path
from claude_agent_sdk import AgentDefinition

SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill_sop(skill_name: str) -> str:
    """Reads the full Markdown SOP from the skill directory if available."""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if skill_file.exists():
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return ""


def get_runtime_evaluator_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in building, running, and diagnosing code execution within the sandbox."""
    sop = load_skill_sop("eval-run-utm")
    base_prompt = (
        "你是一个资深的编译与运行验证专家。你的核心任务是在隔离沙箱中构建并运行待测项目。\n"
        "操作原则：\n"
        "1. 首先阅读项目目录结构，识别项目技术栈（Java Maven/Gradle, Node.js, Python, Go 等）。\n"
        "2. 使用 mcp__sandbox__sandbox_exec 工具在沙箱中按顺序执行构建和启动验证。\n"
        "3. 如遇端口占用、依赖缺失或编译报错，根据专业经验进行排查诊断。\n"
        "4. 最终输出结构化的运行验证结论，包括 status ('success'/'fail')、错误日志摘要和关键堆栈。"
    )
    prompt = f"{base_prompt}\n\n## 详细操作 SOP:\n{sop}" if sop else base_prompt

    return AgentDefinition(
        description="沙箱环境构建与运行验证专家",
        prompt=prompt,
        skills=["eval-run-utm"],
        tools=[
            "Read", "Grep", "Glob", "Write",
            "mcp__sandbox__sandbox_exec",
            "mcp__guardrails__scan_bad_dependencies"
        ],
        model=model
    )


def get_accuracy_evaluator_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in semantic & functional accuracy scoring (Double-Blind: no GT leakage)."""
    sop = load_skill_sop("eval-accuracy")
    base_prompt = (
        "你是一个公正的代码功能与逻辑准确性裁判。\n"
        "评测原则：\n"
        "1. 严格基于待测代码和原始任务需求进行独立审查与打分（0-100分）。\n"
        "2. 考察代码是否完整实现了功能要求、是否存在边界条件遗漏或逻辑漏洞。\n"
        "3. 保持双盲独立性，客观输出各项得分、理由、优点（Strengths）和缺点（Weaknesses）。"
    )
    prompt = f"{base_prompt}\n\n## 评分标准与 SOP:\n{sop}" if sop else base_prompt

    return AgentDefinition(
        description="代码功能与逻辑准确性独立裁判专家",
        prompt=prompt,
        skills=["eval-accuracy"],
        tools=["Read", "Grep", "Glob"],
        model=model
    )


def get_quality_evaluator_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in 11-dimension code quality, architecture, UX, and repair suggestions."""
    sop = load_skill_sop("eval-quality")
    base_prompt = (
        "你是一个资深代码架构师与质量评审专家。\n"
        "评测原则：\n"
        "1. 从规范性、架构可维护性、异常健壮性、性能、安全性及交互体验等11个维度进行全面打分。\n"
        "2. 进行失分点的深度归因分析（Root Cause Analysis）。\n"
        "3. 提供具体、可落地的代码重构与修复建议（Repair Suggestions）。"
    )
    prompt = f"{base_prompt}\n\n## 11 维打分细则与 SOP:\n{sop}" if sop else base_prompt

    return AgentDefinition(
        description="代码质量、工程架构与体验评测专家",
        prompt=prompt,
        skills=["eval-quality"],
        tools=["Read", "Grep", "Glob"],
        model=model
    )


def get_csv_diff_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in comparing generated outputs against Ground Truth data."""
    sop = load_skill_sop("eval-csv-diff")
    base_prompt = (
        "你负责将模型生成的产物与基准标准答案（Ground Truth）进行细粒度对比。\n"
        "分析匹配度比率（matched_ratio）、漏报项（missing）和多余项（unexpected）。"
    )
    prompt = f"{base_prompt}\n\n## 对比 SOP:\n{sop}" if sop else base_prompt

    return AgentDefinition(
        description="生成产物与标准基准差异对比专家",
        prompt=prompt,
        skills=["eval-csv-diff"],
        tools=["Read", "Grep", "Glob"],
        model=model
    )


def get_auto_learner_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in analyzing build failure logs and extracting missing package dependencies."""
    return AgentDefinition(
        description="构建错误与坏依赖根因提炼专家",
        prompt=(
            "你是一个 Maven/NPM/PyPI 依赖错误诊断分析器。\n"
            "你的任务是阅读构建失败日志，准确判断是否属于「包管理仓库中不存在该依赖」导致的失败。\n"
            "若确实是坏依赖，请明确指出其 dep_type (maven/npm/pip)、dep_name (坐标或包名) 及不超过 30 字的简要原因；"
            "若为普通语法错误或网络问题，请明确报告 NOT_A_BAD_DEP。"
        ),
        tools=["Read", "mcp__guardrails__record_bad_dependency"],
        model=model
    )


def get_auto_repair_agent(model: Optional[str] = None) -> AgentDefinition:
    """Agent specialized in writing code diff patches and verifying them in sandbox."""
    return AgentDefinition(
        description="代码自愈与补丁生成验证专家",
        prompt=(
            "你是一个代码自愈与自动修复专家。\n"
            "任务流程：\n"
            "1. 根据质量评测与运行报错日志中的具体失分点，生成修复补丁（Git Diff）。\n"
            "2. 调用 mcp__patch_tools__apply_patch 应用补丁。\n"
            "3. 再次调用 mcp__sandbox__sandbox_exec 验证补丁应用后是否能够成功构建并运行通过。"
        ),
        tools=[
            "Read", "Write", "Grep", "Glob",
            "mcp__patch_tools__apply_patch",
            "mcp__sandbox__sandbox_exec"
        ],
        model=model
    )
