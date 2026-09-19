import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { after, before, test } from "node:test";
import { getGroupDetail, GroupDataError } from "../services/groupData";
import { fixtureGroups } from "./fixtures/groupDetails";
import { writeFixtureSnapshot } from "./fixtures/snapshot";

let directory: string;
const previous = process.env.PULSE_GENERATED_DIR;
const payload = { ...structuredClone(fixtureGroups.GROUP_0042), source: "generated" as const };
before(async () => { directory = await mkdtemp(path.join(os.tmpdir(), "pulse-group-contract-")); process.env.PULSE_GENERATED_DIR = directory; });
after(async () => { if (previous === undefined) delete process.env.PULSE_GENERATED_DIR; else process.env.PULSE_GENERATED_DIR = previous; await rm(directory, { recursive: true, force: true }); });

test("sin snapshot no hay fallback ni conexiones inventadas", async () => {
  for (const id of ["GROUP_0042", "GROUP_9999", "../GROUP_0042"]) assert.equal(await getGroupDetail(id), null);
});
test("grupo conserva null agregado y mismo run que el puntero", async () => {
  await writeFixtureSnapshot(directory, { "groups/GROUP_0042.json": payload });
  const group = await getGroupDetail("GROUP_0042");
  assert.ok(group);
  assert.equal(group.health_score, null);
  assert.equal(group.status, "insufficient_evidence");
  assert.equal(group.run_id, payload.run_id);
});
test("rechaza grupo de otro run, metodología o score consolidado inventado", async () => {
  for (const value of [{ ...payload, run_id: "other-run" }, { ...payload, score_version: "financial_smoothed_v2" }, { ...payload, health_score: 70 }]) {
    await writeFixtureSnapshot(directory, { "groups/GROUP_0042.json": value });
    await assert.rejects(getGroupDetail("GROUP_0042"), GroupDataError);
  }
});
