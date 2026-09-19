import { readdir } from "node:fs/promises";
import path from "node:path";
import { CompanyDataError, getCompanyDetail } from "../services/companyData";
import { getGroupDetail, GroupDataError } from "../services/groupData";

async function main() {
  const groups = process.argv.includes("--groups");
  const directory = groups ? process.env.GROUP_ANALYSIS_DIR || path.join(process.cwd(), "public/generated/groups") : process.env.COMPANY_ANALYSIS_DIR || path.join(process.cwd(), "public/generated/companies");
  const files = (await readdir(directory)).filter((name) => name.endsWith(".json"));
  if (!files.length) throw new Error("No hay archivos JSON de análisis para validar.");
  for (const filename of files) {
    if (!(groups ? /^GROUP_\d{4,10}\.json$/ : /^COMP_\d{4,10}\.json$/).test(filename)) throw new Error(`Nombre de archivo no válido: ${filename}`);
    if (groups) {
      const group = await getGroupDetail(filename.slice(0, -5));
      if (!group) throw new Error(`Archivo no disponible: ${filename}`);
      console.log(`${filename}: contrato válido (${group.members.length} sociedades, ${group.relations.length} relaciones, ${group.recommendations.length} revisiones).`);
    } else {
      const company = await getCompanyDetail(filename.slice(0, -5));
      if (!company) throw new Error(`Archivo no disponible: ${filename}`);
      console.log(`${filename}: contrato válido (${company.history.length} meses, ${company.evidence.length} grupos de evidencia).`);
    }
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : "No se pudieron validar los datos.");
  if (error instanceof CompanyDataError || error instanceof GroupDataError) error.issues.forEach((issue) => console.error(issue));
  process.exitCode = 1;
});
