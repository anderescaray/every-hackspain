import path from "node:path";
import { companyDetailSchema, type CompanyDetail } from "../types/companyDetail";
import { readGeneratedAnalysis } from "./generatedAnalysis";

export class CompanyDataError extends Error {
  constructor(readonly issues: string[] = []) {
    super("Los datos de análisis no tienen el formato esperado.");
    this.name = "CompanyDataError";
  }
}

export async function getCompanyDetail(companyId: string): Promise<CompanyDetail | null> {
  if (!/^COMP_\d{4,10}$/.test(companyId)) return null;
  const directory = process.env.COMPANY_ANALYSIS_DIR || path.join(process.cwd(), "public", "generated", "companies");
  const file = await readGeneratedAnalysis(path.join(directory, `${companyId}.json`), () => new CompanyDataError());
  if (!file) return null;
  const parsed = companyDetailSchema.safeParse(file.payload);
  if (!parsed.success) throw new CompanyDataError(parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`));
  if (parsed.data.company_id !== companyId) throw new CompanyDataError(["company_id: no coincide con el nombre del archivo"]);
  if (parsed.data.source === "fixture" && process.env.COMPANY_DATA_MODE !== "fixtures") throw new CompanyDataError();
  return parsed.data;
}
