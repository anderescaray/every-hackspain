"use client";

import base from "@/components/insights/insights.module.css";

export default function GroupError({ reset }: { reset: () => void }) {
  return <main className={`${base.page} ${base.routeState}`} role="alert"><span className={base.eyebrow}>X Ray</span><h1>No se ha podido cargar el grupo</h1><p>No se muestran conclusiones mientras los datos no estén disponibles.</p><button className={base.primaryButton} onClick={reset}>Volver a intentar</button></main>;
}
