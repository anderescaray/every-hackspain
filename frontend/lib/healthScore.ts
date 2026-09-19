import type { DimensionKey, HealthScoreModel, HealthScoreWeights } from "../types/companyDetail";

export const HEALTH_SCORE_WEIGHTS: HealthScoreWeights = Object.freeze({
  momentum: 0.25,
  cash_generation: 0.30,
  resilience: 0.25,
  debt: 0.20,
});

export const HEALTH_SCORE_MODEL: HealthScoreModel = {
  version: "demo-v1",
  provisional: true,
  weights: HEALTH_SCORE_WEIGHTS,
};

export const HEALTH_DIMENSIONS: { key: DimensionKey; label: string; explanation: string }[] = [
  { key: "momentum", label: "Momentum", explanation: "Hacia dónde va la caja operativa." },
  { key: "cash_generation", label: "Generación de caja", explanation: "Cuánta caja genera la actividad." },
  { key: "resilience", label: "Resiliencia", explanation: "Aguante ante meses con déficit de caja." },
  { key: "debt", label: "Deuda", explanation: "Presión de los pagos de deuda observados." },
];
