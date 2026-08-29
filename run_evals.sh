#!/bin/bash
# run_evals.sh — 5阶段批量评测：dialog预处理 → 运行验证 → 准确性打分 → 质量打分 → CSV对比 → 汇总TSV
# 每阶段幂等（JSON已存在则跳过），失败只需重跑对应阶段
#
# 目录说明：
#   eval/       — 评测规范 + output.md 输出表格（勿删）
#   evals/logs/ — 自动生成的阶段日志（可删，重跑会重建）
#
# 用法：
#   ./run_evals.sh          # 跑所有 case
#   ./run_evals.sh 1 20     # 只跑指定 case

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$WORK_DIR/evals/logs"
mkdir -p "$LOGS_DIR"

# 公共 claude 调用参数（数组形式，防止路径含空格时参数分裂）
CLAUDE_ARGS=(--output-format stream-json --verbose --allowedTools "Read,Write,Bash")

# 收集 case 列表
if [ $# -gt 0 ]; then
  CASES=("$@")
else
  CASES=()
  for d in "$WORK_DIR"/[0-9]*/; do
    CASES+=("$(basename "$d")")
  done
fi

echo "待评测 case：${CASES[*]}"
echo "日志目录：$LOGS_DIR"
echo "---"

run_stage() {
  local stage_name="$1"   # 阶段名，用于日志文件名
  local skill_cmd="$2"    # 传给 claude 的 /skill 命令
  local case_dir="$3"
  local case_id="$4"
  local output_file="$5"  # 幂等判断：此文件存在则跳过

  local log_file="$LOGS_DIR/${case_id}_${stage_name}.txt"

  if [ -f "$output_file" ]; then
    echo "  [SKIP] $stage_name — 已有结果：$(basename "$output_file")"
    return 0
  fi

  echo "  [RUN ] $stage_name ..."
  local t_start t_end elapsed
  t_start=$(date +%s)

  # stream-json 实时格式化：tee 原始 jsonl 到日志，同时解析并打印进度
  local exit_code=0
  local prefix="  [$case_id][$stage_name]"
  claude "${CLAUDE_ARGS[@]}" -p "$skill_cmd $case_dir" 2>&1 | tee "$log_file" | python3 -u - "$prefix" "${QUIET:-0}" <<'PYEOF'
import sys, json

prefix = sys.argv[1]
quiet = sys.argv[2] == "1"
tool_name = None

for line in sys.stdin:
    line = line.rstrip()
    if not line:
        continue
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        if not quiet:
            print(line, flush=True)
        continue

    t = ev.get("type", "")

    if t == "content_block_start":
        cb = ev.get("content_block", {})
        if cb.get("type") == "tool_use":
            tool_name = cb.get("name", "?")
            tool_input_buf = ""
    elif t == "content_block_delta":
        delta = ev.get("delta", {})
        dt = delta.get("type", "")
        if dt == "text_delta":
            text = delta.get("text", "")
            if not quiet:
                print(text, end="", flush=True)
        elif dt == "input_json_delta" and tool_name:
            tool_input_buf += delta.get("partial_json", "")
    elif t == "content_block_stop":
        if tool_name:
            # 尝试提取关键参数显示
            try:
                inp = json.loads(tool_input_buf)
                arg = inp.get("file_path") or inp.get("command", "")[:60] or ""
            except Exception:
                arg = ""
            label = f"  → {tool_name}  {arg}" if arg else f"  → {tool_name}"
            print(f"\n{prefix} {label}", flush=True)
            tool_name = None
        else:
            if not quiet:
                print(flush=True)
    elif t == "message_stop":
        pass  # 不打印，由 shell 输出 [DONE]
PYEOF
  exit_code="${PIPESTATUS[0]}"

  t_end=$(date +%s); elapsed=$((t_end - t_start))

  if [ "$exit_code" -eq 0 ]; then
    echo "  [DONE] $stage_name （${elapsed}s）"
    # eval-run 超过阈值且结果为 fail，触发自动学习
    if [ "$stage_name" = "run" ] && [ "$elapsed" -gt "${RUN_SLOW_THRESHOLD:-120}" ]; then
      local run_result="$case_dir/eval_run_result.json"
      local run_status
      run_status=$(python3 -c "import json,sys; d=json.load(open('$run_result')); print(d.get('status',''))" 2>/dev/null || echo "")
      if [ "$run_status" = "fail" ]; then
        echo "  [SLOW-FAIL] eval-run 耗时 ${elapsed}s 且失败，触发自动学习..."
        auto_learn_bad_dep "$case_dir" "$run_result" "$log_file"
      fi
    fi
  else
    echo "  [FAIL] $stage_name （${elapsed}s）— 查看 $log_file"
    return 1
  fi
}

# eval-run 慢+失败后，分析失败原因并自动将新坏依赖追加到 bad_deps.conf
auto_learn_bad_dep() {
  local case_dir="$1"
  local run_result_json="$2"
  local run_log="$3"

  local bad_deps_conf="$WORK_DIR/bad_deps.conf"

  # 从 run_result.json 提取 error_snippet，交给 claude 分析是否是可静态检测的坏依赖
  local error_snippet
  error_snippet=$(python3 -c "
import json, sys
d = json.load(open('$run_result_json'))
print(d.get('error_snippet', '') or d.get('log_summary', ''))
" 2>/dev/null || tail -30 "$run_log")

  if [ -z "$error_snippet" ]; then
    echo "  [LEARN] 无错误信息，跳过自动学习"
    return
  fi

  # 白名单过滤：只保留可打印 ASCII + 常见中文范围，防止构建日志中的注入内容影响 LLM
  error_snippet=$(echo "$error_snippet" | python3 -c "
import sys, re
text = sys.stdin.read()
# 只保留可打印 ASCII（0x20-0x7E）、换行、制表符、以及中日韩常用字符范围
cleaned = re.sub(r'[^\x20-\x7e\n\t一-鿿　-〿＀-￯]', '', text)
# 截断到 2000 字符防止超长注入
print(cleaned[:2000])
")

  echo "  [LEARN] 分析失败原因..."
  local learn_prompt
  learn_prompt="你是一个 Maven/npm/pip 依赖错误分析器。

以下是一次构建失败的错误信息：
---
$error_snippet
---

任务：
1. 判断这是否是「依赖在包管理仓库中不存在」导致的失败（如 Maven Central 没有该 artifact、npm 404、pip 包名错误）。
2. 如果是，按以下格式回复（dep_type 必须是 maven/npm/pip 之一，dep_id 格式：Maven 用 groupId:artifactId，npm/pip 用包名）：
   BAD_DEP: <dep_type>:<dep_id>  # <原因，不超过30字>
3. 如果不是，回复：NOT_A_BAD_DEP

示例：
  BAD_DEP: maven:org.apache.poi:poi-ooxml-schemas  # POI 5.x 已移除
  BAD_DEP: npm:some-package  # 已从 npm 下架
  BAD_DEP: pip:bad-package  # PyPI 上不存在此包名
  NOT_A_BAD_DEP

只回复以上格式之一（不要多余文字）：
BAD_DEP: <dep_type>:<dep_id>  # <原因，不超过30字>
NOT_A_BAD_DEP"

  local result
  result=$(claude --print --allowedTools "" -p "$learn_prompt" 2>/dev/null | tr -d '\n' | sed 's/^[[:space:]]*//')

  if [[ "$result" == BAD_DEP:* ]]; then
    local dep_line="${result#BAD_DEP: }"
    local dep_type_and_id comment
    dep_type_and_id=$(echo "$dep_line" | cut -d'#' -f1 | sed 's/[[:space:]]*$//')
    comment=$(echo "$dep_line" | cut -d'#' -f2- | sed 's/^[[:space:]]*//')

    # 提取类型前缀（maven/npm/pip）并校验
    local dep_type dep_id
    dep_type=$(echo "$dep_type_and_id" | cut -d: -f1)
    dep_id=$(echo "$dep_type_and_id" | cut -d: -f2-)

    if ! echo "$dep_type" | grep -qE '^(maven|npm|pip)$'; then
      echo "  [LEARN] dep_type 非法（$dep_type），跳过写入"
      return
    fi
    # dep_id 只允许字母、数字、连字符、点、冒号
    if ! echo "$dep_id" | grep -qE '^[a-zA-Z0-9:._-]+$'; then
      echo "  [LEARN] dep_id 格式非法（$dep_id），跳过写入"
      return
    fi

    local conf_entry="${dep_type}:${dep_id}"

    # mkdir 原子锁：兼容 macOS/Linux，防止并行 case 同时写 bad_deps.conf
    local learn_lockdir="$WORK_DIR/.bad_deps_learn.lockdir"
    local lock_attempts=0
    while ! mkdir "$learn_lockdir" 2>/dev/null; do
      lock_attempts=$((lock_attempts + 1))
      if [ "$lock_attempts" -ge 300 ]; then
        echo "  [LEARN] 获取 bad_deps 写锁超时，跳过本次自动学习"
        return
      fi
      sleep 0.1
    done
    (
      trap 'rmdir "$learn_lockdir" 2>/dev/null || true' EXIT INT TERM
      if grep -qF "$conf_entry" "$bad_deps_conf" 2>/dev/null; then
        echo "  [LEARN] 已存在：$conf_entry，跳过"
        exit 0
      fi

      echo "  [LEARN] 发现新坏依赖：$conf_entry  # $comment"
      echo "  [LEARN] 追加到 bad_deps.conf ..."
      printf '%s  # %s\n' "$conf_entry" "$comment" >> "$bad_deps_conf"
      echo "  [LEARN] 下次运行同类 case 将直接快速跳过"
    )
  else
    echo "  [LEARN] 非坏依赖失败（$result），无需更新 bad_deps"
  fi
}

# 快速路径：静态检测明确的构建失败，跳过 eval-run 的 LLM 调用，直接写 fail JSON
# 仅针对常见的、结论确定的失败模式；无法静态判断时返回 1，让 eval-run 正常跑
# 坏依赖列表从外部文件 bad_deps.conf 读取，auto_learn 动态追加，无需修改此脚本
quick_fail_run() {
  local case_dir="$1"
  local output_file="$2"

  local bad_deps_conf="$WORK_DIR/bad_deps.conf"
  local found_bad="" found_type=""

  # bad_deps.conf 不存在则直接跳过快速路径
  [ -f "$bad_deps_conf" ] || return 1

  # 读取 bad_deps.conf，跳过注释行和空行
  while IFS= read -r line || [ -n "$line" ]; do
    # 去掉行内注释和首尾空白
    local entry
    entry=$(echo "$line" | sed 's/#.*//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$entry" ] && continue

    local type id
    type=$(echo "$entry" | cut -d: -f1)
    id=$(echo "$entry" | cut -d: -f2-)

    case "$type" in
      maven)
        local g a
        g=$(echo "$id" | cut -d: -f1)
        a=$(echo "$id" | cut -d: -f2)
        # 用 Python 解析 XML，确保 groupId 与 artifactId 在同一个 <dependency> 块内匹配
        if python3 - "$case_dir/mnt" "$g" "$a" <<'PYEOF' 2>/dev/null; then
import sys, os
from xml.etree import ElementTree as ET

mnt_dir, group_id, artifact_id = sys.argv[1], sys.argv[2], sys.argv[3]
found = False
for root_dir, dirs, files in os.walk(mnt_dir):
    for fname in files:
        if fname != "pom.xml":
            continue
        try:
            tree = ET.parse(os.path.join(root_dir, fname))
        except ET.ParseError:
            continue
        # 支持带命名空间的 pom.xml
        ns = ""
        root = tree.getroot()
        tag = root.tag
        if tag.startswith("{"):
            ns = tag[:tag.index("}") + 1]
        for dep in root.iter(f"{ns}dependency"):
            g_el = dep.find(f"{ns}groupId")
            a_el = dep.find(f"{ns}artifactId")
            if g_el is not None and a_el is not None:
                if g_el.text == group_id and a_el.text == artifact_id:
                    found = True
                    break
        if found:
            break
sys.exit(0 if found else 1)
PYEOF
          found_bad="$id"; found_type="maven"; break
        fi
        ;;
      npm)
        local pkg_files
        pkg_files=$(find "$case_dir/mnt" -name "package.json" -not -path "*/node_modules/*" 2>/dev/null)
        if [ -n "$pkg_files" ] && echo "$pkg_files" | xargs grep -l "\"$id\"" 2>/dev/null | grep -q .; then
          found_bad="$id"; found_type="npm"; break
        fi
        ;;
      pip)
        local req_files
        req_files=$(find "$case_dir/mnt" -name "requirements*.txt" 2>/dev/null)
        # 匹配行首包名，后跟版本约束符、空白或行尾，防止误匹配前缀相同的包（如 requests vs requests-toolbelt）
        if [ -n "$req_files" ] && echo "$req_files" | xargs grep -ilE "^${id}([=<>!~[:space:]]|$)" 2>/dev/null | grep -q .; then
          found_bad="$id"; found_type="pip"; break
        fi
        ;;
    esac
  done < "$bad_deps_conf"

  if [ -n "$found_bad" ]; then
    echo "  [FAST-FAIL] 检测到已知坏依赖（$found_type）：$found_bad，跳过运行，直接写 fail"
    python3 - "$found_type" "$found_bad" > "$output_file" <<'PYEOF'
import json, sys
found_type, found_bad = sys.argv[1], sys.argv[2]
data = {
  "status": "fail",
  "attempt_count": 0,
  "exit_code": 1,
  "log_summary": f"静态检测：{found_type} 依赖 {found_bad} 已知无法解析",
  "error_snippet": f"Dependency {found_bad} not found in {found_type} registry",
  "run_method": "static_analysis",
  "note": f"快速路径静态检测命中，未实际执行构建。{found_bad} 已被移除或重命名，需修改依赖声明后才能构建。",
  "inspect_cmd": ""
}
print(json.dumps(data, ensure_ascii=False, indent=2))
PYEOF
    return 0
  fi

  return 1  # 未命中快速路径，交给 eval-run 正常处理
}

run_case() {
  local case_id="$1"
  local case_dir="$WORK_DIR/$case_id"

  # 子进程意外退出时给出明确提示，方便排查（不影响其他并行 case）
  trap 'echo "[CRASH] case $case_id 意外退出（ERR trap），查看 $LOGS_DIR/${case_id}_*.txt"' ERR

  if [ ! -d "$case_dir" ]; then
    echo "[SKIP] $case_id — 目录不存在"
    return 0
  fi

  echo "[CASE $case_id]"

  # 本地确定任务类型：非空 gt/ 为理解类，否则为生成类；理解类跳过不适用阶段。
  python3 "$WORK_DIR/eval/workflow.py" prepare "$case_dir" >/dev/null

  # 阶段0：固定规则的 dialog 预处理在本地执行，不消耗模型 token。
  if [ -f "$case_dir/eval_dialog_summary.json" ]; then
    echo "  [SKIP] dialog-parse — 已有结果：eval_dialog_summary.json"
  elif python3 "$WORK_DIR/eval/claude-skills/eval-dialog-parse/scripts/parse_dialog.py" "$case_dir" > "$LOGS_DIR/${case_id}_dialog-parse.txt" 2>&1; then
    echo "  [DONE] dialog-parse（本地）"
  else
    echo "  [FAIL] dialog-parse — 查看 $LOGS_DIR/${case_id}_dialog-parse.txt"
    return 0
  fi

  # 阶段1：运行验证（先静态快速路径，再 LLM eval-run）
  if [ ! -f "$case_dir/eval_run_result.json" ]; then
    quick_fail_run "$case_dir" "$case_dir/eval_run_result.json" || true
  fi
  run_stage "run" "/eval-run-utm" \
    "$case_dir" "$case_id" \
    "$case_dir/eval_run_result.json" || { echo "[$case_id] 跳到下一个 case"; return 0; }

  # 阶段2：准确性打分（不读CSV，独立评分）
  run_stage "accuracy" "/eval-accuracy" \
    "$case_dir" "$case_id" \
    "$case_dir/eval_accuracy.json" || { echo "[$case_id] 跳到下一个 case"; return 0; }

  # 阶段3：代码质量+UX打分（含归因文本写作）
  run_stage "quality" "/eval-quality" \
    "$case_dir" "$case_id" \
    "$case_dir/eval_quality.json" || { echo "[$case_id] 跳到下一个 case"; return 0; }

  # 阶段4：CSV对比差异（物理隔离：此时才第一次读CSV）
  run_stage "csv-diff" "/eval-csv-diff" \
    "$case_dir" "$case_id" \
    "$case_dir/eval_csv_diff.json" || { echo "[$case_id] 跳到下一个 case"; return 0; }

  # 汇总：mkdir 原子锁保护 output.md 防止并行写竞争（兼容 macOS/Linux）
  local merge_log="$LOGS_DIR/${case_id}_merge.txt"
  local lockdir="$WORK_DIR/eval/.output_merge.lock"
  # 清理残留的同名普通文件（异常退出时可能留下），防止 mkdir 永远失败
  [ -f "$lockdir" ] && rm -f "$lockdir"
  while ! mkdir "$lockdir" 2>/dev/null; do sleep 0.1; done
  # 确保无论后续如何退出（崩溃/kill）都释放锁，防止自旋死锁
  trap 'rmdir "$lockdir" 2>/dev/null' EXIT
  echo "  [$case_id][MERGE] 更新 eval/output.md ..."
  if python3 "$WORK_DIR/merge_eval.py" "$case_id" > "$merge_log" 2>&1; then
    echo "  [$case_id][DONE] Case $case_id 完成"
  else
    echo "  [$case_id][FAIL] merge — 查看 $merge_log"
    cat "$merge_log" >&2
  fi
  rmdir "$lockdir" 2>/dev/null
  trap - EXIT

  echo "[$case_id] ---"
}

# 并行执行所有 case（每个 case 独立，OrbStack 端口按 case_id 固定偏移不冲突）
PIDS=()
for case_id in "${CASES[@]}"; do
  run_case "$case_id" &
  PIDS+=($!)
done

# 等待所有并行 case 完成，收集失败
FAIL=0
for pid in "${PIDS[@]}"; do
  wait "$pid" || FAIL=$((FAIL + 1))
done

echo "全部完成（失败 case 数：${FAIL}）。结果在 eval/output.md，日志在 $LOGS_DIR/"

# 评测结束后清理资源（electron-env 保持运行，供后续界面交互使用）

# 刷新可视化
echo "刷新可视化..."
python3 "$WORK_DIR/merge_eval.py" --rebuild
python3 "$WORK_DIR/eval/visualize.py" && echo "可视化已更新：eval/output_viz.html"
echo "人工审核：运行 ./review_evals.sh 后访问终端显示的本地地址"
