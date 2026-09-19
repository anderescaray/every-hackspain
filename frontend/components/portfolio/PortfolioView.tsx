import Link from "next/link";
import type { Portfolio } from "@/types/portfolio";
import { trajectoryLabels, confidenceLabel, numberLabel } from "@/lib/companyFormat";
import { attentionLabels, filterItems, sortItems, sortLabels, statusLabels, summarize, SORT_KEYS, type PortfolioQuery } from "@/lib/portfolioPresentation";
import base from "@/components/insights/insights.module.css";
import styles from "./portfolio.module.css";

const PAGE_SIZE = 100;

function Kpi({ label, value, hint }: { label: string; value: number; hint: string }) {
  return <div className={styles.kpi}><span className={base.eyebrow}>{label}</span><strong>{numberLabel(value, 0)}</strong><small>{hint}</small></div>;
}

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className={styles.muted}>—</span>;
  const sign = value > 0.05 ? "+" : "";
  const tone = value > 0.05 ? styles.positive : value < -0.05 ? styles.negative : "";
  return <span className={tone}>{sign}{numberLabel(value, 1)}</span>;
}

export function PortfolioView({ portfolio, query, page }: { portfolio: Portfolio; query: PortfolioQuery; page: number }) {
  const totals = summarize(portfolio);
  const filtered = sortItems(filterItems(portfolio.items, query), query.sort, query.order);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(Math.max(1, page), pages);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const pageHref = (n: number) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) if (value && value !== "all") params.set(key, String(value));
    if (n > 1) params.set("page", String(n));
    const encoded = params.toString();
    return encoded ? `/?${encoded}` : "/";
  };

  return <main className={`${base.page} ${styles.portfolio}`}>
    <header className={styles.header}>
      <div>
        <span className={base.eyebrow}>Embat Pulse · Cartera</span>
        <h1>¿Qué empresas necesitan atención?</h1>
        <p>{portfolio.summary}</p>
      </div>
      <span className={base.periodBadge}>Corte {portfolio.as_of} · {portfolio.period}</span>
    </header>

    <section className={styles.kpis} aria-label="Resumen de la cartera">
      <Kpi label="Empresas" value={totals.total} hint={`${numberLabel(totals.scored, 0)} con Health Score`} />
      <Kpi label="Atención alta" value={totals.highAttention} hint="Prioridad recibida; sin evidencia no se asigna" />
      <Kpi label="Deteriorándose" value={totals.deteriorating} hint="Trayectoria observada, no pronóstico" />
      <Kpi label="Mejorando" value={totals.improving} hint="Trayectoria observada, no pronóstico" />
      <Kpi label="Dependen de apoyo" value={totals.dependent} hint="Sólo con evidencia de apoyo identificado" />
    </section>

    <form className={styles.filters} method="get" action="/" aria-label="Filtros de la cartera">
      <label>Trayectoria<select name="trajectory" defaultValue={query.trajectory}><option value="all">Todas</option>{(["deteriorating", "improving", "stable"] as const).map((v) => <option key={v} value={v}>{trajectoryLabels[v]}</option>)}</select></label>
      <label>Atención<select name="attention" defaultValue={query.attention}><option value="all">Todas</option>{(["high", "medium", "low", "unknown"] as const).map((v) => <option key={v} value={v}>{attentionLabels[v]}</option>)}</select></label>
      <label>Estado<select name="status" defaultValue={query.status}><option value="all">Todos</option>{(["complete", "complete_verified", "complete_bounded", "partial", "insufficient_evidence"] as const).map((v) => <option key={v} value={v}>{statusLabels[v]}</option>)}</select></label>
      <label>Grupo<input name="group" defaultValue={query.group} placeholder="GROUP_0042" maxLength={40} /></label>
      <label>Buscar<input name="q" defaultValue={query.q} placeholder="COMP_0356" maxLength={40} /></label>
      <label>Ordenar por<select name="sort" defaultValue={query.sort}>{SORT_KEYS.map((k) => <option key={k} value={k}>{sortLabels[k]}</option>)}</select></label>
      <label>Orden<select name="order" defaultValue={query.order}><option value="desc">Descendente</option><option value="asc">Ascendente</option></select></label>
      <button type="submit">Aplicar</button>
      <Link href="/" className={styles.reset}>Limpiar</Link>
    </form>

    <section aria-label="Empresas" className={styles.tableSection}>
      <div className={styles.tableMeta}><span>{numberLabel(filtered.length, 0)} empresas · página {current} de {pages}</span><span className={styles.muted}>Los valores nulos significan «no evaluable», nunca cero.</span></div>
      <div className={base.tableScroll}>
        <table className={styles.table}>
          <thead><tr><th scope="col">Empresa</th><th scope="col">Grupo</th><th scope="col">Health Score</th><th scope="col">Δ mes</th><th scope="col">Trayectoria</th><th scope="col">Atención</th><th scope="col">Señal principal</th><th scope="col">Apoyo</th><th scope="col">Cobertura</th><th scope="col">Estado</th></tr></thead>
          <tbody>
            {rows.map((item) => <tr key={item.company_id} data-attention={item.attention}>
              <th scope="row">{item.has_detail ? <Link href={`/companies/${item.company_id}`} className={styles.companyLink}>{item.company_id}</Link> : <span>{item.company_id}</span>}</th>
              <td>{item.group_id ? <Link href={`/groups/${item.group_id}`} className={styles.groupLink}>{item.group_id}</Link> : <span className={styles.muted}>Independiente</span>}</td>
              <td className={styles.score}>{item.health_score === null ? <span className={styles.muted}>No plenamente identificada</span> : <strong>{numberLabel(item.health_score, 2)}</strong>}</td>
              <td><Delta value={item.delta_vs_prev} /></td>
              <td>{item.trajectory ? <span className={`${styles.badge} ${base[item.trajectory]}`}>{trajectoryLabels[item.trajectory]}{item.trajectory_stage === "emerging" ? " · emergente" : ""}</span> : <span className={styles.muted}>Sin evaluar</span>}</td>
              <td><span className={`${styles.attention} ${styles[item.attention]}`}>{attentionLabels[item.attention]}</span></td>
              <td className={styles.signal}>{item.main_signal ? <>{item.main_signal}{item.main_signal_impact !== null ? <small> ({item.main_signal_impact > 0 ? "+" : ""}{numberLabel(item.main_signal_impact, 1)} pts)</small> : null}</> : <span className={styles.muted}>—</span>}</td>
              <td>{item.support_dependency_ratio === null ? <span className={styles.muted}>—</span> : `${numberLabel(item.support_dependency_ratio * 100, 0)} %`}</td>
              <td>{item.confidence === null ? <span className={styles.muted}>No evaluable</span> : `${confidenceLabel(item.confidence)} · ${numberLabel(item.confidence, 0)}`}</td>
              <td><span className={styles.status}>{statusLabels[item.score_status]}</span>{item.status_reason && item.score_status !== "complete" ? <small className={styles.reason}>{item.status_reason}</small> : null}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
      {pages > 1 ? <nav className={styles.pagination} aria-label="Paginación">{current > 1 ? <Link href={pageHref(current - 1)}>← Anterior</Link> : <span />}{current < pages ? <Link href={pageHref(current + 1)}>Siguiente →</Link> : <span />}</nav> : null}
    </section>
    <footer className={styles.footer}><small>Health Score, trayectoria y cobertura los calcula el pipeline de datos; esta vista solo filtra y ordena. {portfolio.score_version} · Run {portfolio.run_id}. No es una probabilidad de impago.</small></footer>
  </main>;
}
