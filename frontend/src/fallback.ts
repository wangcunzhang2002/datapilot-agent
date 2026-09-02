import type { AnalysisResult } from "./api";

/** A deterministic, pre-recorded result kept available for provider outages and limits. */
export const FALLBACK_RESULT: AnalysisResult = {
  run_id: "fallback-datapilot",
  question: "哪个地区的销售额最高？",
  route: "revenue_by_region",
  answer: "这是预录制示例：华东地区排名第一，对应销售额为 11,657 元。",
  sql: "SELECT region, ROUND(SUM(amount), 2) AS revenue FROM orders GROUP BY region ORDER BY revenue DESC",
  columns: ["region", "revenue"],
  rows: [
    { region: "华东", revenue: 11657 },
    { region: "华南", revenue: 10057 },
    { region: "西南", revenue: 7077 },
    { region: "华北", revenue: 5977 },
  ],
  chart: {
    title: "地区销售额（预录制）",
    value_label: "销售额（元）",
    points: [
      { label: "华东", value: 11657 },
      { label: "华南", value: 10057 },
      { label: "西南", value: 7077 },
      { label: "华北", value: 5977 },
    ],
  },
  verification: {
    passed: true,
    checks: ["预录制结果来自受控只读查询示例；未执行本次在线请求。"],
  },
  trace: [
    { name: "inspect_schema", status: "completed", summary: "读取演示数据契约。", duration_ms: 0 },
    { name: "plan_query", status: "completed", summary: "选择地区销售额分析模板。", duration_ms: 0 },
    { name: "execute_query", status: "completed", summary: "载入预录制结果表。", duration_ms: 0 },
    { name: "verify_result", status: "completed", summary: "展示预录制校验记录。", duration_ms: 0 },
    { name: "compose_answer", status: "completed", summary: "组织可追溯示例结论。", duration_ms: 0 },
  ],
  metrics: {
    execution_success: 1,
    verification_passed: 1,
    correction_count: 0,
    tool_calls: 0,
    duration_ms: 0,
    model_call_count: 0,
    llm_fallback_count: 1,
  },
};
