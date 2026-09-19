export type Trajectory = "improving" | "deteriorating" | "stable";
export type Direction = "positive" | "negative" | "neutral";
export type CashCategory = "operating" | "circulation" | "support" | "uncertain";
export type EvidenceRef = string;

export interface HistoryPoint {
  month: string;
  pulse: number;
  health: number;
}

export interface Driver {
  id: string;
  driver: string;
  impact: number;
  direction: Direction;
  explanation: string;
  evidence_count: number;
  evidence_refs: EvidenceRef[];
}

export interface CashComponent {
  category: CashCategory;
  label: string;
  gross_movement: number;
  net_amount: number | null;
  explanation: string;
  confidence: number | null;
  evidence_refs: EvidenceRef[];
}

export interface CashTruth {
  period: string;
  total_gross_movement: number;
  apparent_net: number;
  components: CashComponent[];
  headline: string;
  explanation: string;
  confidence: number | null;
  evidence_refs: EvidenceRef[];
  evidence_summary: string[];
  correction: {
    apparent_operating: number;
    identified_operating: number;
    observed_support: number;
    explanation: string;
  } | null;
  comparison: {
    company_id: string;
    apparent_net: number;
    operating_net: number;
    support_net: number;
    circulation_gross: number;
    explanation: string;
  } | null;
}

export interface TimingSnapshot {
  period: string;
  payment_term: number;
  time_to_cash: number;
  delay: number;
}

export interface TimingSide {
  counterparty_id: string;
  before: TimingSnapshot;
  after: TimingSnapshot;
  headline: string;
  explanation: string;
  methodology: string;
  confidence: number | null;
  evidence_count: number;
  evidence_refs: EvidenceRef[];
}

export interface TimeBorrowed {
  ar: TimingSide | null;
  ap: TimingSide | null;
}

export interface CompanyAlert {
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
  explanation: string;
  period: string;
  evidence_refs: EvidenceRef[];
}

export interface TransactionEvidence {
  kind: "transaction";
  id: string;
  transaction_date: string;
  amount: number;
  category: CashCategory;
  description: string;
}

export interface InvoiceEvidence {
  kind: "invoice";
  id: string;
  invoice: string;
  counterparty_id: string;
  side: "ar" | "ap";
  issue_date: string;
  due_date: string;
  payment_date: string | null;
  amount: number;
}

export interface EvidenceGroup {
  id: EvidenceRef;
  title: string;
  period: string;
  explanation: string;
  confidence: number | null;
  total_count: number;
  rows: (TransactionEvidence | InvoiceEvidence)[];
}

export type ScenarioKey = "customer_term" | "collection_delay" | "supplier_term" | "internal_support";
export type ScenarioInputs = Record<ScenarioKey, number>;

export interface SimulationInput {
  key: ScenarioKey;
  label: string;
  unit: "days" | "%";
  baseline: number;
  min: number;
  max: number;
  step: number;
  pulse_points_per_unit: number;
  explanation: string;
}

export interface Simulation {
  inputs: SimulationInput[];
  example: ScenarioInputs;
  methodology: string;
}

export interface CompanyDetail {
  schema_version: "1.0";
  source: "mock" | "precomputed";
  company_id: string;
  group_id: string;
  as_of: string;
  currency: "EUR";
  pulse: number;
  health: number;
  momentum: { direction: Trajectory; label: string };
  stability: number;
  confidence: number | null;
  trajectory: Trajectory;
  summary: string;
  history: HistoryPoint[];
  drivers_period: string;
  drivers: Driver[];
  cash_truth: CashTruth;
  time_borrowed: TimeBorrowed;
  alerts: CompanyAlert[];
  evidence: EvidenceGroup[];
  simulation: Simulation;
}
