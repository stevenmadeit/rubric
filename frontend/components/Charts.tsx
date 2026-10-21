"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CategoryMetric, RunSummary } from "@/lib/api";

const COLORS = ["#a78bfa", "#58d5c0", "#67a7ff", "#f6ad55"];
const PROMPTS = ["basic", "step_by_step", "structured"];

export function AccuracyChart({ runs }: { runs: RunSummary[] }) {
  const latest = new Map<string, RunSummary>();
  for (const run of [...runs].sort(
    (a, b) => Date.parse(a.started_at) - Date.parse(b.started_at),
  )) {
    latest.set(`${run.model_name}|${run.prompt_variant}`, run);
  }
  const models = Array.from(new Set(runs.map((run) => run.model_name)));
  const data = models.map((model) => {
    const row: Record<string, string | number | null> = { model };
    for (const prompt of PROMPTS) {
      row[prompt] = latest.get(`${model}|${prompt}`)?.accuracy ?? null;
    }
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 12, right: 14, left: -16, bottom: 4 }} barGap={5}>
        <CartesianGrid stroke="#252a3a" vertical={false} />
        <XAxis dataKey="model" tick={{ fill: "#8f96aa", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} tick={{ fill: "#777f94", fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip formatter={(value, name) => [typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—", String(name)]} cursor={{ fill: "#ffffff08" }} contentStyle={{ background: "#171b28", border: "1px solid #30364a", borderRadius: 10, color: "#f4f5f8" }} />
        <Legend wrapperStyle={{ color: "#9aa1b4", fontSize: 11 }} />
        {PROMPTS.map((prompt, index) => (
          <Bar key={prompt} dataKey={prompt} fill={COLORS[index]} radius={[4, 4, 0, 0]} maxBarSize={30} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CategoryChart({ categories }: { categories: CategoryMetric[] }) {
  const models = Array.from(new Set(categories.map((item) => item.model_name)));
  const names = Array.from(new Set(categories.map((item) => item.category)));
  const data = names.map((category) => {
    const row: Record<string, string | number | null> = { category: category.replaceAll("_", " ") };
    for (const model of models) {
      row[model] = categories.find(
        (item) => item.category === category && item.model_name === model,
      )?.accuracy ?? null;
    }
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 12, right: 8, left: -16, bottom: 4 }} barGap={4}>
        <CartesianGrid stroke="#252a3a" vertical={false} />
        <XAxis dataKey="category" interval={0} tick={{ fill: "#8f96aa", fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} tick={{ fill: "#777f94", fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip formatter={(value, name) => [typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—", String(name)]} cursor={{ fill: "#ffffff08" }} contentStyle={{ background: "#171b28", border: "1px solid #30364a", borderRadius: 10, color: "#f4f5f8" }} />
        <Legend wrapperStyle={{ color: "#9aa1b4", fontSize: 11 }} />
        {models.map((model, index) => (
          <Bar key={model} dataKey={model} fill={COLORS[index % COLORS.length]} radius={[3, 3, 0, 0]} maxBarSize={24} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
