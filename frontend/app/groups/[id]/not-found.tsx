import base from "@/components/insights/insights.module.css";

export default function GroupNotFound() {
  return <main className={`${base.page} ${base.routeState}`}><span className={base.eyebrow}>X Ray</span><h1>Grupo no disponible</h1><p>El identificador no tiene el formato esperado.</p></main>;
}
