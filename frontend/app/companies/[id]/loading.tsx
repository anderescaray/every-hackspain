import styles from "@/components/insights/insights.module.css";

export default function CompanyLoading() {
  return <main className={`${styles.page} ${styles.routeState}`} role="status"><span className={styles.eyebrow}>Embat Pulse</span><h1>Preparando el análisis de la empresa…</h1><p>Cargando los datos y su evidencia.</p></main>;
}
