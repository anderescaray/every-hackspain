import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { after, before, test } from "node:test";
import { getGroupDetail, GroupDataError } from "../services/groupData";
import { fixtureGroups } from "./fixtures/groupDetails";

let directory: string;
const previousDirectory = process.env.GROUP_ANALYSIS_DIR;
const previousMode = process.env.COMPANY_DATA_MODE;
const payload = { ...structuredClone(fixtureGroups.GROUP_0042), source: "generated" as const };

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), "embat-group-contract-"));
  process.env.GROUP_ANALYSIS_DIR = directory;
  delete process.env.COMPANY_DATA_MODE;
});
after(async () => {
  if (previousDirectory === undefined) delete process.env.GROUP_ANALYSIS_DIR; else process.env.GROUP_ANALYSIS_DIR = previousDirectory;
  if (previousMode === undefined) delete process.env.COMPANY_DATA_MODE; else process.env.COMPANY_DATA_MODE = previousMode;
  await rm(directory, { recursive: true, force: true });
});

test("sin JSON de grupo no hay fallback ni relaciones inventadas", async () => {
  for (const id of ["GROUP_0042", "GROUP_9999", "../GROUP_0042", "constructor", "__proto__"]) assert.equal(await getGroupDetail(id), null);
});

test("los grupos usan public/generated/groups como ruta predeterminada", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "embat-group-default-"));
  const cwd = process.cwd();
  try {
    await mkdir(path.join(root, "public/generated/groups"), { recursive: true });
    await writeFile(path.join(root, "public/generated/groups/GROUP_0042.json"), JSON.stringify(payload));
    process.chdir(root);
    delete process.env.GROUP_ANALYSIS_DIR;
    assert.equal((await getGroupDetail("GROUP_0042"))?.members.length, 6);
  } finally {
    process.chdir(cwd);
    process.env.GROUP_ANALYSIS_DIR = directory;
    await rm(root, { recursive: true, force: true });
  }
});

test("relee las exportaciones y conserva los agregados del pipeline", async () => {
  await writeFile(path.join(directory, "GROUP_0042.json"), JSON.stringify(payload));
  const first = await getGroupDetail("GROUP_0042");
  assert.ok(first);
  first.available_liquidity.value = 1;
  assert.equal((await getGroupDetail("GROUP_0042"))?.available_liquidity.value, 11300000);
  const update = structuredClone(payload);
  update.available_liquidity.value = 123456;
  await writeFile(path.join(directory, "GROUP_0042.json"), JSON.stringify(update));
  assert.equal((await getGroupDetail("GROUP_0042"))?.available_liquidity.value, 123456);
});

test("rechaza JSON incompatible, IDs distintos y archivos excesivos", async () => {
  for (const value of ["{incompleto", "null", "{}", JSON.stringify({ ...payload, group_id: "GROUP_9999" }), " ".repeat(2 * 1024 * 1024 + 1)]) {
    await writeFile(path.join(directory, "GROUP_0042.json"), value);
    await assert.rejects(getGroupDetail("GROUP_0042"), GroupDataError);
  }
});

test("los fixtures de grupo solo funcionan en modo explícito", async () => {
  await writeFile(path.join(directory, "GROUP_0042.json"), JSON.stringify(fixtureGroups.GROUP_0042));
  await assert.rejects(getGroupDetail("GROUP_0042"), GroupDataError);
  process.env.COMPANY_DATA_MODE = "fixtures";
  try { assert.equal((await getGroupDetail("GROUP_0042"))?.source, "fixture"); }
  finally { delete process.env.COMPANY_DATA_MODE; }
});

test("el adaptador de grupo no importa fixtures ni genera recomendaciones", async () => {
  const source = await readFile(new URL("../services/groupData.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /import[^\n]+(?:fixtures|mock)/);
  assert.doesNotMatch(source, /calculateScore|generateRecommendation/);
});
