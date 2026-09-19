import styles from "@/components/insights/insights.module.css";

export default function CompanyLoading() {
  return <main className={`${styles.page} ${styles.routeState}`} role="status"><span className={styles.eyebrow}>Embat Pulse</span><h1>Cargando empresa…</h1><p>Datos y evidencia.</p></main>;
}
