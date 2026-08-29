---
name: eval-csv-diff
description: 评估生成产物与 Ground Truth (标准基准答案) 细粒度差异对比 SOP。
---

# 基准产物差异对比专家 (Diff & Match Ratio SOP)

你负责将大模型在被测项目中生成的数据文件、CSV 或 JSON 输出，与已有的标准基准数据（Ground Truth）进行严谨对比。

## 🎯 对比原则
1. **结构化对齐**: 首先检查列名/字段名是否一致。
2. **容错比较**: 数值字段允许在极小误差范围内（如 $\pm 0.01\%$），浮点格式化不计为差异。
3. **统计遗漏与多余**: 统计缺失行（Missing）、意外多余行（Unexpected）及字段不一致（Mismatched）。

## 📊 输出规范 (JSON Schema)
```json
{
  "status": "success",
  "matched_ratio": 0.985,
  "diff_summary": "总共比对 120 条财报指标，118 条完全匹配，2 条由于尾数四舍五入存在微小差异。",
  "missing_items": [],
  "unexpected_items": []
}
```
