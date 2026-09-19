import styles from "./insights.module.css";

export function CompanyDataState({ companyId, invalid = false }: { companyId: string; invalid?: boolean }) {
  return <main className={`${styles.page} ${styles.routeState}`}>
    <span className={styles.eyebrow}>Embat Pulse · Análisis de empresa</span>
    <h1>{invalid ? "Los datos de análisis necesitan revisión." : "Datos de análisis todavía no disponibles."}</h1>
    <p>{companyId} · {invalid ? "El archivo recibido no cumple el formato esperado. No se mostrarán puntuaciones ni conclusiones hasta disponer de datos válidos." : "El análisis aparecerá cuando el equipo de datos publique el archivo de esta empresa. No se han generado resultados de ejemplo."}</p>
    <a className={styles.primaryButton} href={`/companies/${companyId}`}>Volver a comprobar</a>
  </main>;
}
