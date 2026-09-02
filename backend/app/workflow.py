"""LangGraph workflow for deterministic, inspectable data analysis."""

from __future__ import annotations

from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .llm import JsonLLM, LLMProviderError
from .models import (
    AnalysisResponse,
    ChartPoint,
    ChartSpec,
    TraceStep,
    VerificationResult,
)
from .repository import SQLiteAnalyticsRepository

SQL_BY_ROUTE = {
    "revenue_by_region": (
        "SELECT region, ROUND(SUM(amount), 2) AS revenue "
        "FROM orders GROUP BY region ORDER BY revenue DESC"
    ),
    "revenue_by_category": (
        "SELECT category, ROUND(SUM(amount), 2) AS revenue "
        "FROM orders GROUP BY category ORDER BY revenue DESC"
    ),
    "monthly_trend": (
        "SELECT SUBSTR(order_date, 1, 7) AS month, "
        "ROUND(SUM(amount), 2) AS revenue FROM orders GROUP BY month ORDER BY month"
    ),
    "orders_by_status": (
        "SELECT status, COUNT(*) AS order_count FROM orders "
        "GROUP BY status ORDER BY order_count DESC"
    ),
    "business_overview": (
        "SELECT COUNT(*) AS order_count, ROUND(SUM(amount), 2) AS revenue, "
        "ROUND(AVG(amount), 2) AS avg_order_value, "
        "SUM(CASE WHEN status = 'refunded' THEN 1 ELSE 0 END) AS refunded_orders "
        "FROM orders"
    ),
}


class DataPilotState(TypedDict, total=False):
    """State exchanged by the five bounded workflow steps."""

    question: str
    schema: str
    route: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    chart: ChartSpec | None
    answer: str
    verification: VerificationResult
    trace: list[TraceStep]
    planner_mode: str
    model_call_count: int
    fallback_count: int


