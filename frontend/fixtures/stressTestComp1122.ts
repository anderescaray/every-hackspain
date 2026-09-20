/** Presentation-only Stress Test demo for COMP_1122. Not a financial model. Not used by companyData. */
export const STRESS_DEMO_COMPANY_ID = "COMP_1122";
export const STRESS_DEMO_SOURCE = "demo-fixture" as const;

export type StressDemoUnit = "pct" | "days" | "bp";
export type StressDemoBand = "green" | "amber" | "red";
export type StressDemoGroup = "comercial" | "costes" | "financiacion" | "mercado";

export type StressDemoShock = { factor: string; relative_pct: number; unit: StressDemoUnit };
export type StressDemoAttribution = { factor: string; points: number };
export type StressDemoPath = { observed_months: 1 | 3 | 6; health: number; band: StressDemoBand };
export type StressDemoEconomic = { label: string; value: string };

export type StressDemoOutcome = {
  health: number;
  delta_points: number;
  band: StressDemoBand;
  path: StressDemoPath[];
  attribution: StressDemoAttribution[];
  economic: StressDemoEconomic;
};

export type StressDemoControl = {
  factor: string;
  group: StressDemoGroup;
  label: string;
  microcopy: string;
  context: string | null;
  unit: StressDemoUnit;
  positions: number[];
};

export type StressDemoPreset = {
  id: string;
  label: string;
  shocks: StressDemoShock[];
  outcome: StressDemoOutcome;
};

const band = (health: number): StressDemoBand => health >= 70 ? "green" : health >= 40 ? "amber" : "red";
const path = (one: number, three: number, six: number): StressDemoPath[] => [
  { observed_months: 1, health: one, band: band(one) },
  { observed_months: 3, health: three, band: band(three) },
  { observed_months: 6, health: six, band: band(six) },
];

export const demoChannelIds = ["margen", "cobros", "costes", "tesorería", "divisa"] as const;
export type DemoChannelId = (typeof demoChannelIds)[number];

export const demoGroupTitles: Record<StressDemoGroup, string> = {
  comercial: "Cobros",
  costes: "Costes",
  financiacion: "Tesorería",
  mercado: "Divisa",
};

export const stressDemoComp1122 = {
  source: STRESS_DEMO_SOURCE,
  company_id: STRESS_DEMO_COMPANY_ID,
  baseline_health: 65,
  baseline_band: "amber" as StressDemoBand,
  default_preset_id: "severo",
  default_horizon: 6 as 1 | 3 | 6,
  presets: [
    {
      id: "leve", label: "Leve",
      shocks: [
        { factor: "operating_inflow", relative_pct: -10, unit: "pct" },
        { factor: "customer_delay", relative_pct: 15, unit: "days" },
      ],
      outcome: {
        health: 62, delta_points: -3, band: "amber",
        path: path(64, 63, 62),
        attribution: [
          { factor: "operating_inflow", points: -1.8 },
          { factor: "customer_delay", points: -1.2 },
        ],
        economic: { label: "Impacto mensual", value: "−42k €/mes" },
      },
    },
    {
      id: "medio", label: "Medio",
      shocks: [
        { factor: "operating_inflow", relative_pct: -15, unit: "pct" },
        { factor: "operating_outflow", relative_pct: 10, unit: "pct" },
        { factor: "customer_delay", relative_pct: 30, unit: "days" },
      ],
      outcome: {
        health: 57, delta_points: -8, band: "amber",
        path: path(62, 59, 57),
        attribution: [
          { factor: "operating_inflow", points: -4.1 },
          { factor: "customer_delay", points: -2.4 },
          { factor: "operating_outflow", points: -1.5 },
        ],
        economic: { label: "Impacto mensual", value: "−81k €/mes" },
      },
    },
    {
      id: "severo", label: "Severo",
      shocks: [
        { factor: "operating_inflow", relative_pct: -15, unit: "pct" },
        { factor: "operating_outflow", relative_pct: 12, unit: "pct" },
        { factor: "customer_delay", relative_pct: 30, unit: "days" },
        { factor: "variable_rate", relative_pct: 200, unit: "bp" },
        { factor: "fx_CAD", relative_pct: -10, unit: "pct" },
      ],
      outcome: {
        health: 52, delta_points: -13, band: "amber",
        path: path(62, 57, 52),
        attribution: [
          { factor: "operating_inflow", points: -5.2 },
          { factor: "customer_delay", points: -3.1 },
          { factor: "operating_outflow", points: -2.4 },
          { factor: "variable_rate", points: -1.5 },
          { factor: "fx_CAD", points: -0.8 },
        ],
        economic: { label: "Impacto mensual", value: "−118k €/mes" },
      },
    },
  ] satisfies StressDemoPreset[],
  controls: [
    { factor: "customer_delay", group: "comercial", label: "Retraso de cobros", microcopy: "Días extra del cliente principal identificado.", context: null, unit: "days", positions: [0, 15, 30, 60] },
    { factor: "operating_inflow", group: "comercial", label: "Caída de cobros", microcopy: "Reducción del volumen de cobros operativos.", context: null, unit: "pct", positions: [0, -10, -15, -20, -30] },
    { factor: "operating_outflow", group: "costes", label: "Subida de costes", microcopy: "Aumento de los costes operativos observados.", context: null, unit: "pct", positions: [0, 10, 12, 20, 30] },
    { factor: "variable_rate", group: "financiacion", label: "Endurecimiento de financiación", microcopy: "Shock sobre el coste de la deuda variable.", context: null, unit: "bp", positions: [0, 100, 200, 300] },
    { factor: "fx_CAD", group: "mercado", label: "EURUSD", microcopy: "Variación del valor en EUR de la exposición.", context: null, unit: "pct", positions: [-20, -10, 0, 10, 20] },
  ] satisfies StressDemoControl[],
} as const;

