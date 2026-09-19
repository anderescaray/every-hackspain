"use client";

import styles from "@/components/insights/insights.module.css";

export default function CompanyError({ reset }: { reset: () => void }) {
  return <main className={`${styles.page} ${styles.routeState}`} role="alert"><span className={styles.eyebrow}>Embat Pulse</span><h1>Insights could not be loaded</h1><p>No scores are shown while the company data is unavailable.</p><button className={styles.primaryButton} onClick={reset}>Try again</button></main>;
}
