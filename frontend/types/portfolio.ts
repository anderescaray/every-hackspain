import { z } from "zod";
import { pulseEnvelopeShape, pulseStatusSchema } from "./pulse";

const text = z.string().min(1).max(2000);
const score = z.number().finite().min(0).max(100);
const amount = z.number().finite();
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const trajectorySchema = z.enum(["improving", "deteriorating", "stable"]);
const attentionSchema = z.enum(["high", "medium", "low", "unknown"]);
const statusSchema = pulseStatusSchema;

const itemSchema = z.object({
  company_id: z.string().regex(/^COMP_\d{4,10}$/),
  group_id: text.nullable(),
  health_score: score.nullable(),
  delta_vs_prev: amount.nullable(),
  trajectory: trajectorySchema.nullable(),
  trajectory_stage: z.enum(["confirmed", "emerging"]).nullable(),
  confidence: score.nullable(),
  score_status: statusSchema,
  status_reason: text.nullable(),
  main_signal: text.nullable(),
  main_signal_impact: amount.nullable(),
  support_dependency_ratio: z.number().min(0).max(1).nullable(),
  attention: attentionSchema,
  has_detail: z.boolean(),
  run_id: text,
  dimensions: z.object({ momentum: score.nullable(), cash_generation: score.nullable(), resilience: score.nullable(), debt: score.nullable() }).strict(),
  missing_components: z.array(text),
  robustness: text,
}).strict();

export const portfolioSchema = z.object({
  schema_version: z.literal("2.0"),
  ...pulseEnvelopeShape,
  source: z.enum(["generated", "fixture"]),
  as_of: date,
  period: text,
  currency: z.literal("EUR"),
  summary: text,
  items: z.array(itemSchema).max(5000),
}).strict().superRefine((portfolio, ctx) => {
  const ids = portfolio.items.map((item) => item.company_id);
  if (new Set(ids).size !== ids.length) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Identificadores duplicados", path: ["items"] });
  portfolio.items.forEach((item, index) => {
    if ((item.score_status === "complete") !== (item.health_score !== null)) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Una empresa sin puntuar no puede tener Health Score", path: ["items", index] });
    if (item.run_id !== portfolio.run_id) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Cartera con runs mezclados", path: ["items", index] });
    if (item.trajectory === null && item.trajectory_stage !== null) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Sin trayectoria no hay fase", path: ["items", index] });
  });
});

export type Portfolio = z.infer<typeof portfolioSchema>;
export type PortfolioItem = z.infer<typeof itemSchema>;
export type PortfolioAttention = z.infer<typeof attentionSchema>;
export type PortfolioStatus = z.infer<typeof statusSchema>;
