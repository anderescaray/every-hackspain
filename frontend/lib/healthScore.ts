import type { DimensionKey } from "../types/companyDetail";

export const HEALTH_DIMENSIONS: { key: DimensionKey; label: string; explanation: string }[] = [
  { key: "momentum", label: "Momentum", explanation: "Hacia dónde va la caja operativa." },
  { key: "cash_generation", label: "Generación de caja", explanation: "Cuánta caja genera la actividad." },
  { key: "resilience", label: "Resiliencia", explanation: "Aguante ante meses con déficit de caja." },
  { key: "debt", label: "Deuda", explanation: "Presión de los pagos de deuda observados." },
];
