import path from "node:path";
import { lstat, realpath } from "node:fs/promises";
import { cache } from "react";
import { z } from "zod";
import { envelopeKeys, pulseEnvelopeShape, pulseEnvelopeSchema } from "../types/pulse";
import { readGeneratedAnalysis } from "./generatedAnalysis";

const sha = z.string().regex(/^[a-f0-9]{64}$/);
const pointerSchema = z.object({ schema_version: z.literal("1.0"), ...pulseEnvelopeShape, manifest_sha256: sha }).strict();
const manifestSchema = z.object({ schema_version: z.literal("1.0"), ...pulseEnvelopeShape, source_manifest_sha256: sha, exporter_version: z.enum(["pulse-frontend-v1", "pulse-frontend-v1.1"]), outputs_sha256: z.record(sha), counts: z.record(z.unknown()) }).passthrough();
class SnapshotError extends Error {}
const invalid = () => new SnapshotError("Snapshot Pulse ausente, mezclado o sin integridad.");

async function safePath(root: string, relative: string) {
  const file = path.join(root, relative);
  const parts = relative.split("/");
  if (parts.some((part) => !part || part === "." || part === "..") || path.isAbsolute(relative)) throw invalid();
  let segment = root;
  for (const part of parts) {
    segment = path.join(segment, part);
    if ((await lstat(segment)).isSymbolicLink()) throw invalid();
  }
  const resolved = await realpath(file);
  if (!resolved.startsWith(`${root}${path.sep}`)) throw invalid();
  return resolved;
}

// React cache is request-scoped in Server Components, not a process-wide stale cache.
const getSnapshot = cache(async () => {
  const configured = process.env.PULSE_GENERATED_DIR;
  if (configured && !path.isAbsolute(configured)) throw invalid();
  const directory = configured || path.join(process.cwd(), "public", "generated");
  let root;
  try {
    if ((await lstat(directory)).isSymbolicLink()) throw invalid();
    root = await realpath(directory);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  let pointerPath;
  try { pointerPath = await safePath(root, "current.json"); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return null; throw error; }
  const raw = await readGeneratedAnalysis(pointerPath, invalid);
  if (!raw) return null;
  const parsed = pointerSchema.safeParse(raw.payload);
  if (!parsed.success) throw invalid();
  const pointer = parsed.data;
  const manifestPath = await safePath(root, `snapshots/${pointer.snapshot_id}/manifest.json`);
  const manifestFile = await readGeneratedAnalysis(manifestPath, invalid);
  if (!manifestFile || manifestFile.sha256 !== pointer.manifest_sha256) throw invalid();
  const manifestResult = manifestSchema.safeParse(manifestFile.payload);
  if (!manifestResult.success) throw invalid();
  const manifest = manifestResult.data;
  if (envelopeKeys.some((key) => manifest[key] !== pointer[key])) throw invalid();
  return { root, pointer, manifest };
});

export async function readPulseDocument(relative: string, makeError: () => Error) {
  try {
    const snapshot = await getSnapshot();
    if (!snapshot) return null;
    const expectedHash = snapshot.manifest.outputs_sha256[relative];
    // Not in this generation means unavailable, never a stale loose-file fallback.
    if (!expectedHash) return null;
    const filename = await safePath(snapshot.root, `snapshots/${snapshot.pointer.snapshot_id}/${relative}`);
    const document = await readGeneratedAnalysis(filename, invalid);
    if (!document || document.sha256 !== expectedHash) throw invalid();
    const envelope = pulseEnvelopeSchema.safeParse(document.payload);
    if (!envelope.success || envelopeKeys.some((key) => envelope.data[key] !== snapshot.pointer[key])) throw invalid();
    return document;
  } catch {
    throw makeError();
  }
}
