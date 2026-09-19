import { z } from "zod";

const finite = z.number().finite();
const score = finite.min(0).max(100);
const text = z.string().min(1);
export const pulseStatusSchema = z.enum(["complete", "partial", "insufficient_evidence"]);
export const pulseEnvelopeShape = {
  snapshot_id: z.string().regex(/^web-[a-f0-9]{64}$/),
  run_id: text,
  score_version: z.literal("PulseFourPillars-v1.0"),
  classification_version: text,
  cleaning_version: text,
  facts_version: text,
  config_version: text,
  as_of: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  // This presentation is explicitly EUR-only; no implicit FX conversion.
  currency: z.literal("EUR"),
};
export const pulseEnvelopeSchema = z.object(pulseEnvelopeShape);
export const envelopeKeys = Object.keys(pulseEnvelopeShape) as (keyof typeof pulseEnvelopeShape)[];
const feature = z.object({ raw: finite.nullable(), score: score.nullable(), numerator: finite.nullable(), denominator: finite.nullable(), formula_id: text, anchors: z.unknown() }).passthrough();
const pillar = z.object({ score: score.nullable(), weight: finite.min(0).max(1), health_contribution: finite.nullable(), features: z.record(feature), evidence_status: z.enum(["verified", "partial", "unknown"]).optional(), evidence_reason: text.optional() }).passthrough();
export const pulsePillarKeys = ["generation", "momentum", "resilience", "debt_obligations"] as const;
export const pulseSchema = z.object({
  schema_version: z.literal("1.0"),
  run_id: text, score_version: pulseEnvelopeShape.score_version,
  classification_version: text, cleaning_version: text, facts_version: text, config_version: text,
  company_id: text, currency: z.literal("EUR"), as_of: pulseEnvelopeShape.as_of,
  status: pulseStatusSchema, health: score.nullable(),
  pillars: z.object({ generation: pillar, momentum: pillar, resilience: pillar, debt_obligations: pillar }).strict(),
  known_weight: finite.min(0).max(1), health_min: score, health_max: score,
  bounds_kind: z.literal("identification_bounds_not_confidence_interval"),
  missing_components: z.array(z.enum(pulsePillarKeys)),
  raw_features: z.record(finite.nullable()), normalized_features: z.record(score.nullable()),
  contributions: z.record(finite.nullable()),
  confidence: z.record(z.unknown()), evidence: z.record(z.unknown()), lineage: z.record(z.unknown()),
  robustness: z.record(z.unknown()), change: z.record(z.unknown()),
  critical_movements: z.array(z.record(z.unknown())), flags: z.array(z.string()),
  direction: z.enum(["improving", "deteriorating", "stable", "unknown"]),
}).passthrough().superRefine((pulse, ctx) => {
  const add = (message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, message });
  if ((pulse.status === "complete") !== (pulse.health !== null)) add("Health solo está identificado en un resultado completo");
  if (pulse.health_min > pulse.health_max) add("Límites de identificación inválidos");
  const missing = pulsePillarKeys.filter((key) => pulse.pillars[key].score === null);
  if (missing.length !== pulse.missing_components.length || missing.some((key) => !pulse.missing_components.includes(key))) add("Componentes ausentes incoherentes");
  for (const key of pulsePillarKeys) {
    if (pulse.pillars[key].health_contribution !== pulse.contributions[key]) add("Contribuciones incoherentes con el resultado original");
    if (pulse.pillars[key].score === null && pulse.contributions[key] !== null) add("Un pilar ausente no tiene contribución");
  }
});
export const canonicalCashTruthSchema = z.object({
  schema_version: z.literal("1.0"), classification_version: text, facts_version: text,
  company_id: text, currency: z.literal("EUR"), as_of: pulseEnvelopeShape.as_of,
  summary: z.record(finite.nullable()), coverage: z.record(z.unknown()),
  classes: z.array(z.record(z.unknown())), evidence: z.record(z.unknown()),
  critical_movements: z.array(z.record(z.unknown())), flags: z.array(z.string()),
}).passthrough();
export type PulseResult = z.infer<typeof pulseSchema>;
