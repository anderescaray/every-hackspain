import type {
  CashTruth,
  CompanyDetail,
  EvidenceGroup,
  HealthDimensions,
  HistoryPoint,
  InvoiceEvidence,
  Simulation,
  TimingSide,
  TransactionEvidence,
} from "../../types/companyDetail";
import { HEALTH_SCORE_MODEL } from "../../lib/healthScore";

const cashPeriod = "sep 2025 – ago 2026";
const beforePeriod = "ene – mar 2026";
const afterPeriod = "jun – ago 2026";

function scoreSnapshot(health_score: number, dimensions: HealthDimensions, scores: number[]) {
  const history: HistoryPoint[] = scores.map((value, index) => ({
    month: new Date(Date.UTC(2024, 8 + index, 1)).toISOString().slice(0, 10),
    health_score: index === scores.length - 1 ? health_score : value,
  }));
  return { health_score, dimensions, health_score_model: HEALTH_SCORE_MODEL, history };
}

function dateAfter(date: string, days: number): string {
  const result = new Date(`${date}T00:00:00Z`);
  result.setUTCDate(result.getUTCDate() + days);
  return result.toISOString().slice(0, 10);
}

function invoices(side: "ar" | "ap", counterparty: string, terms: number[], delays: number[]): InvoiceEvidence[] {
  return terms.map((term, index) => {
    const issueDate = index < 3 ? "2026-01-01" : "2026-05-01";
    const dueDate = dateAfter(issueDate, term);
    return {
      kind: "invoice",
      id: `${side}-invoice-${index + 1}`,
      invoice: `DEMO-${side.toUpperCase()}-${String(index + 1).padStart(3, "0")}`,
      counterparty_id: counterparty,
      side,
      issue_date: issueDate,
      due_date: dueDate,
      payment_date: dateAfter(dueDate, delays[index]),
      amount: 18000 + index * 2500,
    };
  });
}

function timing(
  side: "ar" | "ap",
  counterparty: string,
  before: [number, number, number],
  after: [number, number, number],
  headline: string,
  explanation: string,
): TimingSide {
  return {
    counterparty_id: counterparty,
    before: { period: beforePeriod, payment_term: before[0], time_to_cash: before[1], delay: before[2] },
    after: { period: afterPeriod, payment_term: after[0], time_to_cash: after[1], delay: after[2] },
    headline,
    explanation,
    methodology: "Son medianas independientes en días naturales, agrupadas por fecha de pago. No son relojes que se sumen: la mediana del plazo más la del retraso puede diferir de la mediana del tiempo hasta cobro. Las facturas de ejemplo no reproducen el conjunto completo.",
    confidence: 88,
    evidence_count: 48,
    evidence_refs: [`${side}-timing`],
  };
}

function timingEvidence(ar: TimingSide, ap: TimingSide): EvidenceGroup[] {
  return [ar, ap].map((item, index) => {
    const side = index === 0 ? "ar" : "ap";
    const old = item.before;
    const current = item.after;
    const terms = [old.payment_term, old.payment_term - 1, old.payment_term + 1, current.payment_term, current.payment_term, current.payment_term];
    const delays = [Math.max(0, old.delay - 1), old.delay, old.delay + 1, current.delay, current.delay, current.delay];
    return {
      id: `${side}-timing`,
      title: side === "ar" ? "Plazos y cobros de clientes" : "Plazos y pagos a proveedores",
      period: `${beforePeriod} frente a ${afterPeriod}`,
      explanation: `${item.explanation} ${item.methodology}`,
      confidence: item.confidence,
      total_count: item.evidence_count,
      rows: invoices(side, item.counterparty_id, terms, delays),
    };
  });
}

