import styles from "@/components/insights/insights.module.css";

export default function NotFound() {
  return <main className={`${styles.page} ${styles.routeState}`}><span className={styles.eyebrow}>Embat Pulse</span><h1>Página no disponible</h1><p>Abre el detalle de una empresa mediante su identificador. La navegación general se integra por separado.</p></main>;
}
