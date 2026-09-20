import base from "@/components/insights/insights.module.css";

export default function LoadingGroup() {
  return <main className={`${base.page} ${base.routeState}`} role="status"><span className={base.eyebrow}>X Ray</span><h1>Cargando grupo…</h1><p>Sociedades, relaciones y revisiones.</p></main>;
}
