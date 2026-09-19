import { open } from "node:fs/promises";
import path from "node:path";
import { companyDetailSchema, type CompanyDetail } from "../types/companyDetail";

const MAX_ANALYSIS_BYTES = 2 * 1024 * 1024;

export class CompanyDataError extends Error {
  constructor(readonly issues: string[] = []) {
    super("Los datos de análisis no tienen el formato esperado.");
    this.name = "CompanyDataError";
  }
}

export async function getCompanyDetail(companyId: string): Promise<CompanyDetail | null> {
  if (!/^COMP_\d{4,10}$/.test(companyId)) return null;
  const directory = process.env.COMPANY_ANALYSIS_DIR || path.join(process.cwd(), "public", "generated", "companies");
  let file;
  try {
    file = await open(path.join(directory, `${companyId}.json`), "r");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size > MAX_ANALYSIS_BYTES) throw new CompanyDataError();
    const buffer = Buffer.alloc(MAX_ANALYSIS_BYTES + 1);
    let size = 0;
    while (size <= MAX_ANALYSIS_BYTES) {
      const { bytesRead } = await file.read(buffer, size, buffer.length - size, size);
      if (bytesRead === 0) break;
      size += bytesRead;
    }
    if (size > MAX_ANALYSIS_BYTES) throw new CompanyDataError();
    let payload: unknown;
    try {
      payload = JSON.parse(buffer.subarray(0, size).toString("utf8"));
    } catch {
      throw new CompanyDataError();
    }
    const parsed = companyDetailSchema.safeParse(payload);
    if (!parsed.success) throw new CompanyDataError(parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`));
    if (parsed.data.company_id !== companyId) throw new CompanyDataError(["company_id: no coincide con el nombre del archivo"]);
    if (parsed.data.source === "fixture" && process.env.COMPANY_DATA_MODE !== "fixtures") throw new CompanyDataError();
    return parsed.data;
  } finally {
    await file.close();
  }
}