function simulation(ar: TimingSide, ap: TimingSide, exampleScore: number, lessSupportScore: number): Simulation {
  return {
    inputs: [
      { key: "customer_term", label: "Plazo acordado con clientes", unit: "days", baseline: ar.after.payment_term, min: -30, max: 30, step: 1, explanation: "Un plazo menor reduce mecánicamente el tiempo financiado a clientes." },
      { key: "collection_delay", label: "Retraso en los cobros", unit: "days", baseline: ar.after.delay, min: -ar.after.delay, max: 30, step: 1, explanation: "Un menor retraso acorta mecánicamente el ciclo de cobro." },
      { key: "supplier_term", label: "Plazo acordado con proveedores", unit: "days", baseline: ap.after.payment_term, min: -30, max: 30, step: 1, explanation: "Un plazo mayor aplaza mecánicamente la necesidad de caja." },
      { key: "internal_support", label: "Apoyo intragrupo", unit: "%", baseline: 100, min: -50, max: 50, step: 1, explanation: "Menos apoyo reduce la liquidez disponible en este ejemplo; no demuestra autosuficiencia." },
    ],
    scenarios: [
      { id: "terms-example", label: "Menos plazo a clientes y más plazo de proveedores", inputs: { customer_term: -15, collection_delay: ar.after.delay === 0 ? 0 : -3, supplier_term: 7, internal_support: -10 }, health_score: exampleScore, impacts: [
        { key: "customer_term", label: "Plazo acordado con clientes", points: 4.5 },
        { key: "collection_delay", label: "Retraso en los cobros", points: ar.after.delay === 0 ? 0 : 1.5 },
        { key: "supplier_term", label: "Plazo acordado con proveedores", points: 1.4 },
        { key: "internal_support", label: "Apoyo intragrupo", points: -1.4 },
      ], explanation: "Resultado ficticio precalculado para esta combinación exacta. No representa un resultado futuro garantizado." },
      { id: "less-support", label: "Reducción del apoyo intragrupo", inputs: { customer_term: 0, collection_delay: 0, supplier_term: 0, internal_support: -10 }, health_score: lessSupportScore, impacts: [{ key: "internal_support", label: "Apoyo intragrupo", points: -1.4 }], explanation: "En este ejemplo, retirar apoyo reduce la liquidez disponible; no demuestra autosuficiencia." },
    ],
    example_id: "terms-example",
    methodology: "Resultados de ejemplo precalculados y suministrados por el contrato. El frontend solo selecciona una coincidencia exacta; no calcula puntuaciones ni interpola resultados. Las contribuciones pueden diferir de la variación final por el redondeo aplicado por el proveedor de datos. No se modifica la cobertura de datos.",
  };
}

const mainAr = timing("ar", "COUNTERPARTY_02340", [75, 85, 10], [90, 97, 7], "Más plazo concedido. La caja tarda más en llegar.", "El plazo a clientes aumentó 15 días. La reducción del retraso solo compensa parte del tiempo adicional financiado. No se deduce el motivo del cambio.");
const mainAp = timing("ap", "COUNTERPARTY_04821", [60, 64, 4], [45, 48, 3], "Menos plazo recibido. La caja se necesita antes.", "El plazo concedido por proveedores se redujo 15 días. La empresa necesita caja antes para estas facturas; no se identifica la causa del cambio.");
const punctualAr = timing("ar", "COUNTERPARTY_06105", [62, 81, 20], [102, 102, 0], "Más puntualidad. Más tiempo hasta convertir la venta en caja.", "El cliente ahora paga puntual, pero la empresa tarda más en convertir la venta en caja porque ha ampliado el plazo concedido. Esto describe los tiempos, no la calidad del cliente ni las causas del cambio.");
const comparisonAr = timing("ar", "COUNTERPARTY_03116", [75, 84, 9], [65, 69, 4], "Menos plazo concedido. La caja llega antes.", "Se redujeron tanto el plazo a clientes como el retraso en el cobro. Los tiempos de las facturas no permiten deducir el motivo.");
const comparisonAp = timing("ap", "COUNTERPARTY_03921", [50, 52, 2], [57, 59, 2], "Más plazo recibido. La caja se necesita después.", "El plazo de proveedores aumentó 7 días y el retraso de pago no cambió. Esto no identifica por qué cambiaron las condiciones.");

const mainTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-TX-001", account_id: "ACCOUNT_0356_A", transaction_date: "2026-08-03", amount: -2500000, category: "circulation", description: "Ciclo de tesorería representativo: salida" },
  { kind: "transaction", id: "DEMO-TX-002", account_id: "ACCOUNT_0356_B", transaction_date: "2026-08-04", amount: 2500000, category: "circulation", description: "Ciclo de tesorería representativo: entrada asociada" },
  { kind: "transaction", id: "DEMO-TX-003", account_id: "ACCOUNT_0356_A", transaction_date: "2026-08-05", amount: 180000, category: "operating", description: "Cobros de clientes identificados" },
  { kind: "transaction", id: "DEMO-TX-004", account_id: "ACCOUNT_0356_A", transaction_date: "2026-08-07", amount: -154400, category: "operating", description: "Pagos operativos identificados" },
  { kind: "transaction", id: "DEMO-TX-005", account_id: "ACCOUNT_0356_A", transaction_date: "2026-06-12", amount: 250000, category: "support", description: "Transferencia intragrupo identificada" },
  { kind: "transaction", id: "DEMO-TX-006", account_id: "ACCOUNT_0356_A", transaction_date: "2026-07-10", amount: 400000, category: "support", description: "Transferencia intragrupo identificada" },
  { kind: "transaction", id: "DEMO-TX-007", account_id: "ACCOUNT_0356_A", transaction_date: "2026-08-14", amount: 600000, category: "support", description: "Transferencia intragrupo identificada" },
  { kind: "transaction", id: "DEMO-TX-008", account_id: "ACCOUNT_0356_A", transaction_date: "2026-08-19", amount: 210000, category: "uncertain", description: "Finalidad no identificada con suficiente confianza" },
];

const mainCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 179046800,
  apparent_net: 4165600,
  headline: "Poca caja del negocio. Mucho apoyo del grupo.",
  explanation: "La operación identificada aporta 25,6 mil € netos, frente a 4,14 M€ de apoyo intragrupo identificado. La circulación emparejada no aporta caja neta nueva. Tener liquidez no significa que la haya generado el negocio: conviene revisar el peso del apoyo, sin concluir por ello insolvencia ni autosuficiencia.",
  confidence: 86,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["34 ciclos de tesorería emparejados", "12 transferencias intragrupo identificadas"],
  account_flows: {
    period: cashPeriod,
    explanation: "Tres transferencias representativas ya incluidas en el desglose de caja. No son el inventario completo de cuentas ni todos los movimientos del periodo. Banco, titularidad y emparejamiento son datos ficticios suministrados para la demo.",
    accounts: [
      { account_id: "ACCOUNT_0356_A", label: "Cuenta operativa", bank_name: "Banco A", currency: "EUR", ownership: "company", owner_company_id: "COMP_0356", owner_group_id: "GROUP_0042", ownership_source: "Registro de cuentas de ejemplo: cuenta asignada a COMP_0356.", confidence: 94 },
      { account_id: "ACCOUNT_0356_B", label: "Cuenta de tesorería", bank_name: "Banco B", currency: "EUR", ownership: "company", owner_company_id: "COMP_0356", owner_group_id: "GROUP_0042", ownership_source: "Registro de cuentas de ejemplo: cuenta asignada a COMP_0356.", confidence: 94 },
      { account_id: "ACCOUNT_GROUP_A", label: "Cuenta de otra sociedad del grupo", bank_name: "Banco A", currency: "EUR", ownership: "group_company", owner_company_id: "COMP_0007", owner_group_id: "GROUP_0042", ownership_source: "Registro de cuentas y sociedades de ejemplo: COMP_0007 pertenece a GROUP_0042.", confidence: 91 },
    ],
    transfers: [
      { id: "own-cycle", kind: "own_transfer", from_account_id: "ACCOUNT_0356_A", to_account_id: "ACCOUNT_0356_B", date: "2026-08-03", amount: 2500000, gross_movement: 5000000, company_net_amount: 0, category: "circulation", match_status: "matched", debit: { evidence_id: "cash-movements", transaction_id: "DEMO-TX-001" }, credit: { evidence_id: "cash-movements", transaction_id: "DEMO-TX-002" }, explanation: "El dinero sale de una cuenta y entra en otra del mismo titular. Se observan 5 M€ de movimiento bruto, pero solo se trasladan 2,5 M€ y el neto de este par en la empresa es cero. No es caja nueva.", confidence: 94 },
      { id: "group-support", kind: "intragroup_transfer", from_account_id: "ACCOUNT_GROUP_A", to_account_id: "ACCOUNT_0356_A", date: "2026-08-14", amount: 600000, gross_movement: 600000, company_net_amount: 600000, category: "support", match_status: "partial", debit: null, credit: { evidence_id: "cash-movements", transaction_id: "DEMO-TX-007" }, explanation: "Aquí cambia la empresa titular: el dinero procede de COMP_0007 y entra en COMP_0356. El pipeline de ejemplo lo clasifica como apoyo. Solo se aporta evidencia de la entrada en COMP_0356, no del cargo en la otra sociedad.", confidence: 91 },
      { id: "unidentified-source", kind: "unresolved", from_account_id: null, to_account_id: "ACCOUNT_0356_A", date: "2026-08-19", amount: 210000, gross_movement: 210000, company_net_amount: null, category: "uncertain", match_status: "partial", debit: null, credit: { evidence_id: "cash-movements", transaction_id: "DEMO-TX-008" }, explanation: "La entrada está observada, pero no se conoce suficientemente la cuenta de origen ni su titular. No se atribuye a cuentas propias, a apoyo del grupo ni a operación; el neto atribuible sigue sin identificar.", confidence: null },
    ],
  },
  components: [
    { category: "operating", label: "Generado por la operación", gross_movement: 1245600, net_amount: 25600, explanation: "Neto operativo identificado tras separar la circulación de tesorería emparejada.", confidence: 86, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Circulación de tesorería", gross_movement: 173451200, net_amount: 0, explanation: "Movimientos brutos emparejados, contando entrada y salida. No son generación operativa de caja.", confidence: 94, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Apoyo interno / intragrupo", gross_movement: 4140000, net_amount: 4140000, explanation: "Entradas de apoyo identificadas; no son ingresos de actividad ni caja generada por la operación.", confidence: 91, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Origen no identificado", gross_movement: 210000, net_amount: null, explanation: "No identificable con suficiente confianza.", confidence: null, evidence_refs: [] },
  ],
  correction: null,
  comparison: {
    company_id: "COMP_0655",
    apparent_net: 4165600,
    operating_net: 3850000,
    support_net: 315600,
    circulation_gross: 2400000,
    explanation: "Misma posición aparente de caja. Distinta realidad financiera. COMP_0655 muestra más generación operativa identificada y menos apoyo en este periodo de ejemplo; no es una evaluación completa de su salud financiera.",
  },
};

const comparisonCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 8265600,
  apparent_net: 4165600,
  headline: "Una caja similar. Un origen distinto.",
  explanation: "Un movimiento neto aparente similar se apoya principalmente en la operación identificada, no en el apoyo intragrupo. La circulación se mantiene separada y hay movimientos sin clasificar. Esto no determina por sí solo la salud financiera global.",
  confidence: 90,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["8 ciclos de tesorería emparejados", "2 transferencias intragrupo identificadas"],
  components: [
    { category: "operating", label: "Generado por la operación", gross_movement: 5450000, net_amount: 3850000, explanation: "Cobros operativos identificados menos pagos operativos.", confidence: 92, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Circulación de tesorería", gross_movement: 2400000, net_amount: 0, explanation: "Movimiento bruto emparejado, contando entrada y salida; no es caja generada.", confidence: 93, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Apoyo interno / intragrupo", gross_movement: 315600, net_amount: 315600, explanation: "Apoyo identificado, separado de la operación.", confidence: 87, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Origen no identificado", gross_movement: 100000, net_amount: null, explanation: "No identificable con suficiente confianza.", confidence: null, evidence_refs: [] },
  ],
  correction: null,
  comparison: {
    company_id: "COMP_0356",
    apparent_net: 4165600,
    operating_net: 25600,
    support_net: 4140000,
    circulation_gross: 173451200,
    explanation: "Misma posición aparente de caja. Distinta realidad financiera. COMP_0356 depende más del apoyo identificado pese a un movimiento neto aparente similar.",
  },
};

const punctualCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 3880000,
  apparent_net: 1720000,
  headline: "Operación positiva. El apoyo sigue siendo relevante.",
  explanation: "La operación sigue siendo positiva, pero la liquidez observada muestra mayor dependencia del apoyo identificado. Los movimientos sin clasificar permanecen visibles y no se consideran caja operativa.",
  confidence: 79,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["9 ciclos de tesorería emparejados", "5 transferencias intragrupo identificadas"],
  components: [
    { category: "operating", label: "Generado por la operación", gross_movement: 1400000, net_amount: 320000, explanation: "Neto operativo identificado tras separar la circulación.", confidence: 82, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Circulación de tesorería", gross_movement: 870000, net_amount: 0, explanation: "Movimientos brutos emparejados, contando entrada y salida; no son generación operativa.", confidence: 90, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Apoyo interno / intragrupo", gross_movement: 1400000, net_amount: 1400000, explanation: "Apoyo intragrupo identificado, no generación operativa.", confidence: 84, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Origen no identificado", gross_movement: 210000, net_amount: null, explanation: "No identificable con suficiente confianza.", confidence: null, evidence_refs: [] },
  ],
  correction: null,
  comparison: null,
};

function cashEvidence(cash: CashTruth, rows: TransactionEvidence[]): EvidenceGroup {
  return {
    id: "cash-movements",
    title: "Clasificación de caja y apoyo identificado",
    period: cash.period,
    explanation: "Muestra de movimientos ilustrativos, no una conciliación completa. Los recuentos de ciclos y transferencias se refieren al conjunto de ejemplo, no a las filas mostradas. No se atribuye finalidad operativa a lo no identificado. El neto aparente es una observación suministrada aparte, no la suma de los movimientos brutos clasificados.",
    confidence: cash.confidence,
    total_count: 156,
    rows,
  };
}

const comparisonTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-C-TX-001", transaction_date: "2026-08-01", amount: 4650000, category: "operating", description: "Cobros de clientes identificados" },
  { kind: "transaction", id: "DEMO-C-TX-002", transaction_date: "2026-08-05", amount: -800000, category: "operating", description: "Pagos a proveedores identificados" },
  { kind: "transaction", id: "DEMO-C-TX-003", transaction_date: "2026-08-06", amount: -120000, category: "circulation", description: "Salida de tesorería" },
  { kind: "transaction", id: "DEMO-C-TX-004", transaction_date: "2026-08-07", amount: 120000, category: "circulation", description: "Entrada de tesorería emparejada" },
  { kind: "transaction", id: "DEMO-C-TX-005", transaction_date: "2026-08-12", amount: 150600, category: "support", description: "Transferencia intragrupo identificada" },
  { kind: "transaction", id: "DEMO-C-TX-006", transaction_date: "2026-08-18", amount: 100000, category: "uncertain", description: "Finalidad sin clasificar" },
];

const punctualTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-P-TX-001", transaction_date: "2026-08-01", amount: 860000, category: "operating", description: "Cobros de clientes identificados" },
  { kind: "transaction", id: "DEMO-P-TX-002", transaction_date: "2026-08-05", amount: -540000, category: "operating", description: "Pagos operativos identificados" },
  { kind: "transaction", id: "DEMO-P-TX-003", transaction_date: "2026-08-06", amount: -150000, category: "circulation", description: "Salida de tesorería" },
  { kind: "transaction", id: "DEMO-P-TX-004", transaction_date: "2026-08-07", amount: 150000, category: "circulation", description: "Entrada de tesorería emparejada" },
  { kind: "transaction", id: "DEMO-P-TX-005", transaction_date: "2026-08-12", amount: 280000, category: "support", description: "Apoyo intragrupo identificado" },
  { kind: "transaction", id: "DEMO-P-TX-006", transaction_date: "2026-08-18", amount: 210000, category: "uncertain", description: "Finalidad sin clasificar" },
];

const growthEvidence: EvidenceGroup = {
  id: "growth-signals",
  title: "Señales de crecimiento bajo presión",
  period: `${beforePeriod} frente a ${afterPeriod}`,
  explanation: "Indicadores agregados ficticios para ilustrar crecimiento bajo presión. La facturación aumenta, pero la conversión a caja cae y crecen el apoyo utilizado y el plazo concedido. Son observaciones simultáneas, no una relación causal demostrada. No se calculan a partir de las facturas o movimientos de muestra.",
  confidence: 85,
  total_count: 6,
  rows: [
    { kind: "observation", id: "growth-revenue", metric: "Facturación", before: 1000000, after: 1320000, unit: "EUR" },
    { kind: "observation", id: "growth-conversion", metric: "Conversión de ventas a caja", before: 52, after: 24, unit: "%" },
    { kind: "observation", id: "growth-support", metric: "Apoyo intragrupo utilizado", before: 900000, after: 1400000, unit: "EUR" },
    { kind: "observation", id: "growth-terms", metric: "Plazo concedido a clientes", before: 62, after: 102, unit: "days" },
    { kind: "observation", id: "growth-cash", metric: "Tiempo hasta cobro", before: 81, after: 102, unit: "days" },
    { kind: "observation", id: "growth-delay", metric: "Retraso en los cobros", before: 20, after: 0, unit: "days" },
  ],
};

