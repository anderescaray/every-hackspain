import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fixtureEnvelope } from "./pulseData";

// Publication helper only for authored loader regressions, never used at runtime.
export async function writeFixtureSnapshot(root: string, documents: Record<string, unknown>, envelope = fixtureEnvelope) {
  const directory = path.join(root, "snapshots", envelope.snapshot_id);
  await mkdir(directory, { recursive: true });
  const hashes: Record<string, string> = {};
  for (const [relative, payload] of Object.entries(documents)) {
    const content = typeof payload === "string" ? payload : JSON.stringify(payload);
    await mkdir(path.dirname(path.join(directory, relative)), { recursive: true });
    await writeFile(path.join(directory, relative), content);
    hashes[relative] = createHash("sha256").update(content).digest("hex");
  }
  const manifest = JSON.stringify({ schema_version: "1.0", ...envelope, source_manifest_sha256: "b".repeat(64), exporter_version: "pulse-frontend-v1", outputs_sha256: hashes, counts: {} });
  await writeFile(path.join(directory, "manifest.json"), manifest);
  await writeFile(path.join(root, "current.json"), JSON.stringify({ schema_version: "1.0", ...envelope, manifest_sha256: createHash("sha256").update(manifest).digest("hex") }));
  return directory;
}
