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
  { key: "momentum", label: "Momentum", explanation: "Evolución financiera: crecer más no siempre significa mejorar." },
  { key: "cash_generation", label: "Generación de caja", explanation: "Capacidad de convertir la actividad en caja operativa." },
  { key: "resilience", label: "Resiliencia", explanation: "Margen para absorber tensiones de liquidez y financiación." },
  { key: "debt", label: "Deuda", explanation: "Capacidad de atender compromisos; más puntos no significa más deuda." },
];
