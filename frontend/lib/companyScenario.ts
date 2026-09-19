import type { ScenarioInputs, Simulation } from "../types/companyDetail";

export const defaultScenarioInputs: ScenarioInputs = {
  customer_term: 0,
  collection_delay: 0,
  supplier_term: 0,
  internal_support: 0,
};

export function selectScenario(currentHealthScore: number | null, simulation: Simulation, requested: ScenarioInputs) {
  const inputs = { ...defaultScenarioInputs };
  for (const input of simulation.inputs) {
    const value = Number.isFinite(requested[input.key]) ? requested[input.key] : 0;
    inputs[input.key] = Math.max(input.min, Math.min(input.max, Math.round(value / input.step) * input.step)) || 0;
  }
  const isBaseline = Object.values(inputs).every((value) => value === 0);
  const scenario = simulation.scenarios.find((item) => simulation.inputs.every((input) => item.inputs[input.key] === inputs[input.key]));
  return {
    inputs,
    health_score: isBaseline ? currentHealthScore : scenario?.health_score ?? null,
    impacts: isBaseline ? [] : scenario?.impacts ?? [],
    explanation: isBaseline ? "Sin ajustes: se muestra el análisis actual." : scenario?.explanation ?? "No hay un escenario precalculado para esta combinación. No se estima una puntuación.",
  };
}
