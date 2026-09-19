import type {
  CashTruth,
  CompanyDetail,
  EvidenceGroup,
  HistoryPoint,
  InvoiceEvidence,
  Simulation,
  TimingSide,
  TransactionEvidence,
} from "../types/companyDetail";

const cashPeriod = "Sep 2025 – Aug 2026";
const beforePeriod = "Jan – Mar 2026";
const afterPeriod = "Jun – Aug 2026";

function history(pulse: number[], healthOffset: number): HistoryPoint[] {
  return pulse.map((value, index) => ({
    month: new Date(Date.UTC(2024, 8 + index, 1)).toISOString().slice(0, 10),
    pulse: value,
    health: Math.min(100, value + healthOffset),
  }));
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
    methodology: "Separate cohort medians in calendar days, grouped by payment date, not additive clocks. The median term plus median delay need not equal median time to cash. Representative mock invoices do not reproduce the full cohort.",
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
      title: side === "ar" ? "Customer invoice timing" : "Supplier invoice timing",
      period: `${beforePeriod} compared with ${afterPeriod}`,
      explanation: `${item.explanation} ${item.methodology}`,
      confidence: item.confidence,
      total_count: item.evidence_count,
      rows: invoices(side, item.counterparty_id, terms, delays),
    };
  });
}

function simulation(ar: TimingSide, ap: TimingSide): Simulation {
  return {
    inputs: [
      { key: "customer_term", label: "Customer payment term", unit: "days", baseline: ar.after.payment_term, min: -30, max: 30, step: 1, pulse_points_per_unit: -0.3, explanation: "Shorter terms mechanically reduce time financed to customers." },
      { key: "collection_delay", label: "Collection delay", unit: "days", baseline: ar.after.delay, min: -ar.after.delay, max: 30, step: 1, pulse_points_per_unit: -0.5, explanation: "Less delay mechanically shortens the collection cycle." },
      { key: "supplier_term", label: "Supplier payment term", unit: "days", baseline: ap.after.payment_term, min: -30, max: 30, step: 1, pulse_points_per_unit: 0.2, explanation: "Longer supplier terms mechanically defer the need for cash." },
      { key: "internal_support", label: "Internal support", unit: "%", baseline: 100, min: -50, max: 50, step: 1, pulse_points_per_unit: 0.14, explanation: "Less support reduces available liquidity in this mock; it does not establish self-sufficiency." },
    ],
    example: { customer_term: -15, collection_delay: -Math.min(3, ar.after.delay), supplier_term: 7, internal_support: -10 },
    methodology: "Illustrative, fixed mock sensitivities only. Each input delta is multiplied by its displayed points-per-unit weight; the sum is added to current Pulse, rounded and capped at 0–100. No cash-flow model, behavioral assumptions or financial prediction. Confidence is not recalculated.",
  };
}

const mainAr = timing("ar", "COUNTERPARTY_02340", [75, 85, 10], [90, 97, 7], "More time granted. Slower cash conversion.", "Customer terms increased by 15 days. Lower collection delay only partly offsets the additional time financed to customers. No motive is inferred.");
const mainAp = timing("ap", "COUNTERPARTY_04821", [60, 64, 4], [45, 48, 3], "Less time received. Cash is needed earlier.", "Supplier payment terms shortened by 15 days. The company needs cash earlier for these invoices; the reason for the change is not identified.");
const punctualAr = timing("ar", "COUNTERPARTY_06105", [62, 81, 20], [102, 102, 0], "Punctuality improved. Cash conversion became slower.", "Customers are paying on time, but the company is granting more time before payment is due. This describes timing, not customer quality, insolvency or loss.");
const comparisonAr = timing("ar", "COUNTERPARTY_03116", [75, 84, 9], [65, 69, 4], "Shorter terms. Faster cash conversion.", "Observed customer terms and collection delays both decreased. The reason is not inferred from invoice timing alone.");
const comparisonAp = timing("ap", "COUNTERPARTY_03921", [50, 52, 2], [57, 59, 2], "More time received. Cash is needed later.", "Supplier terms increased by 7 days while payment delay remained unchanged. This does not identify why terms changed.");

const mainTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-TX-001", transaction_date: "2026-08-03", amount: -2500000, category: "circulation", description: "Representative treasury cycle: outgoing leg" },
  { kind: "transaction", id: "DEMO-TX-002", transaction_date: "2026-08-04", amount: 2500000, category: "circulation", description: "Representative treasury cycle: matched incoming leg" },
  { kind: "transaction", id: "DEMO-TX-003", transaction_date: "2026-08-05", amount: 180000, category: "operating", description: "Identified customer collections" },
  { kind: "transaction", id: "DEMO-TX-004", transaction_date: "2026-08-07", amount: -154400, category: "operating", description: "Identified operating payments" },
  { kind: "transaction", id: "DEMO-TX-005", transaction_date: "2026-06-12", amount: 250000, category: "support", description: "Identified group transfer" },
  { kind: "transaction", id: "DEMO-TX-006", transaction_date: "2026-07-10", amount: 400000, category: "support", description: "Identified group transfer" },
  { kind: "transaction", id: "DEMO-TX-007", transaction_date: "2026-08-14", amount: 600000, category: "support", description: "Identified group transfer" },
  { kind: "transaction", id: "DEMO-TX-008", transaction_date: "2026-08-19", amount: 210000, category: "uncertain", description: "Purpose not identifiable with sufficient confidence" },
];

const mainCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 179046800,
  apparent_net: 4165600,
  headline: "False weakness. Real dependency.",
  explanation: "Correcting treasury circulation removes a false operating deterioration, while revealing liquidity dependency. Identified operations are slightly positive; observed liquidity still relies on identified support. This is not a healthy-company verdict.",
  confidence: 86,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["34 matched treasury cycles", "12 identified group transfers"],
  components: [
    { category: "operating", label: "Generated by operations", gross_movement: 1245600, net_amount: 25600, explanation: "Identified operating net, after separating matched treasury circulation.", confidence: 86, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Treasury circulation", gross_movement: 173451200, net_amount: 0, explanation: "Gross matched movements, including both legs. Circulation is not operating cash generation.", confidence: 94, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Group / internal support", gross_movement: 4140000, net_amount: 4140000, explanation: "Identified support inflows; not revenue or self-generated operating cash.", confidence: 91, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Other / uncertain", gross_movement: 210000, net_amount: null, explanation: "Not identifiable with sufficient confidence.", confidence: null, evidence_refs: [] },
  ],
  correction: {
    apparent_operating: -86700000,
    identified_operating: 25600,
    observed_support: 4140000,
    explanation: "The mock correction separates €86.7256M of outgoing treasury circulation previously included in the apparent operating figure. The matching incoming leg is circulation too. Support remains separate; this is a classification correction, not new cash.",
  },
  comparison: {
    company_id: "COMP_0655",
    apparent_net: 4165600,
    operating_net: 3850000,
    support_net: 315600,
    circulation_gross: 2400000,
    explanation: "Same apparent cash position. Different financial reality. COMP_0655 shows more identified operating generation and less identified support in this mock period; that alone is not a full health assessment.",
  },
};

const comparisonCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 8265600,
  apparent_net: 4165600,
  headline: "Same cash position. A different source.",
  explanation: "A similar apparent net cash movement is supported mainly by identified operations rather than group support. Treasury circulation remains separate, and some movement is unclassified. This alone does not establish overall financial health.",
  confidence: 90,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["8 matched treasury cycles", "2 identified group transfers"],
  components: [
    { category: "operating", label: "Generated by operations", gross_movement: 5450000, net_amount: 3850000, explanation: "Identified operating receipts less operating payments.", confidence: 92, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Treasury circulation", gross_movement: 2400000, net_amount: 0, explanation: "Gross matched movements, including both legs; not cash generated.", confidence: 93, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Group / internal support", gross_movement: 315600, net_amount: 315600, explanation: "Identified support, shown separately from operations.", confidence: 87, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Other / uncertain", gross_movement: 100000, net_amount: null, explanation: "Not identifiable with sufficient confidence.", confidence: null, evidence_refs: [] },
  ],
  correction: null,
  comparison: {
    company_id: "COMP_0356",
    apparent_net: 4165600,
    operating_net: 25600,
    support_net: 4140000,
    circulation_gross: 173451200,
    explanation: "Same apparent cash position. Different financial reality. COMP_0356 depends more on identified support despite a similar apparent net movement.",
  },
};

