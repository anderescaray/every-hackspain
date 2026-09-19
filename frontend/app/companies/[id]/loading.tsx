import styles from "@/components/insights/insights.module.css";

export default function CompanyLoading() {
  return <main className={`${styles.page} ${styles.routeState}`} role="status"><span className={styles.eyebrow}>Embat Pulse</span><h1>Preparing company insights…</h1><p>Loading the company snapshot and its evidence.</p></main>;
}
