import path from "node:path";
import { portfolioSchema, type Portfolio } from "../types/portfolio";
import { readGeneratedAnalysis } from "./generatedAnalysis";

export class PortfolioDataError extends Error {
  constructor(readonly issues: string[] = []) {
    super("Los datos de cartera no tienen el formato esperado.");
    this.name = "PortfolioDataError";
  }
}

export async function getPortfolio(): Promise<Portfolio | null> {
  const file = process.env.PORTFOLIO_ANALYSIS_FILE || path.join(process.cwd(), "public", "generated", "portfolio.json");
  const read = await readGeneratedAnalysis(file, () => new PortfolioDataError());
  if (!read) return null;
  const parsed = portfolioSchema.safeParse(read.payload);
  if (!parsed.success) throw new PortfolioDataError(parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`));
  if (parsed.data.source === "fixture" && process.env.COMPANY_DATA_MODE !== "fixtures") throw new PortfolioDataError();
  return parsed.data;
}