const punctualCash: CashTruth = {
  period: cashPeriod,
  total_gross_movement: 3880000,
  apparent_net: 1720000,
  headline: "Positive operations. Support still matters.",
  explanation: "Operations remain positive, but observed liquidity shows increasing dependency on identified support. Unclassified movements remain visible rather than being treated as operating cash.",
  confidence: 79,
  evidence_refs: ["cash-movements"],
  evidence_summary: ["9 matched treasury cycles", "5 identified group transfers"],
  components: [
    { category: "operating", label: "Generated by operations", gross_movement: 1400000, net_amount: 320000, explanation: "Identified operating net after separating circulation.", confidence: 82, evidence_refs: ["cash-movements"] },
    { category: "circulation", label: "Treasury circulation", gross_movement: 870000, net_amount: 0, explanation: "Gross matched movements, including both legs; not operating generation.", confidence: 90, evidence_refs: ["cash-movements"] },
    { category: "support", label: "Group / internal support", gross_movement: 1400000, net_amount: 1400000, explanation: "Identified group support, not operating generation.", confidence: 84, evidence_refs: ["cash-movements"] },
    { category: "uncertain", label: "Other / uncertain", gross_movement: 210000, net_amount: null, explanation: "Not identifiable with sufficient confidence.", confidence: null, evidence_refs: [] },
  ],
  correction: null,
  comparison: null,
};

function cashEvidence(cash: CashTruth, rows: TransactionEvidence[]): EvidenceGroup {
  return {
    id: "cash-movements",
    title: "Cash classification & identified support",
    period: cash.period,
    explanation: "Illustrative transaction samples, not a complete reconciliation. Matched-cycle and transfer counts describe the full mock cohort, not the rows shown. Uncertain movement is not assigned an operating purpose. Apparent net is a separate supplied observation, not a sum of classified gross movements.",
    confidence: cash.confidence,
    total_count: 156,
    rows,
  };
}

const comparisonTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-C-TX-001", transaction_date: "2026-08-01", amount: 4650000, category: "operating", description: "Identified customer receipts" },
  { kind: "transaction", id: "DEMO-C-TX-002", transaction_date: "2026-08-05", amount: -800000, category: "operating", description: "Identified supplier payments" },
  { kind: "transaction", id: "DEMO-C-TX-003", transaction_date: "2026-08-06", amount: -120000, category: "circulation", description: "Treasury outgoing leg" },
  { kind: "transaction", id: "DEMO-C-TX-004", transaction_date: "2026-08-07", amount: 120000, category: "circulation", description: "Matched treasury incoming leg" },
  { kind: "transaction", id: "DEMO-C-TX-005", transaction_date: "2026-08-12", amount: 150600, category: "support", description: "Identified group transfer" },
  { kind: "transaction", id: "DEMO-C-TX-006", transaction_date: "2026-08-18", amount: 100000, category: "uncertain", description: "Unclassified purpose" },
];

