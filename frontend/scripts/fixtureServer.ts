import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fixtureCompanies } from "../tests/fixtures/companyDetails";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureGroups, groupCompanyFixtures } from "../tests/fixtures/groupDetails";
import { groupDetailSchema } from "../types/groupDetail";

async function main() {
  const [mode, ...args] = process.argv.slice(2);
  if (!["dev", "start", "empty"].includes(mode)) throw new Error("Modo de pruebas no válido.");
  const directory = await mkdtemp(path.join(os.tmpdir(), "embat-analysis-fixtures-"));
  try {
    const companyDirectory = path.join(directory, "companies");
    const groupDirectory = path.join(directory, "groups");
    await Promise.all([mkdir(companyDirectory), mkdir(groupDirectory)]);
    if (mode !== "empty") {
      for (const company of Object.values({ ...fixtureCompanies, ...groupCompanyFixtures })) {
        await writeFile(path.join(companyDirectory, `${company.company_id}.json`), JSON.stringify(companyDetailSchema.parse(company)));
      }
      for (const group of Object.values(fixtureGroups)) {
        await writeFile(path.join(groupDirectory, `${group.group_id}.json`), JSON.stringify(groupDetailSchema.parse(group)));
      }
      await writeFile(path.join(companyDirectory, "COMP_9998.json"), "{datos incompletos");
      await writeFile(path.join(groupDirectory, "GROUP_9998.json"), "{datos incompletos");
    }
    const require = createRequire(import.meta.url);
    const child = spawn(process.execPath, [require.resolve("next/dist/bin/next"), mode === "dev" ? "dev" : "start", ...args], {
      stdio: "inherit",
      env: { ...process.env, COMPANY_ANALYSIS_DIR: companyDirectory, GROUP_ANALYSIS_DIR: groupDirectory, COMPANY_DATA_MODE: mode === "empty" ? "generated" : "fixtures" },
    });
    const stop = () => child.kill("SIGTERM");
    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
    try {
      process.exitCode = await new Promise<number>((resolve, reject) => {
        child.once("error", reject);
        child.once("exit", (code) => resolve(code ?? 0));
      });
    } finally {
      process.off("SIGINT", stop);
      process.off("SIGTERM", stop);
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

main().catch((error: unknown) => { console.error(error instanceof Error ? error.message : "No se pudo iniciar el entorno de pruebas."); process.exitCode = 1; });
