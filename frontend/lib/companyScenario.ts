import type { ScenarioInputs, Simulation } from "../types/companyDetail";

export const defaultScenarioInputs: ScenarioInputs = {
  customer_term: 0,
  collection_delay: 0,
  supplier_term: 0,
  internal_support: 0,
};

export function calculateScenario(currentPulse: number, simulation: Simulation, requested: ScenarioInputs) {
  const inputs = { ...defaultScenarioInputs };
  const impacts = simulation.inputs.map((input) => {
    const value = Number.isFinite(requested[input.key]) ? requested[input.key] : 0;
    const delta = Math.max(input.min, Math.min(input.max, Math.round(value / input.step) * input.step)) || 0;
    inputs[input.key] = delta;
    return { key: input.key, label: input.label, points: delta * input.pulse_points_per_unit };
  });
  const uncapped = currentPulse + impacts.reduce((sum, impact) => sum + impact.points, 0);
  return { inputs, impacts, pulse: Math.max(0, Math.min(100, Math.round(uncapped))) };
}
