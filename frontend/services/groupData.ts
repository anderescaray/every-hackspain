import path from "node:path";
import { groupDetailSchema, type GroupDetail } from "../types/groupDetail";
import { readGeneratedAnalysis } from "./generatedAnalysis";

export class GroupDataError extends Error {
  constructor(readonly issues: string[] = []) {
    super("Los datos de análisis del grupo no tienen el formato esperado.");
    this.name = "GroupDataError";
  }
}

export async function getGroupDetail(groupId: string): Promise<GroupDetail | null> {
  if (!/^GROUP_\d{4,10}$/.test(groupId)) return null;
  const directory = process.env.GROUP_ANALYSIS_DIR || path.join(process.cwd(), "public", "generated", "groups");
  const file = await readGeneratedAnalysis(path.join(directory, `${groupId}.json`), () => new GroupDataError());
  if (!file) return null;
  const parsed = groupDetailSchema.safeParse(file.payload);
  if (!parsed.success) throw new GroupDataError(parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`));
  if (parsed.data.group_id !== groupId) throw new GroupDataError(["group_id: no coincide con el nombre del archivo"]);
  if (parsed.data.source === "fixture" && process.env.COMPANY_DATA_MODE !== "fixtures") throw new GroupDataError();
  return parsed.data;
}
