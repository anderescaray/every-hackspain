import Link from "next/link";
import styles from "@/components/insights/insights.module.css";

export default function CompanyNotFound() {
  return (
    <main className={`${styles.page} ${styles.routeState}`}>
      <span className={styles.eyebrow}>Embat Pulse · Detalle de empresa</span>
      <h1>Empresa no disponible</h1>
      <p>El identificador de empresa no tiene el formato esperado. La falta de datos no permite extraer conclusiones financieras.</p>
      <Link className={styles.primaryButton} href="/companies/COMP_0356">Abrir el detalle de COMP_0356</Link>
    </main>
  );
}