const demoWeights: Record<string, { pts: number; eur: number }> = {
  operating_inflow: { pts: 0.35, eur: 6100 },
  operating_outflow: { pts: 0.22, eur: 4800 },
  cost_payroll: { pts: 0.18, eur: 3600 },
  customer_delay: { pts: 0.1, eur: 2200 },
  observed_debt_service: { pts: 0.08, eur: 900 },
  variable_rate: { pts: 0.008, eur: 85 },
  fx_CAD: { pts: 0.08, eur: 2800 },
};

export function demoValuesFromShocks(shocks: StressDemoShock[]): Record<string, number> {
  const values: Record<string, number> = {};
  for (const control of stressDemoComp1122.controls) values[control.factor] = 0;
  for (const shock of shocks) values[shock.factor] = shock.relative_pct;
  return values;
}

export function demoShocksFromValues(values: Record<string, number>): StressDemoShock[] {
  return stressDemoComp1122.controls.flatMap((control) => {
    const relative_pct = values[control.factor] ?? 0;
    if (!relative_pct) return [];
    return [{ factor: control.factor, relative_pct, unit: control.unit }];
  });
}

export function demoChannels(values: Record<string, number>): { id: DemoChannelId; label: string; active: boolean }[] {
  const inflow = values.operating_inflow ?? 0;
  const delay = values.customer_delay ?? 0;
  const outflow = values.operating_outflow ?? 0;
  const funding = (values.variable_rate ?? 0) || (values.observed_debt_service ?? 0);
  const fx = values.fx_CAD ?? 0;
  return [
    { id: "margen", label: "margen", active: inflow !== 0 && outflow !== 0 },
    { id: "cobros", label: "cobros", active: inflow !== 0 || delay !== 0 },
    { id: "costes", label: "costes", active: outflow !== 0 },
    { id: "tesorería", label: "tesorería", active: funding !== 0 },
    { id: "divisa", label: "divisa", active: fx !== 0 },
  ];
}

export function demoHealthAtHorizon(outcome: StressDemoOutcome, horizon: 1 | 3 | 6) {
  return outcome.path.find((item) => item.observed_months === horizon)?.health ?? outcome.health;
}

export function demoStressCopy(health: number, delta: number, money: string) {
  const pts = Math.abs(Math.round(delta));
  const drop = delta < 0;
  const ptsLabel = pts === 1 ? "punto" : "puntos";
  return {
    headline: !drop ? "El Health se mantiene." : pts >= 10 ? "La tesorería no absorbe el shock." : "El shock deja huella en el Health.",
    body: drop ? `El Health cae ${pts} ${ptsLabel}. El impacto de caja es ${money}.` : `Sin caída de Health. El impacto de caja es ${money}.`,
    close: health <= 52
      ? "La tesorería no cubre el deterioro. El negocio se tensiona."
      : health < 60
        ? "La caja aguanta, pero el margen de seguridad se estrecha."
        : "Queda colchón suficiente en este horizonte.",
  };
}

function roundHealth(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

/** Presentation lookup only. Do not reuse outside COMP_1122 demo. */
export function resolveComp1122Custom(values: Record<string, number>): StressDemoOutcome {
  const shocks = demoShocksFromValues(values);
  const attribution = shocks.map((shock) => {
    const weight = demoWeights[shock.factor] ?? { pts: 0.1, eur: 1000 };
    const magnitude = shock.unit === "bp" ? shock.relative_pct : Math.abs(shock.relative_pct);
    const sign = shock.factor === "operating_inflow" || shock.factor === "fx_CAD"
      ? (shock.relative_pct < 0 ? -1 : 1)
      : (shock.relative_pct > 0 ? -1 : 1);
    return { factor: shock.factor, points: Math.round(sign * magnitude * weight.pts * 10) / 10 };
  }).filter((item) => item.points !== 0).sort((a, b) => Math.abs(b.points) - Math.abs(a.points));
  const delta = Math.round(attribution.reduce((sum, item) => sum + item.points, 0) * 10) / 10;
  const health = roundHealth(stressDemoComp1122.baseline_health + delta);
  const one = roundHealth(stressDemoComp1122.baseline_health + delta * 0.4);
  const three = roundHealth(stressDemoComp1122.baseline_health + delta * 0.7);
  const eur = Math.round(shocks.reduce((sum, shock) => {
    const weight = demoWeights[shock.factor] ?? { eur: 0 };
    const magnitude = shock.unit === "bp" ? shock.relative_pct / 10 : Math.abs(shock.relative_pct);
    return sum + magnitude * weight.eur;
  }, 0) / 1000) * 1000;
  return {
    health, delta_points: health - stressDemoComp1122.baseline_health, band: band(health),
    path: path(one, three, health), attribution: attribution.slice(0, 5),
    economic: { label: "Impacto mensual", value: eur ? `−${Math.round(eur / 1000)}k €/mes` : "0 €/mes" },
  };
}

export function isStressDemoCompany(companyId?: string | null) {
  return companyId === STRESS_DEMO_COMPANY_ID;
}
