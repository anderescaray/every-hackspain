import { createHash } from "node:crypto";
import { open } from "node:fs/promises";

const MAX_ANALYSIS_BYTES = 2 * 1024 * 1024;

export async function readGeneratedAnalysis(filename: string, invalid: () => Error): Promise<{ payload: unknown; sha256: string } | null> {
  let file;
  try {
    file = await open(filename, "r");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size > MAX_ANALYSIS_BYTES) throw invalid();
    const buffer = Buffer.alloc(MAX_ANALYSIS_BYTES + 1);
    let size = 0;
    while (size <= MAX_ANALYSIS_BYTES) {
      const { bytesRead } = await file.read(buffer, size, buffer.length - size, size);
      if (bytesRead === 0) break;
      size += bytesRead;
    }
    if (size > MAX_ANALYSIS_BYTES) throw invalid();
    try {
      return { payload: JSON.parse(buffer.subarray(0, size).toString("utf8")), sha256: createHash("sha256").update(buffer.subarray(0, size)).digest("hex") };
    } catch {
      throw invalid();
    }
  } finally {
    await file.close();
  }
}
