import { z } from "zod";

const text = z.string().min(1).max(5000);
const score = z.number().finite().min(0).max(100);
const count = z.number().int().nonnegative();
const amount = z.number().finite();
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}, "Fecha de calendario no válida");
const refs = z.array(text).max(50);
const trajectorySchema = z.enum(["improving", "deteriorating", "stable"]);
const dimensionKeySchema = z.enum(["momentum", "cash_generation", "resilience", "debt"]);
const cashCategorySchema = z.enum(["operating", "circulation", "support", "uncertain"]);
const dimensionsSchema = z.object({ momentum: score, cash_generation: score, resilience: score, debt: score }).strict();
const weightsSchema = z.object({ momentum: z.number().min(0).max(1), cash_generation: z.number().min(0).max(1), resilience: z.number().min(0).max(1), debt: z.number().min(0).max(1) }).strict().refine((weights) => Math.abs(Object.values(weights).reduce((sum, weight) => sum + weight, 0) - 1) < 1e-9, "Los pesos deben sumar 1");
const modelSchema = z.object({ version: text, provisional: z.boolean(), weights: weightsSchema });
const historySchema = z.object({ month: date, health_score: score.int() });
const driverSchema = z.object({ id: text, driver: text, affected_dimensions: z.array(dimensionKeySchema).min(1).max(4), impact: amount, direction: z.enum(["positive", "negative", "neutral"]), explanation: text, evidence_count: count, evidence_refs: refs });
const cashComponentSchema = z.object({ category: cashCategorySchema, label: text, gross_movement: amount.nonnegative(), net_amount: amount.nullable(), explanation: text, confidence: score.nullable(), evidence_refs: refs });
const cashTruthSchema = z.object({
  period: text,
  total_gross_movement: amount.nonnegative(),
  apparent_net: amount,
  components: z.array(cashComponentSchema).length(4),
  headline: text,
  explanation: text,
  confidence: score.nullable(),
  evidence_refs: refs,
  evidence_summary: z.array(text).max(20),
  correction: z.object({ apparent_operating: amount, identified_operating: amount, observed_support: amount, explanation: text }).nullable(),
  comparison: z.object({ company_id: z.string().regex(/^COMP_\d{4,10}$/), apparent_net: amount, operating_net: amount, support_net: amount, circulation_gross: amount.nonnegative(), explanation: text }).nullable(),
});
const timingSnapshotSchema = z.object({ period: text, payment_term: amount.nonnegative(), time_to_cash: amount.nonnegative(), delay: amount.nonnegative() });
const timingSideSchema = z.object({ counterparty_id: text, before: timingSnapshotSchema, after: timingSnapshotSchema, headline: text, explanation: text, methodology: text, confidence: score.nullable(), evidence_count: count, evidence_refs: refs });
const timeBorrowedSchema = z.object({ ar: timingSideSchema.nullable(), ap: timingSideSchema.nullable() });
const alertSchema = z.object({ id: text, severity: z.enum(["high", "medium", "low"]), title: text, explanation: text, period: text, evidence_refs: refs });
const transactionSchema = z.object({ kind: z.literal("transaction"), id: text, transaction_date: date, amount, category: cashCategorySchema, description: text });
const invoiceSchema = z.object({ kind: z.literal("invoice"), id: text, invoice: text, counterparty_id: text, side: z.enum(["ar", "ap"]), issue_date: date, due_date: date, payment_date: date.nullable(), amount: amount.nonnegative() });
const observationSchema = z.object({ kind: z.literal("observation"), id: text, metric: text, before: amount, after: amount, unit: z.enum(["EUR", "%", "days"]) });
const evidenceSchema = z.object({ id: text, title: text, period: text, explanation: text, confidence: score.nullable(), total_count: count, rows: z.array(z.discriminatedUnion("kind", [transactionSchema, invoiceSchema, observationSchema])).max(10) });
const scenarioKeySchema = z.enum(["customer_term", "collection_delay", "supplier_term", "internal_support"]);
const scenarioInputsSchema = z.object({ customer_term: amount, collection_delay: amount, supplier_term: amount, internal_support: amount }).strict();
const simulationInputSchema = z.object({ key: scenarioKeySchema, label: text, unit: z.enum(["days", "%"]), baseline: amount.nonnegative(), min: amount, max: amount, step: amount.positive(), explanation: text });
const scenarioSchema = z.object({ id: text, label: text, inputs: scenarioInputsSchema, health_score: score.int(), impacts: z.array(z.object({ key: scenarioKeySchema, label: text, points: amount })).max(4), explanation: text });
const simulationSchema = z.object({ inputs: z.array(simulationInputSchema).length(4), scenarios: z.array(scenarioSchema).max(1000), example_id: text.nullable(), methodology: text });

