import Link from "next/link";
import styles from "@/components/insights/insights.module.css";

export default function CompanyNotFound() {
  return (
    <main className={`${styles.page} ${styles.routeState}`}>
      <span className={styles.eyebrow}>Embat Pulse</span>
      <h1>Empresa no disponible</h1>
      <p>El identificador no tiene el formato esperado.</p>
      <Link className={styles.primaryButton} href="/companies/COMP_0356">Abrir COMP_0356</Link>
    </main>
  );
}
