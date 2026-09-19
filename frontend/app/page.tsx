import { PortfolioView } from "@/components/portfolio/PortfolioView";
import { parseQuery } from "@/lib/portfolioPresentation";
import { getPortfolio, PortfolioDataError } from "@/services/portfolioData";
import base from "@/components/insights/insights.module.css";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function PortfolioPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  let portfolio;
  let invalid = false;
  try {
    portfolio = await getPortfolio();
  } catch (error) {
    if (!(error instanceof PortfolioDataError)) throw error;
    invalid = true;
  }
  if (!portfolio) {
    return <main className={`${base.page} ${base.routeState}`}>
      <span className={base.eyebrow}>Embat Pulse</span>
      <h1>{invalid ? "Los datos de cartera necesitan revisión." : "Datos de cartera todavía no disponibles."}</h1>
      <p>{invalid ? "El snapshot Pulse de cartera no cumple el contrato. No se muestran puntuaciones parciales." : "Ejecutá la exportación Pulse (scripts/09_export_frontend.py) para publicar el snapshot de cartera."}</p>
    </main>;
  }
  const page = Number.parseInt(String(Array.isArray(params.page) ? params.page[0] : params.page ?? "1"), 10);
  return <PortfolioView portfolio={portfolio} query={parseQuery(params)} page={Number.isFinite(page) ? page : 1} />;
}
