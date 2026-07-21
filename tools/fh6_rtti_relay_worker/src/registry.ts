import { canonicalJson, sha256Hex } from "./protocol";

export const REGISTRY_FORMAT = "kfps_fh6_rtti_registry_v1";
export const EXPECTED_COUNTS = [3000, 2997, 2994, 2991, 2988, 2985];
export const MAX_PROFILES = 64;

export interface NormalizedProfile {
  game: "fh6";
  module_size: number;
  descriptor_offset: number;
  vtable_offsets: number[];
  update_code: string;
  base_class_count: number;
  game_build: string;
  created_utc: string;
  calibrator_version: string;
  evidence: {
    workflow: string;
    confidence: string;
    scan_count: number;
    distinct_counts: number[];
  };
  profile_id: string;
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be an object`);
  return value as Record<string, unknown>;
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) throw new Error(`${label} must be an integer`);
  return value;
}

function text(value: unknown, label: string, maximum: number, required = false): string {
  const result = String(value ?? "").trim();
  if (required && !result) throw new Error(`${label} is required`);
  if (result.length > maximum) throw new Error(`${label} is too long`);
  return result;
}

function updateCode(value: unknown): string {
  const result = text(value, "update_code", 128, true);
  if (!/^[!-~]+$/.test(result)) throw new Error("update_code contains unsupported characters");
  return result;
}

export async function normalizeProfile(raw: unknown, requireComplete: boolean): Promise<NormalizedProfile> {
  const input = record(raw, "profile");
  if (text(input.game ?? "fh6", "game", 16, true).toLowerCase() !== "fh6") {
    throw new Error("only FH6 profiles are supported");
  }
  const moduleSize = integer(input.module_size, "module_size");
  if (moduleSize < 1024 * 1024 || moduleSize > 1024 * 1024 * 1024) throw new Error("module_size is outside the supported range");
  const descriptorOffset = integer(input.descriptor_offset, "descriptor_offset");
  if (descriptorOffset <= 0 || descriptorOffset >= moduleSize) throw new Error("descriptor_offset must be inside the main module");
  if (!Array.isArray(input.vtable_offsets) || input.vtable_offsets.length < 1 || input.vtable_offsets.length > 16) {
    throw new Error("vtable_offsets is invalid");
  }
  const vtableOffsets = [...new Set(input.vtable_offsets.map((value) => integer(value, "vtable_offset")))].sort((a, b) => a - b);
  if (vtableOffsets.some((value) => value <= 0 || value >= moduleSize)) throw new Error("vtable offset must be inside the main module");
  const baseClassCount = integer(input.base_class_count ?? 0, "base_class_count");
  if (baseClassCount < 0 || baseClassCount > 64) throw new Error("base_class_count is outside the supported range");
  const evidenceInput = record(input.evidence ?? {}, "evidence");
  if (!Array.isArray(evidenceInput.distinct_counts) || evidenceInput.distinct_counts.length > 32) {
    throw new Error("evidence distinct_counts is invalid");
  }
  const counts = [...new Set(evidenceInput.distinct_counts.map((value) => integer(value, "evidence count")))].sort((a, b) => b - a);
  if (counts.some((value) => value < 0 || value > 3000)) throw new Error("evidence contains an invalid FH6 layer count");
  const scanCount = integer(evidenceInput.scan_count ?? counts.length, "evidence scan_count");
  if (scanCount < counts.length || scanCount > 256) throw new Error("evidence scan_count is invalid");
  const confidence = text(evidenceInput.confidence ?? "unknown", "evidence confidence", 32, true).toLowerCase();
  if (!["unknown", "legacy", "medium", "high", "very_high"].includes(confidence)) throw new Error("evidence confidence is unsupported");
  const workflow = text(evidenceInput.workflow, "evidence workflow", 64);
  if (requireComplete) {
    if (workflow !== "six_step_template_calibration") throw new Error("only six-step calibration profiles can be submitted");
    if (!(["high", "very_high"].includes(confidence))) throw new Error("calibration profile is not high confidence");
    if (scanCount < 6 || canonicalJson(counts) !== canonicalJson(EXPECTED_COUNTS)) throw new Error("calibration profile is missing one or more independent layer counts");
  }
  const partial = {
    game: "fh6" as const,
    module_size: moduleSize,
    descriptor_offset: descriptorOffset,
    vtable_offsets: vtableOffsets,
    update_code: updateCode(input.update_code),
    base_class_count: baseClassCount,
    game_build: text(input.game_build, "game_build", 64),
    created_utc: text(input.created_utc, "created_utc", 40),
    calibrator_version: text(input.calibrator_version, "calibrator_version", 32),
    evidence: { workflow, confidence, scan_count: scanCount, distinct_counts: counts },
  };
  const identity = {
    game: "fh6",
    module_size: partial.module_size,
    descriptor_offset: partial.descriptor_offset,
    vtable_offsets: partial.vtable_offsets,
    update_code: partial.update_code,
  };
  const profileId = `fh6-${(await sha256Hex(new TextEncoder().encode(canonicalJson(identity)))).slice(0, 20)}`;
  return { ...partial, profile_id: profileId };
}

export async function normalizeRegistry(raw: unknown): Promise<{ format: string; updated_utc: string; profiles: NormalizedProfile[] }> {
  const input = record(raw, "registry");
  if (input.format !== REGISTRY_FORMAT || !Array.isArray(input.profiles) || input.profiles.length > MAX_PROFILES) {
    throw new Error("registry format or profile list is invalid");
  }
  const seen = new Set<string>();
  const profiles: NormalizedProfile[] = [];
  for (const rawProfile of input.profiles) {
    const profile = await normalizeProfile(rawProfile, false);
    if (!seen.has(profile.profile_id)) {
      seen.add(profile.profile_id);
      profiles.push(profile);
    }
  }
  return { format: REGISTRY_FORMAT, updated_utc: text(input.updated_utc, "updated_utc", 40), profiles };
}
