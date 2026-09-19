import { z } from "zod";
import { pulseEnvelopeShape, pulseStatusSchema, identificationFields, identificationIssue, compositionFields } from "./pulse";

const text = z.string().min(1).max(5000);
const id = z.string().min(1).max(100);
const companyId = z.string().regex(/^COMP_\d{4,10}$/);
const score = z.number().finite().min(0).max(100);
const amount = z.number().finite();
const count = z.number().int().nonnegative();
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}, "Fecha no válida");
const refs = z.array(id).max(50);
const companyRefs = z.array(companyId).max(50);
const severity = z.enum(["high", "medium", "low"]);
const relationStatus = z.enum(["identified", "candidate", "unknown"]);
const relationKind = z.enum(["support", "transfer", "cash_pooling", "treasury_circulation", "commercial", "unknown"]);
const outlookSchema = z.object({ status: z.enum(["available", "insufficient"]), horizon: text, summary: text, funding_need: amount.nonnegative().nullable(), confidence: score.nullable(), evidence_refs: refs });
const memberSchema = z.object({
  company_id: companyId,
  health_score: score.nullable(),
  ...compositionFields,
  dimensions: z.object({ momentum: score.nullable(), cash_generation: score.nullable(), resilience: score.nullable(), debt: score.nullable() }),
  trajectory: z.enum(["improving", "stable", "deteriorating"]).nullable(),
  role: z.enum(["provider", "receiver", "both", "none_identified", "unknown"]),
  available_liquidity: amount.nonnegative().nullable(),
  identified_debt: amount.nonnegative().nullable(),
  obligations_due: amount.nonnegative().nullable(),
  cash_generation_net: amount.nullable(),
  internal_received: amount.nonnegative().nullable(),
  internal_provided: amount.nonnegative().nullable(),
  confidence: score.nullable(),
  attention: z.enum(["high", "medium", "low", "unknown"]),
  score_status: pulseStatusSchema,
  ...identificationFields,
  missing_components: z.array(text),
  summary: text,
  outlook: outlookSchema,
  evidence_refs: refs,
});
const metricSchema = z.object({ value: amount.nonnegative().nullable(), covered_company_ids: companyRefs, explanation: text, evidence_refs: refs });
const insightSchema = z.object({ id, title: text, explanation: text, severity, company_refs: companyRefs, relation_refs: refs, evidence_refs: refs });
const alertSchema = insightSchema.extend({ period: text });
const changeSchema = insightSchema.extend({ date });
const relationSchema = z.object({
  id,
  from_company_id: companyId.nullable(),
  to_company_id: companyId.nullable(),
  kind: relationKind,
  status: relationStatus,
  volume: amount.nonnegative().nullable(),
  transfer_count: count.nullable(),
  period: text,
  recurrence: text,
  change: z.enum(["new", "increasing", "stable", "decreasing", "unknown"]),
  first_seen: date.nullable(),
  last_seen: date.nullable(),
  explanation: text,
  confidence: score.nullable(),
  evidence_refs: refs,
});
const transactionSchema = z.object({ kind: z.literal("transaction"), id, company_id: companyId, counterparty_company_id: companyId.nullable(), transaction_date: date, amount, category: text, description: text });
const invoiceSchema = z.object({ kind: z.literal("invoice"), id, invoice: id, issuer_company_id: companyId, customer_company_id: companyId, issue_date: date, due_date: date, payment_date: date.nullable(), amount: amount.nonnegative() });
const metricRowSchema = z.object({ kind: z.literal("metric"), id, company_id: companyId, metric: text, value: amount.nullable(), unit: z.enum(["EUR", "%", "days", "score"]), period: text, source: text });
const evidenceSchema = z.object({ id, title: text, period: text, explanation: text, confidence: score.nullable(), total_count: count, rows: z.array(z.discriminatedUnion("kind", [transactionSchema, invoiceSchema, metricRowSchema])).max(10) });
const recommendationSchema = z.object({
  id,
  type: z.enum(["recurring_support", "liquidity_distribution", "increasing_dependency", "funding_structure", "concentration", "stress_liquidity", "insufficient_evidence"]),
  priority: severity,
  title: text,
  explanation: text,
  period: text,
  confidence: score.nullable(),
  signals: z.array(z.object({ source: z.enum(["health", "momentum", "resilience", "cash_truth", "network", "liquidity", "obligations", "outlook", "concentration", "confidence"]), observation: text })).min(1).max(12),
  review_steps: z.array(text).min(1).max(10),
  constraints: z.array(text).min(1).max(10),
  company_refs: companyRefs,
  relation_refs: refs,
  evidence_refs: refs,
});