export const fixtureCompanies: Record<string, CompanyDetail> = {
  COMP_0356: {
    schema_version: "2.0",
    source: "fixture",
    company_id: "COMP_0356",
    group_id: "GROUP_0042",
    as_of: "2026-08-31",
    currency: "EUR",
    ...scoreSnapshot(72, { momentum: 68, cash_generation: 81, resilience: 74, debt: 59 }, [86, 87, 85, 88, 87, 86, 88, 86, 85, 86, 84, 83, 85, 84, 82, 83, 81, 80, 78, 77, 76, 74, 73, 72]),
    assessment: "Señales de presión y dependencia de apoyo",
    confidence: 88,
    trajectory: "deteriorating",
    summary: "La operación genera poca caja neta frente al apoyo intragrupo recibido. El saldo por sí solo no permite saber cuánto dinero aporta el negocio y cuánto llega de otras sociedades.",
    drivers_period: "sep 2024 – ago 2026 · contribuciones ilustrativas seleccionadas, no un desglose completo de la variación",
    drivers: [
      { id: "support", driver: "Dependencia de liquidez", affected_dimensions: ["resilience", "cash_generation"], impact: -8, direction: "negative", explanation: "El apoyo identificado gana importancia en la liquidez observada. Se muestra separado de lo que genera la actividad de la empresa.", evidence_count: 12, evidence_refs: ["cash-movements"] },
      { id: "terms", driver: "Plazos concedidos a clientes", affected_dimensions: ["momentum", "cash_generation"], impact: -5, direction: "negative", explanation: "Los plazos más largos mantienen la caja en manos del cliente durante más tiempo.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "collections", driver: "Cobros", affected_dimensions: ["cash_generation"], impact: 2, direction: "positive", explanation: "El menor retraso compensa parcialmente la ampliación de los plazos a clientes.", evidence_count: 48, evidence_refs: ["ar-timing"] },
    ],
    cash_truth: mainCash,
    time_borrowed: { ar: mainAr, ap: mainAp },
    alerts: [
      { id: "support", severity: "high", title: "Aumenta la dependencia de liquidez", explanation: "El apoyo identificado de 4,14 M€ acompaña a solo 25,6 mil € de neto operativo identificado. Conviene revisar cuánto necesita la empresa ese apoyo; no equivale a ventas ni demuestra por sí solo insolvencia.", period: cashPeriod, evidence_refs: ["cash-movements"] },
      { id: "customer-terms", severity: "medium", title: "Se amplían los plazos a clientes", explanation: "Los plazos concedidos pasaron de 75 a 90 días. Los cobros mejoraron, pero la conversión a caja se alargó.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "supplier-terms", severity: "medium", title: "Se acorta la financiación de proveedores", explanation: "Los plazos recibidos pasaron de 60 a 45 días y la caja se necesita antes. No se identifica la causa.", period: afterPeriod, evidence_refs: ["ap-timing"] },
    ],
    evidence: [cashEvidence(mainCash, mainTransactions), ...timingEvidence(mainAr, mainAp)],
    simulation: simulation(mainAr, mainAp, 78, 71),
  },
  COMP_0655: {
    schema_version: "2.0",
    source: "fixture",
    company_id: "COMP_0655",
    group_id: "GROUP_0087",
    as_of: "2026-08-31",
    currency: "EUR",
    ...scoreSnapshot(79, { momentum: 78, cash_generation: 87, resilience: 76, debt: 72 }, [59, 60, 59, 62, 61, 63, 62, 65, 66, 64, 67, 68, 67, 69, 71, 70, 72, 73, 72, 74, 76, 75, 77, 79]),
    assessment: "Mejora financiera con apoyo residual",
    confidence: 90,
    trajectory: "improving",
    summary: "Una posición aparente de caja similar, con una realidad financiera distinta: más generación operativa identificada y menor dependencia de apoyo.",
    drivers_period: "sep 2024 – ago 2026 · contribuciones ilustrativas seleccionadas, no un desglose completo de la variación",
    drivers: [
      { id: "operations", driver: "Generación operativa", affected_dimensions: ["cash_generation", "momentum"], impact: 9, direction: "positive", explanation: "La operación identificada aporta más a la liquidez observada.", evidence_count: 86, evidence_refs: ["cash-movements"] },
      { id: "terms", driver: "Plazos concedidos a clientes", affected_dimensions: ["cash_generation"], impact: 5, direction: "positive", explanation: "Unos plazos más cortos reducen el tiempo financiado a clientes.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "support", driver: "Dependencia residual de apoyo", affected_dimensions: ["resilience"], impact: -2, direction: "negative", explanation: "Parte de la liquidez sigue siendo atribuible al apoyo intragrupo identificado.", evidence_count: 2, evidence_refs: ["cash-movements"] },
    ],
    cash_truth: comparisonCash,
    time_borrowed: { ar: comparisonAr, ap: comparisonAp },
    alerts: [
      { id: "support", severity: "medium", title: "Persiste cierto apoyo intragrupo", explanation: "Los 315,6 mil € de apoyo identificado se mantienen separados de la generación operativa. Un Health Score que mejora no garantiza salud financiera.", period: cashPeriod, evidence_refs: ["cash-movements"] },
      { id: "coverage", severity: "low", title: "Hay movimientos de caja sin clasificar", explanation: "No puede atribuirse una finalidad con suficiente confianza a 100 mil € de movimiento bruto.", period: cashPeriod, evidence_refs: ["cash-movements"] },
    ],
    evidence: [cashEvidence(comparisonCash, comparisonTransactions), ...timingEvidence(comparisonAr, comparisonAp)],
    simulation: simulation(comparisonAr, comparisonAp, 85, 78),
  },
  COMP_1171: {
    schema_version: "2.0",
    source: "fixture",
    company_id: "COMP_1171",
    group_id: "GROUP_0194",
    as_of: "2026-08-31",
    currency: "EUR",
    ...scoreSnapshot(61, { momentum: 50, cash_generation: 62, resilience: 65, debt: 70 }, [77, 78, 77, 76, 78, 77, 76, 77, 75, 74, 75, 73, 72, 73, 71, 70, 69, 68, 66, 65, 64, 63, 62, 61]),
    assessment: "Crecimiento bajo presión de liquidez",
    confidence: 85,
    trajectory: "deteriorating",
    summary: "La facturación crece y el cliente paga puntual, pero la venta tarda más en convertirse en caja. Crecer no equivale a mejorar la posición financiera.",
    drivers_period: "sep 2024 – ago 2026 · contribuciones ilustrativas seleccionadas, no un desglose completo de la variación",
    drivers: [
      { id: "terms", driver: "Plazos concedidos a clientes", affected_dimensions: ["momentum", "cash_generation"], impact: -12, direction: "negative", explanation: "El plazo concedido al grupo de facturas observado aumentó 40 días.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "growth-pressure", driver: "Crecimiento bajo presión", affected_dimensions: ["momentum", "cash_generation", "resilience"], impact: -4, direction: "negative", explanation: "La facturación sube, pero la conversión a caja cae, aumenta el apoyo utilizado y se amplían los plazos a clientes. Son señales simultáneas de tensión, no causas demostradas ni otra puntuación.", evidence_count: 6, evidence_refs: ["growth-signals", "ar-timing"] },
      { id: "support", driver: "Dependencia de liquidez", affected_dimensions: ["resilience"], impact: -6, direction: "negative", explanation: "El apoyo identificado representa una parte creciente de la liquidez observada.", evidence_count: 5, evidence_refs: ["cash-movements"] },
      { id: "collections", driver: "Puntualidad en los cobros", affected_dimensions: ["cash_generation"], impact: 5, direction: "positive", explanation: "El retraso cayó a cero sin reducir el tiempo total hasta cobro.", evidence_count: 48, evidence_refs: ["ar-timing"] },
    ],
    cash_truth: punctualCash,
    time_borrowed: { ar: punctualAr, ap: mainAp },
    alerts: [
      { id: "cash-conversion", severity: "high", title: "La caja llega más tarde pese a la puntualidad", explanation: "El tiempo hasta cobro de COUNTERPARTY_06105 pasó de 81 a 102 días y el retraso de 20 a 0. Esto no permite concluir insolvencia ni pérdidas.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "growth-pressure", severity: "medium", title: "Crecimiento bajo presión", explanation: "Más facturación convive con menor conversión a caja, más apoyo utilizado y más plazo financiado al cliente. Revisar Momentum, Generación de caja y Resiliencia, sin asumir el motivo.", period: afterPeriod, evidence_refs: ["growth-signals"] },
      { id: "customer-terms", severity: "medium", title: "Se amplían los plazos a clientes", explanation: "Los plazos pasaron de 62 a 102 días. La empresa financia más tiempo antes del vencimiento.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "support", severity: "medium", title: "El apoyo identificado merece atención", explanation: "La operación positiva identificada convive con 1,4 M€ de apoyo intragrupo.", period: cashPeriod, evidence_refs: ["cash-movements"] },
    ],
    evidence: [cashEvidence(punctualCash, punctualTransactions), ...timingEvidence(punctualAr, mainAp), growthEvidence],
    simulation: simulation(punctualAr, mainAp, 66, 60),
  },
};
