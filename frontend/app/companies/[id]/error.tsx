"use client";

import styles from "@/components/insights/insights.module.css";

export default function CompanyError({ reset }: { reset: () => void }) {
  return <main className={`${styles.page} ${styles.routeState}`} role="alert"><span className={styles.eyebrow}>X Ray</span><h1>No se ha podido cargar la empresa</h1><p>No se muestra el Health Score mientras faltan los datos.</p><button className={styles.primaryButton} onClick={reset}>Volver a intentar</button></main>;
}
