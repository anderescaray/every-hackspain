import Link from "next/link";
import styles from "@/components/insights/insights.module.css";

export default function CompanyNotFound() {
  return (
    <main className={`${styles.page} ${styles.routeState}`}>
      <span className={styles.eyebrow}>Embat Pulse · Company detail</span>
      <h1>Company not available</h1>
      <p>This ID is not included in the prepared demo data. No financial conclusion can be drawn from missing data.</p>
      <Link className={styles.primaryButton} href="/companies/COMP_0356">Open the Cash Truth demo</Link>
    </main>
  );
}