export const groupDetailSchema = z.object({
  schema_version: z.literal("2.0"),
  ...pulseEnvelopeShape,
  composition_version: z.literal("operating-extended-health-v1").optional(),
  health_score: z.null(),
  status: z.literal("insufficient_evidence"),
  source: z.enum(["generated", "fixture"]),
  group_id: z.string().regex(/^GROUP_\d{4,10}$/),
  as_of: date,
  period: text,
  currency: z.literal("EUR"),
  summary: text,
  coverage: z.object({ known_company_count: count.nullable(), confidence: score.nullable(), explanation: text }),
  available_liquidity: metricSchema,
  identified_debt: metricSchema,
  obligations: metricSchema.extend({ horizon: text }),
  limitations: z.array(text).min(1).max(15),
  members: z.array(memberSchema).max(50),
  insights: z.array(insightSchema).max(15),
  alerts: z.array(alertSchema).max(20),
  concentration: z.array(insightSchema).max(10),
  recent_changes: z.array(changeSchema).max(15),
  relations: z.array(relationSchema).max(200),
  recommendations: z.array(recommendationSchema).max(30),
  evidence: z.array(evidenceSchema).max(50),
}).strict().superRefine((group, ctx) => {
  const issue = (message: string, path: (string | number)[]) => ctx.addIssue({ code: z.ZodIssueCode.custom, message, path });
  if (group.score_version === "PulseFourPillars-v1.1" && group.composition_version !== "operating-extended-health-v1") issue("Falta versión de composición", ["composition_version"]);
  const unique = (ids: string[], path: (string | number)[]) => { if (new Set(ids).size !== ids.length) issue("Identificadores duplicados", path); };
  unique(group.members.map((member) => member.company_id), ["members"]);
  for (const key of ["relations", "recommendations", "evidence", "insights", "alerts", "concentration", "recent_changes"] as const) unique(group[key].map((item) => item.id), [key]);
  const members = new Set(group.members.map((member) => member.company_id));
  const relations = new Set(group.relations.map((relation) => relation.id));
  const evidence = new Map(group.evidence.map((item) => [item.id, item]));
  const checkCompanies = (ids: string[], path: (string | number)[]) => { if (ids.some((value) => !members.has(value))) issue("Sociedad no incluida en el grupo observado", path); };
  const checkEvidence = (ids: string[], path: (string | number)[]) => { if (ids.some((value) => !evidence.has(value))) issue("Referencia de evidencia inexistente", path); };
  if (group.coverage.known_company_count !== null && group.coverage.known_company_count < group.members.length) issue("La cobertura no puede declarar menos sociedades que las observadas", ["coverage"]);
  for (const key of ["available_liquidity", "identified_debt", "obligations"] as const) {
    const metric = group[key];
    checkCompanies(metric.covered_company_ids, [key, "covered_company_ids"]);
    unique(metric.covered_company_ids, [key, "covered_company_ids"]);
    checkEvidence(metric.evidence_refs, [key, "evidence_refs"]);
    if (metric.value !== null && !metric.covered_company_ids.length) issue("Una magnitud disponible debe declarar las sociedades cubiertas", [key]);
  }
  group.members.forEach((member, index) => {
    const invalid = identificationIssue(group.score_version, member);
    if (invalid) issue(invalid, ["members", index]);
    if (group.score_version === "PulseFourPillars-v1.1") {
      const operatingValid = [member.dimensions.cash_generation, member.dimensions.momentum, member.dimensions.resilience].every((value) => value !== null);
      const expectedLevel = !operatingValid ? null : member.dimensions.debt === null ? "operating_only" : member.health_evidence === "bounded" ? "extended_bounded" : "extended_verified";
      if (group.composition_version !== "operating-extended-health-v1" || member.composition_version !== group.composition_version || member.operating_health === undefined || member.extended_health === undefined || member.health_level === undefined || member.insights_available === undefined || member.missing_modules === undefined) issue("Falta composición Operating/Extended", ["members", index]);
      if ((member.operating_health !== null) !== operatingValid || member.extended_health !== member.health_score || member.health_level !== expectedLevel) issue("Disponibilidad Operating/Extended incoherente", ["members", index]);
    }
    checkEvidence(member.evidence_refs, ["members", index]);
    checkEvidence(member.outlook.evidence_refs, ["members", index, "outlook"]);
    if (member.outlook.status === "insufficient" && member.outlook.funding_need !== null) issue("Sin evidencia de perspectiva no se puede afirmar una necesidad de caja", ["members", index, "outlook"]);
  });
  for (const key of ["insights", "alerts", "concentration", "recent_changes", "recommendations"] as const) {
    group[key].forEach((item, index) => {
      checkCompanies(item.company_refs, [key, index, "company_refs"]);
      checkEvidence(item.evidence_refs, [key, index, "evidence_refs"]);
      if (item.relation_refs.some((ref) => !relations.has(ref))) issue("Relación referenciada inexistente", [key, index, "relation_refs"]);
    });
  }
  group.relations.forEach((relation, index) => {
    const endpoints = [relation.from_company_id, relation.to_company_id].filter((value): value is string => value !== null);
    checkCompanies(endpoints, ["relations", index]);
    checkEvidence(relation.evidence_refs, ["relations", index, "evidence_refs"]);
    if (!endpoints.length || (endpoints.length === 2 && endpoints[0] === endpoints[1])) issue("La relación necesita al menos una sociedad y no puede ser un autoenlace", ["relations", index]);
    const linkedRows = relation.evidence_refs.flatMap((ref) => evidence.get(ref)?.rows ?? []);
    const hasLinkedEvidence = linkedRows.some((row) => row.kind === "transaction" ? (row.company_id === relation.from_company_id && row.counterparty_company_id === relation.to_company_id && row.amount < 0) || (row.company_id === relation.to_company_id && row.counterparty_company_id === relation.from_company_id && row.amount > 0) : row.kind === "invoice" && relation.kind === "commercial" && row.issuer_company_id === relation.to_company_id && row.customer_company_id === relation.from_company_id);
    if (relation.status === "identified" && (endpoints.length !== 2 || relation.kind === "unknown" || !hasLinkedEvidence)) issue("Una relación identificada requiere extremos, tipo y evidencia que conecte esas sociedades", ["relations", index]);
    if ((relation.first_seen && relation.first_seen > group.as_of) || (relation.last_seen && relation.last_seen > group.as_of) || (relation.first_seen && relation.last_seen && relation.first_seen > relation.last_seen)) issue("Fechas de observación incoherentes", ["relations", index]);
  });
  group.recent_changes.forEach((item, index) => { if (item.date > group.as_of) issue("Un cambio observado no puede superar la fecha de corte", ["recent_changes", index]); });
  group.evidence.forEach((item, index) => {
    unique(item.rows.map((row) => row.id), ["evidence", index, "rows"]);
    if (item.rows.length > item.total_count) issue("La muestra supera el conjunto declarado", ["evidence", index]);
    for (const row of item.rows) {
      checkCompanies(row.kind === "invoice" ? [row.issuer_company_id, row.customer_company_id] : [row.company_id, ...(row.kind === "transaction" && row.counterparty_company_id ? [row.counterparty_company_id] : [])], ["evidence", index]);
      if (row.kind === "transaction" && row.transaction_date > group.as_of) issue("Un movimiento observado no puede ser futuro", ["evidence", index]);
      if (row.kind === "invoice" && (row.issue_date > group.as_of || row.due_date < row.issue_date || (row.payment_date && (row.payment_date < row.issue_date || row.payment_date > group.as_of)))) issue("Fechas de factura incoherentes", ["evidence", index]);
    }
  });
});

export type GroupDetail = z.infer<typeof groupDetailSchema>;
export type GroupMember = z.infer<typeof memberSchema>;
export type GroupRelation = z.infer<typeof relationSchema>;
export type GroupRecommendation = z.infer<typeof recommendationSchema>;
export type GroupEvidence = z.infer<typeof evidenceSchema>;
export type GroupMetric = z.infer<typeof metricSchema>;
export type GroupInsight = z.infer<typeof insightSchema>;
export type GroupView = "overview" | "network" | "recommendations";
