import { z } from "zod";

const finite = z.number().finite();
const score = finite.min(0).max(100);
const text = z.string().min(1);
export const pulseStatusSchema = z.enum(["complete", "complete_verified", "complete_bounded", "partial", "insufficient_evidence"]);
export const isCompleteStatus = (status: z.infer<typeof pulseStatusSchema>) => ["complete", "complete_verified", "complete_bounded"].includes(status);
export const healthEvidenceSchema = z.enum(["verified", "bounded", "partial", "unknown"]);
export const identifiedRangeSchema = z.object({ min: score, max: score, kind: z.literal("identification_bounds_not_confidence_interval") }).strict().refine((range) => range.min <= range.max, "Rango de identificación invertido");
export const identificationFields = { identified_range: identifiedRangeSchema.nullable().optional(), health_evidence: healthEvidenceSchema.optional() };
export function identificationIssue(method: string, item: {
  score_status: z.infer<typeof pulseStatusSchema>; health_score: number | null;
  identified_range?: z.infer<typeof identifiedRangeSchema> | null; health_evidence?: z.infer<typeof healthEvidenceSchema>;
}): string | null {
  if (isCompleteStatus(item.score_status) !== (item.health_score !== null)) return "Estado y Health incoherentes";
  if (method === "PulseFourPillars-v1.0") return ["complete", "partial", "insufficient_evidence"].includes(item.score_status) ? null : "Estado no disponible en v1.0";
  if (item.score_status === "complete" || item.identified_range === undefined || item.health_evidence === undefined) return "Falta contrato de identificación v1.0.1";
  const expected = { complete_verified: "verified", complete_bounded: "bounded", partial: "partial", insufficient_evidence: "unknown" }[item.score_status];
  if (item.health_evidence !== expected) return "Evidencia incompatible con el estado";
  if (item.health_score !== null && (!item.identified_range || item.health_score < item.identified_range.min || item.health_score > item.identified_range.max)) return "Health fuera del rango suministrado";
  return null;
}
export const pulseEnvelopeShape = {
  snapshot_id: z.string().regex(/^web-[a-f0-9]{64}$/),
  run_id: text,
  score_version: z.enum(["PulseFourPillars-v1.0", "PulseFourPillars-v1.0.1"]),
  classification_version: text,
  cleaning_version: text,
  facts_version: text,
  config_version: text,
  as_of: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  // This presentation is explicitly EUR-only; no implicit FX conversion.
  currency: z.literal("EUR"),
};
export const pulseEnvelopeSchema = z.object(pulseEnvelopeShape);
export type PulseEnvelope = z.infer<typeof pulseEnvelopeSchema>;
export const envelopeKeys = Object.keys(pulseEnvelopeShape) as (keyof typeof pulseEnvelopeShape)[];
const feature = z.object({ raw: finite.nullable(), score: score.nullable(), numerator: finite.nullable(), denominator: finite.nullable(), formula_id: text, anchors: z.unknown() }).passthrough();
const nullableRange = z.object({ min: finite.nullable(), max: finite.nullable() }).strict().superRefine((range, ctx) => {
  if ((range.min === null) !== (range.max === null) || (range.min !== null && range.max !== null && (range.min < 0 || range.min > range.max))) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Rango incompleto o invertido" });
});
const debtFields = {
  identified_score: score.nullable(), score_range: nullableRange,
  score_range_width: finite.nonnegative().nullable(), score_estimation: z.enum(["identified", "bounded_midpoint"]).nullable(),
  reason: text, evidence_status: healthEvidenceSchema, evidence_reason: text,
  identified_service: z.object({ debt_principal_paid: finite.nonnegative().nullable(), debt_interest_paid: finite.nonnegative().nullable(), verified_financing_fees: finite.nonnegative().nullable(), debt_service_paid: finite.nonnegative().nullable(), observed_months: z.number().int().min(0).max(6), required_months: z.literal(6), history_complete: z.boolean() }).strict(),
  // Identified service can supply a lower amount while the upper amount remains unknown.
  service_bounds: z.object({ min: finite.nonnegative().nullable(), max: finite.nonnegative().nullable() }).strict().refine((range) => range.max === null || (range.min !== null && range.min <= range.max), "Límite de servicio incoherente"), service_absence_verified: z.literal(false),
  uncertainty: z.object({ debt_possible_uncertain_outflows: finite.nonnegative().nullable(), debt_impossible_uncertain_outflows: finite.nonnegative().nullable(), debt_unresolved_uncertain_outflows: finite.nonnegative().nullable(), potentially_financial_uncertain_outflows: finite.nonnegative().nullable(), version: z.literal("debt-uncertainty-v1") }).passthrough(),
};
const debtContract = z.object(debtFields).passthrough();
const pillar = z.object({ score: score.nullable(), weight: finite.min(0).max(1), health_contribution: finite.nullable(), features: z.record(feature), ...z.object(debtFields).partial().shape }).passthrough();
export const pulsePillarKeys = ["generation", "momentum", "resilience", "debt_obligations"] as const;
export const pulseSchema = z.object({
  schema_version: z.literal("1.0"),
  run_id: text, score_version: pulseEnvelopeShape.score_version,
  classification_version: text, cleaning_version: text, facts_version: text, config_version: text,
  company_id: text, currency: z.literal("EUR"), as_of: pulseEnvelopeShape.as_of,
  status: pulseStatusSchema, health: score.nullable(),
  ...identificationFields,
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
  if (isCompleteStatus(pulse.status) !== (pulse.health !== null)) add("Health solo está identificado en un resultado completo");
  const patch = pulse.score_version === "PulseFourPillars-v1.0.1";
  if (pulse.config_version !== (patch ? "pulse-config-v1.0.1" : "pulse-config-v1")) add("Versión de configuración distinta del método");
  if (patch ? pulse.status === "complete" : !["complete", "partial"].includes(pulse.status)) add("Estado incompatible con la versión del motor");
  if (pulse.health_min > pulse.health_max) add("Límites de identificación inválidos");
  const missing = pulsePillarKeys.filter((key) => pulse.pillars[key].score === null);
  if (missing.length !== pulse.missing_components.length || missing.some((key) => !pulse.missing_components.includes(key))) add("Componentes ausentes incoherentes");
  for (const key of pulsePillarKeys) {
    if (pulse.pillars[key].health_contribution !== pulse.contributions[key]) add("Contribuciones incoherentes con el resultado original");
    if (pulse.pillars[key].score === null && pulse.contributions[key] !== null) add("Un pilar ausente no tiene contribución");
  }
  if (!patch && pulse.pillars.debt_obligations.evidence_status === "bounded") add("v1.0 no admite evidencia acotada");
  if (patch) {
    const result = debtContract.safeParse(pulse.pillars.debt_obligations);
    if (!result.success) add("Falta el contrato trazable de Debt v1.0.1");
    if (pulse.identified_range === undefined || pulse.health_evidence === undefined) add("Falta la identificación de Health v1.0.1");
    const expectedEvidence = { complete_verified: "verified", complete_bounded: "bounded", partial: "partial", insufficient_evidence: "unknown", complete: "verified" }[pulse.status];
    if (pulse.health_evidence !== expectedEvidence) add("Evidencia de Health incompatible con su estado");
    if (result.success) {
      const debt = result.data, point = pulse.pillars.debt_obligations.score;
      if (debt.reason !== debt.evidence_reason) add("Motivos de Debt incoherentes");
      if (debt.score_range.max !== null && debt.score_range.max > 100) add("Rango de Debt fuera de escala");
      if (point !== null && (debt.score_range.min === null || debt.score_range.max === null || point < debt.score_range.min || point > debt.score_range.max)) add("Debt fuera del rango suministrado");
      if (debt.evidence_status === "bounded" && (point === null || debt.score_estimation !== "bounded_midpoint")) add("Debt acotado requiere estimación explícita");
      if (debt.evidence_status === "verified" && (point === null || debt.score_estimation !== "identified")) add("Debt verificado requiere identificación explícita");
      if (["partial", "unknown"].includes(debt.evidence_status) && point !== null) add("Debt no identificado debe seguir null");
      if (isCompleteStatus(pulse.status) && debt.evidence_status !== expectedEvidence) add("Health no puede ocultar la evidencia de Debt");
    }
    if (pulse.health !== null && pulse.identified_range && (pulse.health_min !== pulse.identified_range.min || pulse.health_max !== pulse.identified_range.max)) add("Límites completos de Health incoherentes");
    if (pulse.health !== null && (!pulse.identified_range || pulse.health < pulse.identified_range.min || pulse.health > pulse.identified_range.max)) add("Health fuera del rango suministrado");
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