export const companyDetailSchema = z.object({
  schema_version: z.literal("2.0"),
  source: z.enum(["generated", "fixture"]),
  company_id: z.string().regex(/^COMP_\d{4,10}$/),
  group_id: text,
  as_of: date,
  currency: z.literal("EUR"),
  health_score: score.int(),
  dimensions: dimensionsSchema,
  health_score_model: modelSchema,
  assessment: text,
  confidence: score.nullable(),
  trajectory: trajectorySchema,
  summary: text,
  history: z.array(historySchema).max(24),
  drivers_period: text,
  drivers: z.array(driverSchema).max(20),
  cash_truth: cashTruthSchema,
  time_borrowed: timeBorrowedSchema,
  alerts: z.array(alertSchema).max(5),
  evidence: z.array(evidenceSchema).max(50),
  simulation: simulationSchema,
}).strict().superRefine((company, ctx) => {
  const issue = (message: string, path: (string | number)[]) => ctx.addIssue({ code: z.ZodIssueCode.custom, message, path });
  const unique = (values: string[], path: (string | number)[]) => { if (new Set(values).size !== values.length) issue("Identificadores duplicados", path); };
  unique(company.evidence.map((group) => group.id), ["evidence"]);
  unique(company.drivers.map((driver) => driver.id), ["drivers"]);
  unique(company.alerts.map((alert) => alert.id), ["alerts"]);
  unique(company.cash_truth.components.map((component) => component.category), ["cash_truth", "components"]);
  unique(company.simulation.inputs.map((input) => input.key), ["simulation", "inputs"]);
  unique(company.simulation.scenarios.map((scenario) => scenario.id), ["simulation", "scenarios"]);
  const evidenceIds = new Set(company.evidence.map((group) => group.id));
  const explanations = [...company.drivers, ...company.alerts, company.cash_truth, ...company.cash_truth.components, company.time_borrowed.ar, company.time_borrowed.ap];
  if (explanations.some((entry) => entry?.evidence_refs.some((ref) => !evidenceIds.has(ref)))) issue("Referencia de evidencia inexistente", ["evidence"]);
  company.history.forEach((point, index) => {
    if (point.month > company.as_of || (index > 0 && point.month <= company.history[index - 1].month)) issue("El histórico debe estar ordenado y no superar la fecha de corte", ["history", index]);
  });
  if (company.history.length && company.history.at(-1)?.health_score !== company.health_score) issue("El último valor debe coincidir con el Health Score actual", ["history"]);
  company.evidence.forEach((group, index) => {
    unique(group.rows.map((row) => row.id), ["evidence", index, "rows"]);
    if (group.rows.length > group.total_count) issue("La muestra supera el conjunto declarado", ["evidence", index]);
    if (group.rows.some((row) => row.kind === "invoice" && (row.due_date < row.issue_date || (row.payment_date !== null && row.payment_date < row.issue_date)))) issue("Fechas de factura incoherentes", ["evidence", index]);
  });
  company.simulation.inputs.forEach((input, index) => {
    if (input.min > 0 || input.max < 0 || input.min > input.max || input.baseline + input.min < 0) issue("Rango de ajustes no válido", ["simulation", "inputs", index]);
  });
  const combinations = company.simulation.scenarios.map((scenario) => company.simulation.inputs.map((input) => scenario.inputs[input.key]).join("|"));
  unique(combinations, ["simulation", "scenarios"]);
  company.simulation.scenarios.forEach((scenario, index) => {
    unique(scenario.impacts.map((impact) => impact.key), ["simulation", "scenarios", index, "impacts"]);
    for (const input of company.simulation.inputs) {
      const value = scenario.inputs[input.key];
      if (value < input.min || value > input.max || Math.abs(value / input.step - Math.round(value / input.step)) > 1e-8) issue("Ajuste fuera del rango o paso permitido", ["simulation", "scenarios", index, "inputs", input.key]);
    }
    if (Object.values(scenario.inputs).every((value) => value === 0) && scenario.health_score !== company.health_score) issue("El escenario sin ajustes debe coincidir con el estado actual", ["simulation", "scenarios", index]);
  });
  if (company.simulation.example_id !== null && !company.simulation.scenarios.some((scenario) => scenario.id === company.simulation.example_id)) issue("El escenario de ejemplo no existe", ["simulation", "example_id"]);
});

export type CompanyDetail = z.infer<typeof companyDetailSchema>;
export type Trajectory = z.infer<typeof trajectorySchema>;
export type DimensionKey = z.infer<typeof dimensionKeySchema>;
export type HealthDimensions = z.infer<typeof dimensionsSchema>;
export type HealthScoreWeights = Readonly<z.infer<typeof weightsSchema>>;
export type HealthScoreModel = z.infer<typeof modelSchema>;
export type HistoryPoint = z.infer<typeof historySchema>;
export type CashCategory = z.infer<typeof cashCategorySchema>;
export type CashTruth = z.infer<typeof cashTruthSchema>;
export type TimingSnapshot = z.infer<typeof timingSnapshotSchema>;
export type TimingSide = z.infer<typeof timingSideSchema>;
export type TimeBorrowed = z.infer<typeof timeBorrowedSchema>;
export type CompanyAlert = z.infer<typeof alertSchema>;
export type EvidenceRef = string;
export type EvidenceGroup = z.infer<typeof evidenceSchema>;
export type TransactionEvidence = z.infer<typeof transactionSchema>;
export type InvoiceEvidence = z.infer<typeof invoiceSchema>;
export type ObservationEvidence = z.infer<typeof observationSchema>;
export type ScenarioKey = z.infer<typeof scenarioKeySchema>;
export type ScenarioInputs = z.infer<typeof scenarioInputsSchema>;
export type Simulation = z.infer<typeof simulationSchema>;
