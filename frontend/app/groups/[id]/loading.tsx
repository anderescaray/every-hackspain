import base from "@/components/insights/insights.module.css";

export default function LoadingGroup() {
  return <main className={`${base.page} ${base.routeState}`} role="status"><span className={base.eyebrow}>Embat Pulse · Inteligencia de grupo</span><h1>Preparando el análisis del grupo…</h1><p>Cargando sociedades, relaciones observadas y revisiones propuestas.</p></main>;
}
