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
const cashAccountSchema = z.object({
  account_id: text,
  label: text,
  bank_name: text.nullable(),
  currency: z.literal("EUR"),
  ownership: z.enum(["company", "group_company", "external", "unknown"]),
  owner_company_id: z.string().regex(/^COMP_\d{4,10}$/).nullable(),
  owner_group_id: text.nullable(),
  ownership_source: text.nullable(),
  confidence: score.nullable(),
}).strict();
const transferLegSchema = z.object({ evidence_id: text, transaction_id: text }).strict();
const accountTransferSchema = z.object({
  id: text,
  kind: z.enum(["own_transfer", "intragroup_transfer", "external_transfer", "unresolved"]),
  from_account_id: text.nullable(),
  to_account_id: text.nullable(),
  date,
  amount: amount.positive(),
  gross_movement: amount.nonnegative(),
  company_net_amount: amount.nullable(),
  category: cashCategorySchema,
  match_status: z.enum(["matched", "partial", "unmatched"]),
  debit: transferLegSchema.nullable(),
  credit: transferLegSchema.nullable(),
  explanation: text,
  confidence: score.nullable(),
}).strict();
const accountFlowsSchema = z.object({
  period: text,
  explanation: text,
  accounts: z.array(cashAccountSchema).max(50),
  transfers: z.array(accountTransferSchema).max(10),
}).strict();
const ownAccountCirculationSchema = z.object({
  transferred_amount: amount.nonnegative(),
  transfer_count: count,
  explanation: text,
  confidence: score.nullable(),
  evidence_refs: refs,
}).strict();
const cashTruthSchema = z.object({
  period: text,
  total_gross_movement: amount.nonnegative(),
  account_flows: accountFlowsSchema.nullable().optional(),
  own_account_circulation: ownAccountCirculationSchema.nullable().optional(),
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
const transactionSchema = z.object({ kind: z.literal("transaction"), id: text, account_id: text.nullable().optional(), transaction_date: date, amount, category: cashCategorySchema, description: text });
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
  const explanations = [...company.drivers, ...company.alerts, company.cash_truth, company.cash_truth.own_account_circulation, ...company.cash_truth.components, company.time_borrowed.ar, company.time_borrowed.ap];
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
  const flows = company.cash_truth.account_flows;
  if (flows) {
    const root = ["cash_truth", "account_flows"];
    unique(flows.accounts.map((account) => account.account_id), [...root, "accounts"]);
    unique(flows.transfers.map((transfer) => transfer.id), [...root, "transfers"]);
    const accounts = new Map(flows.accounts.map((account) => [account.account_id, account]));
    flows.accounts.forEach((account, index) => {
      const location = [...root, "accounts", index];
      if (account.ownership === "unknown") {
        if (account.owner_company_id !== null || account.owner_group_id !== null) issue("Titularidad no confirmada: no atribuir empresa ni grupo", location);
      } else {
        if (!account.owner_company_id || !account.owner_group_id || !account.ownership_source) issue("La titularidad identificada necesita empresa, grupo y fuente", location);
        if (account.ownership === "company" && (account.owner_company_id !== company.company_id || account.owner_group_id !== company.group_id)) issue("La cuenta propia debe pertenecer a la empresa analizada", location);
        if (account.ownership === "group_company" && (account.owner_company_id === company.company_id || account.owner_group_id !== company.group_id)) issue("Otra sociedad del grupo debe ser una empresa distinta del mismo grupo", location);
        if (account.ownership === "external" && (account.owner_company_id === company.company_id || account.owner_group_id === company.group_id)) issue("Un tercero no puede ser la empresa ni otra sociedad del grupo", location);
      }
    });
    company.evidence.forEach((group, index) => {
      if (group.rows.some((row) => row.kind === "transaction" && row.account_id != null && !accounts.has(row.account_id))) issue("Cuenta de evidencia no incluida en el registro", ["evidence", index]);
    });
    const usedLegs = new Set<string>();
    flows.transfers.forEach((transfer, index) => {
      const location = [...root, "transfers", index];
      const from = transfer.from_account_id ? accounts.get(transfer.from_account_id) : undefined;
      const to = transfer.to_account_id ? accounts.get(transfer.to_account_id) : undefined;
      if ((transfer.from_account_id && !from) || (transfer.to_account_id && !to)) issue("Referencia a una cuenta inexistente", location);
      if (transfer.from_account_id !== null && transfer.from_account_id === transfer.to_account_id) issue("Origen y destino deben ser cuentas distintas", location);
      if (transfer.date > company.as_of) issue("La transferencia supera la fecha de corte", location);
      const ownPair = from?.ownership === "company" && to?.ownership === "company";
      const crosses = (ownership: "group_company" | "external") => (from?.ownership === "company" && to?.ownership === ownership) || (to?.ownership === "company" && from?.ownership === ownership);
      if (from?.ownership !== "company" && to?.ownership !== "company") issue("La transferencia debe incluir una cuenta de la empresa analizada", location);
      if (transfer.kind === "own_transfer" && !ownPair) issue("Un traslado propio necesita dos cuentas de la misma empresa", location);
      if (transfer.kind === "intragroup_transfer" && !crosses("group_company")) issue("La transferencia intragrupo necesita otra sociedad identificada del grupo", location);
      if (transfer.kind === "external_transfer" && !crosses("external")) issue("La transferencia externa necesita un tercero identificado", location);
      if (transfer.kind === "unresolved" && (transfer.category !== "uncertain" || transfer.company_net_amount !== null)) issue("Un origen no resuelto no permite atribuir finalidad ni neto", location);
      if (transfer.kind === "own_transfer") {
        const complete = transfer.match_status === "matched";
        if (transfer.category !== (complete ? "circulation" : "uncertain") || transfer.company_net_amount !== (complete ? 0 : null)) issue("Solo un traslado propio emparejado permite circulación con neto cero", location);
      }
      const resolveLeg = (leg: z.infer<typeof transferLegSchema> | null, accountId: string | null, sign: number) => {
        if (!leg) return undefined;
        const row = company.evidence.find((group) => group.id === leg.evidence_id)?.rows.find((item) => item.id === leg.transaction_id);
        const key = `${accountId ?? ""}/${leg.transaction_id}`;
        if (usedLegs.has(key)) issue("No reutilizar un movimiento en varias transferencias", location);
        usedLegs.add(key);
        if (!row || row.kind !== "transaction" || !accountId || row.account_id !== accountId || row.transaction_date > company.as_of || Math.sign(row.amount) !== sign || Math.abs(Math.abs(row.amount) - transfer.amount) > 0.01) {
          issue("La evidencia del tramo debe corresponder a cuenta, signo e importe", location);
          return undefined;
        }
        return row;
      };
      const debit = resolveLeg(transfer.debit, transfer.from_account_id, -1);
      const credit = resolveLeg(transfer.credit, transfer.to_account_id, 1);
      if (transfer.match_status === "matched" && (!debit || !credit)) issue("Emparejado requiere evidencia de salida y entrada", location);
      if (transfer.match_status === "partial" && Number(Boolean(debit)) + Number(Boolean(credit)) !== 1) issue("Parcial requiere exactamente un tramo observado", location);
      if (transfer.match_status === "unmatched" && debit && credit) issue("Dos tramos declarados requieren un estado de emparejamiento coherente", location);
      const companyLegs = [from?.ownership === "company" ? debit : undefined, to?.ownership === "company" ? credit : undefined].filter((row) => row !== undefined);
      if (!companyLegs.length) issue("Se necesita al menos un movimiento observado de la empresa", location);
      if (companyLegs.some((row) => row.category !== transfer.category)) issue("La categoría debe coincidir con la evidencia de la empresa", location);
      if (Math.abs(companyLegs.reduce((sum, row) => sum + Math.abs(row.amount), 0) - transfer.gross_movement) > 0.01) issue("El bruto debe corresponder a los tramos observados de la empresa, sin duplicar otras sociedades", location);
      if (transfer.company_net_amount !== null && Math.abs(companyLegs.reduce((sum, row) => sum + row.amount, 0) - transfer.company_net_amount) > 0.01) issue("El neto suministrado no coincide con los tramos observados de la empresa", location);
    });
  }
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
export type CashAccount = z.infer<typeof cashAccountSchema>;
export type AccountTransfer = z.infer<typeof accountTransferSchema>;
export type AccountFlows = z.infer<typeof accountFlowsSchema>;
export type TransactionEvidenceRef = z.infer<typeof transferLegSchema>;
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