const punctualTransactions: TransactionEvidence[] = [
  { kind: "transaction", id: "DEMO-P-TX-001", transaction_date: "2026-08-01", amount: 860000, category: "operating", description: "Identified customer receipts" },
  { kind: "transaction", id: "DEMO-P-TX-002", transaction_date: "2026-08-05", amount: -540000, category: "operating", description: "Identified operating payments" },
  { kind: "transaction", id: "DEMO-P-TX-003", transaction_date: "2026-08-06", amount: -150000, category: "circulation", description: "Treasury outgoing leg" },
  { kind: "transaction", id: "DEMO-P-TX-004", transaction_date: "2026-08-07", amount: 150000, category: "circulation", description: "Matched treasury incoming leg" },
  { kind: "transaction", id: "DEMO-P-TX-005", transaction_date: "2026-08-12", amount: 280000, category: "support", description: "Identified group support" },
  { kind: "transaction", id: "DEMO-P-TX-006", transaction_date: "2026-08-18", amount: 210000, category: "uncertain", description: "Unclassified purpose" },
];

export const mockCompanies: Record<string, CompanyDetail> = {
  COMP_0356: {
    schema_version: "1.0",
    source: "mock",
    company_id: "COMP_0356",
    group_id: "GROUP_0042",
    as_of: "2026-08-31",
    currency: "EUR",
    pulse: 68,
    health: 72,
    momentum: { direction: "deteriorating", label: "Deteriorating" },
    stability: 61,
    confidence: 88,
    trajectory: "deteriorating",
    summary: "The cash position is not the whole story. Operating weakness is overstated, but dependency on group support deserves attention.",
    history: history([82, 83, 81, 84, 83, 82, 84, 82, 81, 82, 80, 79, 81, 80, 78, 79, 77, 76, 74, 73, 72, 70, 69, 68], 4),
    drivers_period: "Sep 2024 – Aug 2026 · selected mock contributions, not a full score reconciliation",
    drivers: [
      { id: "support", driver: "Liquidity dependency", impact: -8, direction: "negative", explanation: "Identified support is increasingly important to observed liquidity. This is separate from the corrected operating classification.", evidence_count: 12, evidence_refs: ["cash-movements"] },
      { id: "terms", driver: "Customer terms", impact: -5, direction: "negative", explanation: "Longer granted payment terms keep cash with customers for longer.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "collections", driver: "Collections", impact: 2, direction: "positive", explanation: "Lower collection delays partially offset the extension of customer terms.", evidence_count: 48, evidence_refs: ["ar-timing"] },
    ],
    cash_truth: mainCash,
    time_borrowed: { ar: mainAr, ap: mainAp },
    alerts: [
      { id: "support", severity: "high", title: "Liquidity dependency increasing", explanation: "€4.14M of identified support accompanies only €25.6k of identified operating net. A corrected classification does not remove liquidity dependency.", period: cashPeriod, evidence_refs: ["cash-movements"] },
      { id: "customer-terms", severity: "medium", title: "Customer payment terms extended", explanation: "Granted terms increased from 75 to 90 days. Collections improved, but the observed cash conversion cycle became longer.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "supplier-terms", severity: "medium", title: "Supplier funding window shortened", explanation: "Received payment terms shortened from 60 to 45 days, bringing the need for cash forward. The reason is not identified.", period: afterPeriod, evidence_refs: ["ap-timing"] },
    ],
    evidence: [cashEvidence(mainCash, mainTransactions), ...timingEvidence(mainAr, mainAp)],
    simulation: simulation(mainAr, mainAp),
  },
  COMP_0655: {
    schema_version: "1.0",
    source: "mock",
    company_id: "COMP_0655",
    group_id: "GROUP_0087",
    as_of: "2026-08-31",
    currency: "EUR",
    pulse: 65,
    health: 70,
    momentum: { direction: "improving", label: "Improving" },
    stability: 73,
    confidence: 90,
    trajectory: "improving",
    summary: "A similar apparent cash position, with a different financial reality: more identified operating generation and less reliance on support.",
    history: history([45, 46, 45, 48, 47, 49, 48, 51, 52, 50, 53, 54, 53, 55, 57, 56, 58, 59, 58, 60, 62, 61, 63, 65], 5),
    drivers_period: "Sep 2024 – Aug 2026 · selected mock contributions, not a full score reconciliation",
    drivers: [
      { id: "operations", driver: "Operating generation", impact: 9, direction: "positive", explanation: "Identified operating generation contributes more to observed liquidity.", evidence_count: 86, evidence_refs: ["cash-movements"] },
      { id: "terms", driver: "Customer terms", impact: 5, direction: "positive", explanation: "Shorter customer terms reduce the observed time financed to customers.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "support", driver: "Residual support reliance", impact: -2, direction: "negative", explanation: "Some liquidity is still attributable to identified group support.", evidence_count: 2, evidence_refs: ["cash-movements"] },
    ],
    cash_truth: comparisonCash,
    time_borrowed: { ar: comparisonAr, ap: comparisonAp },
    alerts: [
      { id: "support", severity: "medium", title: "Residual reliance on group support", explanation: "€315.6k of identified support remains distinct from operating generation. Improving Pulse is not proof of financial health.", period: cashPeriod, evidence_refs: ["cash-movements"] },
      { id: "coverage", severity: "low", title: "Some cash movements remain unclassified", explanation: "€100k of gross movement cannot be assigned a purpose with sufficient confidence.", period: cashPeriod, evidence_refs: ["cash-movements"] },
    ],
    evidence: [cashEvidence(comparisonCash, comparisonTransactions), ...timingEvidence(comparisonAr, comparisonAp)],
    simulation: simulation(comparisonAr, comparisonAp),
  },
  COMP_1171: {
    schema_version: "1.0",
    source: "mock",
    company_id: "COMP_1171",
    group_id: "GROUP_0194",
    as_of: "2026-08-31",
    currency: "EUR",
    pulse: 62,
    health: 67,
    momentum: { direction: "deteriorating", label: "Deteriorating" },
    stability: 64,
    confidence: 85,
    trajectory: "deteriorating",
    summary: "Customers now pay on time. Yet cash arrives later, because the company grants more time before payment is due.",
    history: history([78, 79, 78, 77, 79, 78, 77, 78, 76, 75, 76, 74, 73, 74, 72, 71, 70, 69, 67, 66, 65, 64, 63, 62], 5),
    drivers_period: "Sep 2024 – Aug 2026 · selected mock contributions, not a full score reconciliation",
    drivers: [
      { id: "terms", driver: "Customer terms", impact: -12, direction: "negative", explanation: "Granted terms increased by 40 days for the observed counterparty cohort.", evidence_count: 48, evidence_refs: ["ar-timing"] },
      { id: "support", driver: "Liquidity dependency", impact: -6, direction: "negative", explanation: "Identified support makes up an increasing part of observed liquidity.", evidence_count: 5, evidence_refs: ["cash-movements"] },
      { id: "collections", driver: "Payment punctuality", impact: 5, direction: "positive", explanation: "Late payment fell to zero, without making the total cash conversion cycle shorter.", evidence_count: 48, evidence_refs: ["ar-timing"] },
    ],
    cash_truth: punctualCash,
    time_borrowed: { ar: punctualAr, ap: mainAp },
    alerts: [
      { id: "cash-conversion", severity: "high", title: "Cash conversion slowed despite punctuality", explanation: "Time to cash rose from 81 to 102 days for COUNTERPARTY_06105 while delay fell from 20 to 0 days. This does not imply insolvency or loss.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "customer-terms", severity: "medium", title: "Customer payment terms extended", explanation: "Terms rose from 62 to 102 days. The company is financing more time before payment is due.", period: afterPeriod, evidence_refs: ["ar-timing"] },
      { id: "support", severity: "medium", title: "Identified support deserves attention", explanation: "Positive identified operations coexist with €1.4M of identified group support.", period: cashPeriod, evidence_refs: ["cash-movements"] },
    ],
    evidence: [cashEvidence(punctualCash, punctualTransactions), ...timingEvidence(punctualAr, mainAp)],
    simulation: simulation(punctualAr, mainAp),
  },
};
