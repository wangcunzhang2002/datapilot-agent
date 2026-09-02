import {
  BarChart3,
  CheckCircle2,
  Clock3,
  Code2,
  Database,
  Download,
  Loader2,
  Play,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { analyze, ApiRequestError, type AnalysisResult } from "./api";
import { Badge, Button, Card, Skeleton, Textarea } from "./components/ui";
import { FALLBACK_RESULT } from "./fallback";

const DEMO_QUESTIONS = [
  "哪个地区的销售额最高？",
  "按品类汇总收入",
  "最近几个月的销售趋势",
  "退款订单的状态如何分布？",
];

const STEP_LABELS: Record<string, string> = {
  inspect_schema: "读取数据契约",
  plan_query: "规划只读查询",
  execute_query: "执行 SQL 工具",
  verify_result: "交叉校验结果",
  compose_answer: "组织可追溯结论",
};

function formatValue(value: string | number | null) {
  if (typeof value === "number") {
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
  }
  return value ?? "—";
}

function App() {
  const [question, setQuestion] = useState(DEMO_QUESTIONS[0]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fallbackMode, setFallbackMode] = useState(false);

  async function runAnalysis(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 2) return;
    setLoading(true);
    setError(null);
    setFallbackMode(false);
    try {
      setResult(await analyze(trimmed));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.fallbackAvailable) {
        setResult({ ...FALLBACK_RESULT, question: trimmed });
        setFallbackMode(true);
        setError(caught.message);
      } else {
        setError(caught instanceof Error ? caught.message : "分析失败，请稍后重试。");
      }
    } finally {
      setLoading(false);
    }
  }

  function downloadResult() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `datapilot-${result.run_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const maxChartValue = Math.max(...(result?.chart?.points.map((point) => point.value) ?? [1]));

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white/95">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-blue-700 text-white">
              <BarChart3 className="size-5" aria-hidden="true" />
            </div>
            <div>
              <div className="font-semibold tracking-tight text-slate-950">DataPilot</div>
              <div className="text-xs text-slate-500">可追溯的数据分析同事</div>
            </div>
          </div>
          <Badge className="hidden border-emerald-200 bg-emerald-50 text-emerald-700 sm:inline-flex">
            <span className="mr-1.5 size-1.5 rounded-full bg-emerald-500" />
            默认离线基线 · 可选结构化 LLM
          </Badge>
        </div>
      </header>

      <main className="mx-auto max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8">
        {fallbackMode && (
          <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
            <div className="font-semibold">当前为预录制演示</div>
            <p className="mt-1">在线 Agent 暂时不可用或已达到公开访问限制；页面仍保留完整的展示内容。</p>
          </div>
        )}
        <section className="mb-6 max-w-3xl">
          <Badge className="mb-3 border-blue-200 bg-blue-50 text-blue-700">ANALYTICS COPILOT</Badge>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            从业务问题到经校验的数据结论
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">
            Agent 先检查数据结构，再生成受约束 SQL、执行查询并核对口径。每个结论都能回到 SQL、结果表和运行轨迹。
          </p>
        </section>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
          <div className="min-w-0 space-y-6">
            <Card className="p-4 shadow-sm sm:p-5">
              <form onSubmit={(event) => void runAnalysis(event)}>
                <label htmlFor="question" className="mb-2 block text-sm font-semibold text-slate-800">
                  你想了解什么？
                </label>
                <Textarea
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="例如：哪个地区的销售额最高？"
                  disabled={loading}
                  aria-describedby="question-help"
                />
                <div className="mt-3 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <p id="question-help" className="text-xs text-slate-500">
                    数据范围：18 条脱敏电商订单；工具权限：仅 SELECT、仅 orders 表。
                  </p>
                  <Button type="submit" disabled={loading || question.trim().length < 2}>
                    {loading ? (
                      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <Play className="size-4" aria-hidden="true" />
                    )}
                    {loading ? "分析中" : "开始分析"}
                  </Button>
                </div>
              </form>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                {DEMO_QUESTIONS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                    onClick={() => setQuestion(prompt)}
                    disabled={loading}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </Card>

            <div aria-live="polite">
              {error && (
                <Card className={`${fallbackMode ? "border-amber-200 bg-amber-50 text-amber-900" : "border-red-200 bg-red-50 text-red-800"} p-4 text-sm`}>
                  <div className="font-semibold">{fallbackMode ? "已切换到预录制结果" : "无法完成分析"}</div>
                  <p className="mt-1">{error}</p>
                  {!fallbackMode && <p className="mt-2 text-xs">请稍后重试。</p>}
                </Card>
              )}

              {loading && (
                <div className="space-y-6" aria-label="正在载入分析结果">
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[0, 1, 2].map((item) => (
                      <Skeleton key={item} className="h-24" />
                    ))}
                  </div>
                  <Skeleton className="h-36" />
                  <Skeleton className="h-72" />
                </div>
              )}

              {!loading && !result && !error && (
                <Card className="border-dashed p-8 text-center sm:p-12">
                  <Database className="mx-auto size-9 text-slate-400" aria-hidden="true" />
                  <h2 className="mt-4 font-semibold text-slate-900">等待第一个业务问题</h2>
                  <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
                    选择上方示例或输入自己的问题。当前演示支持业务概览、地区、品类、月度趋势和订单状态分析。
                  </p>
                </Card>
              )}

              {!loading && result && (
                <div className="space-y-6">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Card className="p-4">
                      <div className="text-xs font-medium text-slate-500">结果校验</div>
                      <div className="mt-2 flex items-center gap-2 text-lg font-semibold text-emerald-700">
                        <CheckCircle2 className="size-5" aria-hidden="true" />
                        {result.verification.passed ? "已通过" : "未通过"}
                      </div>
                    </Card>
                    <Card className="p-4">
                      <div className="text-xs font-medium text-slate-500">返回数据</div>
                      <div className="mt-2 text-lg font-semibold text-slate-950">
                        {result.rows.length} 行 × {result.columns.length} 列
                      </div>
                    </Card>
                    <Card className="p-4">
                      <div className="text-xs font-medium text-slate-500">工作流耗时</div>
                      <div className="mt-2 flex items-center gap-2 text-lg font-semibold text-slate-950">
                        <Clock3 className="size-5 text-slate-400" aria-hidden="true" />
                        {result.metrics.duration_ms.toFixed(2)} ms
                      </div>
                    </Card>
                  </div>

                  <Card className="overflow-hidden shadow-sm">
                    <div className="flex flex-col justify-between gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-start">
                      <div>
                        <div className="flex items-center gap-2">
                          <Badge className="border-blue-200 bg-blue-50 text-blue-700">分析结论</Badge>
                          <span className="text-xs text-slate-400">{result.route}</span>
                        </div>
                        <p className="mt-3 text-base leading-7 text-slate-800">{result.answer}</p>
                      </div>
                      <Button variant="outline" onClick={downloadResult} className="shrink-0">
                        <Download className="size-4" aria-hidden="true" />
                        导出 JSON
                      </Button>
                    </div>

                    {result.chart && (
                      <div className="border-b border-slate-100 p-5">
                        <div className="mb-5 flex items-end justify-between gap-4">
                          <div>
                            <h2 className="font-semibold text-slate-900">{result.chart.title}</h2>
                            <p className="mt-1 text-xs text-slate-500">{result.chart.value_label}</p>
                          </div>
                        </div>
                        <div className="space-y-3">
                          {result.chart.points.map((point) => (
                            <div key={point.label} className="grid grid-cols-[72px_minmax(0,1fr)_90px] items-center gap-3 text-sm">
                              <span className="truncate text-slate-600" title={point.label}>{point.label}</span>
                              <div className="h-7 overflow-hidden rounded-md bg-slate-100">
                                <div
                                  className="h-full rounded-md bg-blue-600"
                                  style={{ width: `${Math.max((point.value / maxChartValue) * 100, 2)}%` }}
                                />
                              </div>
                              <span className="text-right font-medium tabular-nums text-slate-800">
                                {formatValue(point.value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="p-5">
                      <h2 className="mb-3 font-semibold text-slate-900">查询结果</h2>
                      <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full min-w-[520px] border-collapse text-left text-sm">
                          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              {result.columns.map((column) => (
                                <th key={column} className="border-b border-slate-200 px-4 py-3 font-semibold">
                                  {column}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {result.rows.map((row, index) => (
                              <tr key={index} className="border-b border-slate-100 last:border-0">
                                {result.columns.map((column) => (
                                  <td key={column} className="px-4 py-3 tabular-nums text-slate-700">
                                    {formatValue(row[column])}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </Card>

                  <Card className="overflow-hidden">
                    <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-3">
                      <Code2 className="size-4 text-slate-500" aria-hidden="true" />
                      <h2 className="text-sm font-semibold text-slate-800">实际执行的 SQL</h2>
                    </div>
                    <pre className="overflow-x-auto bg-slate-950 p-5 text-sm leading-6 text-slate-100">
                      <code>{result.sql}</code>
                    </pre>
                  </Card>
                </div>
              )}
            </div>
          </div>

          <aside className="min-w-0 xl:sticky xl:top-6 xl:self-start">
            <Card className="overflow-hidden shadow-sm">
              <div className="border-b border-slate-200 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 font-semibold text-slate-900">
                    <ShieldCheck className="size-5 text-blue-700" aria-hidden="true" />
                    Agent 运行轨迹
                  </div>
                  {result && <Badge>{result.trace.length} 步</Badge>}
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">轨迹来自本次真实后端执行，不是预设动画。</p>
              </div>

              <div className="p-5">
                {result ? (
                  <ol className="space-y-5">
                    {result.trace.map((step, index) => (
                      <li key={step.name} className="relative pl-8">
                        {index < result.trace.length - 1 && (
                          <span className="absolute left-[11px] top-6 h-[calc(100%+4px)] w-px bg-slate-200" />
                        )}
                        <span className="absolute left-0 top-0.5 grid size-6 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                          <CheckCircle2 className="size-4" aria-hidden="true" />
                        </span>
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-sm font-semibold text-slate-800">
                            {STEP_LABELS[step.name] ?? step.name}
                          </div>
                          <span className="shrink-0 text-[11px] tabular-nums text-slate-400">
                            {step.duration_ms.toFixed(2)} ms
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-5 text-slate-500">{step.summary}</p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <ol className="space-y-4 text-sm text-slate-500">
                    {Object.values(STEP_LABELS).map((label, index) => (
                      <li key={label} className="flex items-center gap-3">
                        <span className="grid size-6 place-items-center rounded-full border border-slate-200 text-[11px] text-slate-400">
                          {index + 1}
                        </span>
                        {label}
                      </li>
                    ))}
                  </ol>
                )}
              </div>

              {result && (
                <div className="border-t border-slate-200 bg-slate-50 p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">校验记录</h3>
                  <ul className="mt-3 space-y-2">
                    {result.verification.checks.map((check) => (
                      <li key={check} className="flex gap-2 text-xs leading-5 text-slate-600">
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                        {check}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          </aside>
        </div>
      </main>
    </div>
  );
}

export default App;
