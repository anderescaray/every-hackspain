"use client";

import styles from "@/components/insights/insights.module.css";

export default function CompanyError({ reset }: { reset: () => void }) {
  return <main className={`${styles.page} ${styles.routeState}`} role="alert"><span className={styles.eyebrow}>Embat Pulse</span><h1>No se ha podido cargar el análisis</h1><p>No se muestran Operating ni Extended Health mientras los datos de la empresa no estén disponibles.</p><button className={styles.primaryButton} onClick={reset}>Volver a intentar</button></main>;
}