class DataPilotAgent:
    """Plan, execute, verify, and explain a supported analytics question."""

    def __init__(
        self, repository: SQLiteAnalyticsRepository, llm: JsonLLM | None = None
    ) -> None:
        self.repository = repository
        self.llm = llm
        graph = StateGraph(DataPilotState)
        graph.add_node("inspect_schema", self._inspect_schema)
        graph.add_node("plan_query", self._plan_query)
        graph.add_node("execute_query", self._execute_query)
        graph.add_node("verify_result", self._verify_result)
        graph.add_node("compose_answer", self._compose_answer)
        graph.add_edge(START, "inspect_schema")
        graph.add_edge("inspect_schema", "plan_query")
        graph.add_edge("plan_query", "execute_query")
        graph.add_edge("execute_query", "verify_result")
        graph.add_edge("verify_result", "compose_answer")
        graph.add_edge("compose_answer", END)
        self.graph = graph.compile()

    @staticmethod
    def _trace(
        state: DataPilotState,
        *,
        name: str,
        summary: str,
        started_at: float,
    ) -> list[TraceStep]:
        return [
            *state.get("trace", []),
            TraceStep(
                name=name,
                status="completed",
                summary=summary,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            ),
        ]

    def _inspect_schema(self, state: DataPilotState) -> DataPilotState:
        started_at = perf_counter()
        schema = self.repository.schema_summary()
        return {
            "schema": schema,
            "trace": self._trace(
                state,
                name="inspect_schema",
                summary=f"读取允许访问的数据表：{schema}",
                started_at=started_at,
            ),
        }

    @staticmethod
    def _deterministic_route(question: str) -> str:
        lowered = question.lower()
        if any(word in lowered for word in ("地区", "区域", "region")):
            return "revenue_by_region"
        if any(word in lowered for word in ("品类", "类别", "category")):
            return "revenue_by_category"
        if any(word in lowered for word in ("月", "趋势", "trend")):
            return "monthly_trend"
        if any(word in lowered for word in ("退款", "状态", "refund", "status")):
            return "orders_by_status"
        return "business_overview"

    def _plan_query(self, state: DataPilotState) -> DataPilotState:
        started_at = perf_counter()
        route = self._deterministic_route(state["question"])
        planner_mode = "deterministic"
        model_call_count = 0
        fallback_count = 0
        if self.llm is not None:
            model_call_count = 1
            try:
                payload = self.llm.complete_json(
                    system=(
                        "你是数据分析路由器。只返回 JSON 对象，键为 route。route 必须是："
                        f"{', '.join(SQL_BY_ROUTE)}。不要生成 SQL。"
                    ),
                    user=f"Schema: {state['schema']}\n业务问题: {state['question']}",
                )
                candidate = payload.get("route")
                if not isinstance(candidate, str) or candidate not in SQL_BY_ROUTE:
                    raise LLMProviderError("Model selected an unsupported analytics route.")
                route = candidate
                planner_mode = "llm"
            except LLMProviderError:
                planner_mode = "fallback"
                fallback_count = 1
        sql = SQL_BY_ROUTE[route]
        return {
            "route": route,
            "sql": sql,
            "planner_mode": planner_mode,
            "model_call_count": model_call_count,
            "fallback_count": fallback_count,
            "trace": self._trace(
                state,
                name="plan_query",
                summary=f"以 {planner_mode} 模式选择分析意图 {route}，SQL 仍来自审查模板。",
                started_at=started_at,
            ),
        }

    def _execute_query(self, state: DataPilotState) -> DataPilotState:
        started_at = perf_counter()
        columns, rows = self.repository.execute(state["sql"])
        return {
            "columns": columns,
            "rows": rows,
            "trace": self._trace(
                state,
                name="execute_query",
                summary=f"只读工具返回 {len(rows)} 行、{len(columns)} 列。",
                started_at=started_at,
            ),
        }

    def _verify_result(self, state: DataPilotState) -> DataPilotState:
        started_at = perf_counter()
        rows = state["rows"]
        checks = ["SQL 通过只读语句与 orders 单表白名单校验"]
        passed = bool(rows)

        if state["route"] in {
            "revenue_by_region",
            "revenue_by_category",
            "monthly_trend",
        }:
            grouped_total = round(sum(float(row["revenue"]) for row in rows), 2)
            source_total = round(
                self.repository.scalar("SELECT SUM(amount) AS total FROM orders"), 2
            )
            totals_match = abs(grouped_total - source_total) < 0.01
            checks.append(
                f"分组汇总 {grouped_total:.2f} 与源表总额 {source_total:.2f} "
                f"{'一致' if totals_match else '不一致'}"
            )
            passed = passed and totals_match
        elif state["route"] == "orders_by_status":
            grouped_count = sum(int(row["order_count"]) for row in rows)
            source_count = int(
                self.repository.scalar("SELECT COUNT(*) AS total FROM orders")
            )
            counts_match = grouped_count == source_count
            checks.append(
                f"状态分组订单数 {grouped_count} 与源表订单数 {source_count} "
                f"{'一致' if counts_match else '不一致'}"
            )
            passed = passed and counts_match
        else:
            checks.append("概览指标来自同一条聚合查询，无跨查询口径差异")

        verification = VerificationResult(passed=passed, checks=checks)
        return {
            "verification": verification,
            "trace": self._trace(
                state,
                name="verify_result",
                summary=f"执行 {len(checks)} 项结果校验，结论：{'通过' if passed else '未通过'}。",
                started_at=started_at,
            ),
        }

    def _compose_answer(self, state: DataPilotState) -> DataPilotState:
        started_at = perf_counter()
        rows = state["rows"]
        route = state["route"]
        chart: ChartSpec | None = None

        if route == "business_overview":
            row = rows[0]
            answer = (
                f"样例数据共有 {row['order_count']} 笔订单，销售额 {row['revenue']:.2f} 元，"
                f"平均客单价 {row['avg_order_value']:.2f} 元，其中退款订单 "
                f"{row['refunded_orders']} 笔。"
            )
        else:
            label_key, value_key = state["columns"][0], state["columns"][1]
            leader = rows[0]
            if route == "orders_by_status":
                value_label = "订单数"
                title = "订单状态分布"
            else:
                value_label = "销售额（元）"
                title = {
                    "revenue_by_region": "地区销售额",
                    "revenue_by_category": "品类销售额",
                    "monthly_trend": "月度销售趋势",
                }[route]
            answer = (
                f"在 {len(rows)} 个分组中，{leader[label_key]} 排名第一，"
                f"对应{value_label}为 {leader[value_key]}。完整结果见数据表。"
            )
            chart = ChartSpec(
                title=title,
                value_label=value_label,
                points=[
                    ChartPoint(label=str(row[label_key]), value=float(row[value_key]))
                    for row in rows
                ],
            )

        return {
            "answer": answer,
            "chart": chart,
            "trace": self._trace(
                state,
                name="compose_answer",
                summary="仅根据已执行结果生成结论，并保留 SQL、表格与校验轨迹。",
                started_at=started_at,
            ),
        }

    def analyze(self, question: str) -> AnalysisResponse:
        """Run the compiled graph and return its public response contract."""

        state = self.graph.invoke({"question": question, "trace": []})
        total_duration = round(sum(step.duration_ms for step in state["trace"]), 2)
        return AnalysisResponse(
            run_id=str(uuid4()),
            question=question,
            route=state["route"],
            answer=state["answer"],
            sql=state["sql"],
            columns=state["columns"],
            rows=state["rows"],
            chart=state["chart"],
            verification=state["verification"],
            trace=state["trace"],
            metrics={
                "execution_success": 1,
                "verification_passed": int(state["verification"].passed),
                "correction_count": 0,
                "tool_calls": 3,
                "duration_ms": total_duration,
                "model_call_count": state["model_call_count"],
                "llm_fallback_count": state["fallback_count"],
            },
        )
