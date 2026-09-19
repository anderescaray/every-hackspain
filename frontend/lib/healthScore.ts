import type { DimensionKey } from "../types/companyDetail";

export const HEALTH_DIMENSIONS: { key: DimensionKey; label: string; explanation: string }[] = [
  { key: "momentum", label: "Momentum", explanation: "Trayectoria reciente de caja operativa. Es un nowcast, no un pronóstico." },
  { key: "cash_generation", label: "Generación de caja", explanation: "Capacidad de convertir la actividad en caja operativa." },
  { key: "resilience", label: "Resiliencia", explanation: "Presión histórica de los déficits de caja operativa." },
  { key: "debt", label: "Deuda", explanation: "Presión del servicio financiero observado; no mide deuda total ni solvencia." },
];
