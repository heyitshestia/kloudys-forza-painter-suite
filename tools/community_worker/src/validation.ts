import { base64ToBytes, HttpError, plainText, sha256Hex } from "./security";
import type { ArtworkClassification, CanonicalDesign, CanonicalShape, DetectedSchema, ValidatedUpload } from "./types";

export const CATEGORIES = [
  "Characters", "Motorsport", "Logos", "Gaming", "Abstract",
  "Patterns", "Humor", "Original Artwork", "Other",
] as const;
export const GAMES = ["FH5", "FH6", "FM8"] as const;
export const LICENSES = ["kfps-community-share-v1", "cc-by-4.0", "cc-by-nc-4.0", "cc0-1.0"] as const;
export const CLASSIFICATIONS = ["handmade", "toolmade"] as const;

const MAX_DESIGN_BYTES = 24 * 1024 * 1024;
export const MAX_PREVIEW_BYTES = 2 * 1024 * 1024;
export const MAX_THUMBNAIL_BYTES = 512 * 1024;
const MAX_SHAPES = 3001;
const FORBIDDEN_KEYS = new Set(["__proto__", "prototype", "constructor"]);
const SHAPE_KEYS = new Set([
  "type", "type_word", "typeWord", "shape_word", "shapeWord", "data", "color", "score",
  "mask", "is_mask", "isMask", "resource_family", "resource_index", "source_format",
]);
const PRIMITIVE_TYPES = new Set([1, 2, 8, 16]);
const KNOWN_FORMATS: Record<string, { id: string; label: string; games?: string[] }> = {
  "kfps.community.v1": { id: "kfps-community", label: "KFPS Community JSON" },
  "kfps.primitive.v1": { id: "kfps-primitives", label: "KFPS primitive geometry" },
  "fh6_typecode_json_export_v1": { id: "forza-typecode-export", label: "Forza live type-code export" },
  "kfps_forza_save_library_json_v1": { id: "forza-save-library", label: "KFPS Forza save-library export" },
  "kfps_forza_file_export_json_v1": { id: "forza-file-export", label: "KFPS decoded Forza file export" },
  "kfps_cgroup_flat_json_v1": { id: "kfps-cgroup-flat", label: "KFPS flat C_group JSON" },
  "kfps.fd6.converted.v1": { id: "fd6-converted", label: "Forza Designer 6 conversion", games: ["FH6"] },
};

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function normalizedGame(value: unknown): string {
  const key = String(value || "").trim().toLocaleLowerCase("en-US").replace(/[^a-z0-9]/g, "");
  if (["fh5", "forzahorizon5", "horizon5"].includes(key)) return "FH5";
  if (["fh6", "forzahorizon6", "horizon6"].includes(key)) return "FH6";
  if (["fm", "fm8", "forzamotorsport", "forzamotorsport8", "motorsport"].includes(key)) return "FM8";
  return "";
}

function gameOrigins(value: unknown): string[] {
  const root = objectValue(value);
  const metadata = objectValue(root.metadata);
  const source = objectValue(root.source);
  const candidates: unknown[] = [
    root.target_game, root.game, metadata.target_game, metadata.game, source.target_game, source.game,
  ];
  for (const container of [root, metadata, source]) {
    if (Array.isArray(container.detected_games)) candidates.push(...container.detected_games);
    if (Array.isArray(container.games)) candidates.push(...container.games);
  }
  const games = candidates.map(normalizedGame).filter(Boolean);
  return [...new Set(games)];
}

export function detectDesignSchema(value: unknown, shapes: unknown[]): DetectedSchema {
  const root = objectValue(value);
  const format = String(root.format || "").trim().toLocaleLowerCase("en-US");
  const games = gameOrigins(value);
  const known = KNOWN_FORMATS[format];
  if (known) {
    for (const game of known.games || []) if (!games.includes(game)) games.push(game);
    if (format === "fh6_typecode_json_export_v1" && games.length === 0) games.push("FH6");
    return { id: known.id, label: known.label, known: true, games };
  }

  const shapeRows = shapes.map(objectValue);
  const sourceFormats = new Set(shapeRows.map((shape) => String(shape.source_format || "").trim().toLocaleLowerCase("en-US")));
  const fh6TypeCodes = sourceFormats.has("fh6_typecode");
  const typeCodeGeometry = shapeRows.some((shape) =>
    Number(shape.type || 0) > 1_000_000
    || shape.type_word != null || shape.typeWord != null || shape.shape_word != null || shape.shapeWord != null
    || shape.resource_family != null || shape.resource_index != null
  );
  const primitiveGeometry = shapeRows.length > 0 && shapeRows.every((shape) =>
    PRIMITIVE_TYPES.has(Number(shape.type)) && Array.isArray(shape.data) && Array.isArray(shape.color)
  );

  if (format) {
    const safeFormat = /^[a-z0-9._-]{1,64}$/.test(format) ? format : "unrecognized";
    return {
      id: "unrecognized",
      label: safeFormat === "unrecognized" ? "Unrecognized JSON format" : `Unrecognized format: ${safeFormat}`,
      known: false,
      games,
    };
  }
  if (fh6TypeCodes) {
    if (!games.includes("FH6")) games.push("FH6");
    return { id: "fh6-typecode", label: "FH6 type-code geometry", known: true, games };
  }
  if (typeCodeGeometry) {
    return { id: "forza-typecode", label: "Forza type-code geometry", known: true, games };
  }
  if (primitiveGeometry) {
    return { id: "kfps-primitives", label: "KFPS primitive geometry", known: true, games };
  }
  return { id: "unrecognized", label: "Unrecognized compatible shape list", known: false, games };
}

function finiteNumber(value: unknown, field: string, minimum: number, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new HttpError(400, "invalid_design", `${field} contains an invalid number.`);
  }
  return value;
}

function integer(value: unknown, field: string, minimum: number, maximum: number): number {
  const number = finiteNumber(value, field, minimum, maximum);
  if (!Number.isInteger(number)) throw new HttpError(400, "invalid_design", `${field} must be an integer.`);
  return number;
}

function checkedArray(value: unknown, field: string, minimum: number, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    throw new HttpError(400, "invalid_design", `${field} has an invalid length.`);
  }
  return value;
}

function canonicalShape(value: unknown, index: number): CanonicalShape {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new HttpError(400, "invalid_design", `Shape ${index + 1} is not an object.`);
  }
  const source = value as Record<string, unknown>;
  for (const key of Object.keys(source)) {
    if (FORBIDDEN_KEYS.has(key)) throw new HttpError(400, "invalid_design", "The design contains a forbidden key.");
  }
  const type = integer(source.type, `shape ${index + 1} type`, 0, 2_000_000);
  const data = checkedArray(source.data, `shape ${index + 1} data`, 4, 12)
    .map((item) => finiteNumber(item, `shape ${index + 1} data`, -1_000_000, 1_000_000));
  const color = checkedArray(source.color, `shape ${index + 1} color`, 3, 4)
    .map((item) => finiteNumber(item, `shape ${index + 1} color`, 0, 255));
  if (color.length === 3) color.push(255);
  const shape: CanonicalShape = { type, data, color };
  const mask = source.mask ?? source.is_mask ?? source.isMask;
  if (mask != null) {
    if (typeof mask === "boolean") shape.mask = mask;
    else if (mask === 0 || mask === 1) shape.mask = Boolean(mask);
    else throw new HttpError(400, "invalid_design", `Shape ${index + 1} has an invalid mask flag.`);
  }
  const word = source.type_word ?? source.typeWord ?? source.shape_word ?? source.shapeWord;
  if (word != null) shape.type_word = integer(word, `shape ${index + 1} type word`, 0, 65535);
  if (source.resource_family != null) shape.resource_family = plainText(source.resource_family, "resource_family", 64, true);
  if (source.resource_index != null) shape.resource_index = integer(source.resource_index, "resource_index", 1, 1000);
  if (source.source_format != null) shape.source_format = plainText(source.source_format, "source_format", 48, true);
  for (const key of Object.keys(source)) {
    if (!SHAPE_KEYS.has(key)) continue;
  }
  return shape;
}

function extractShapes(design: unknown): { shapes: unknown[]; sourceFormat: string; groupCount: number } {
  if (Array.isArray(design)) return { shapes: design, sourceFormat: "array", groupCount: 0 };
  if (!design || typeof design !== "object") throw new HttpError(400, "invalid_design");
  const value = design as Record<string, unknown>;
  for (const key of Object.keys(value)) {
    if (FORBIDDEN_KEYS.has(key)) throw new HttpError(400, "invalid_design", "The design contains a forbidden key.");
  }
  for (const key of ["shapes", "layers", "items"]) {
    if (Array.isArray(value[key])) {
      const metadata = value.metadata;
      const groups = metadata && typeof metadata === "object" && !Array.isArray(metadata)
        ? Number((metadata as Record<string, unknown>).group_count || 0) : 0;
      return {
        shapes: value[key] as unknown[],
        sourceFormat: plainText(value.format, "format", 64, false) || key,
        groupCount: Number.isInteger(groups) && groups >= 0 && groups <= 3001 ? groups : 0,
      };
    }
  }
  throw new HttpError(400, "invalid_design", "The JSON does not contain a supported shape list.");
}

function canonicalizeDesign(value: unknown, schema: DetectedSchema): CanonicalDesign {
  const extracted = extractShapes(value);
  if (extracted.shapes.length < 1 || extracted.shapes.length > MAX_SHAPES) {
    throw new HttpError(400, "invalid_shape_count", `Designs must contain between 1 and ${MAX_SHAPES} shapes.`);
  }
  const shapes = extracted.shapes.map(canonicalShape);
  return {
    format: "kfps.community.v1",
    metadata: {
      shape_count: shapes.length,
      source_format: extracted.sourceFormat,
      source_schema: schema.id,
      schema_known: schema.known,
      detected_games: schema.games,
    },
    shapes,
  };
}

function shapeUsesMask(shape: CanonicalShape): boolean {
  if (Object.prototype.hasOwnProperty.call(shape, "mask")) return shape.mask === true;
  const dataFlag = shape.data[6];
  return typeof dataFlag === "number" && Number.isFinite(dataFlag) && Math.trunc(dataFlag) !== 0;
}

function decodeDesign(value: unknown): unknown {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string" || value.length > MAX_DESIGN_BYTES) throw new HttpError(400, "invalid_design");
  try {
    return JSON.parse(value);
  } catch {
    throw new HttpError(400, "invalid_design");
  }
}

function crc32(bytes: Uint8Array, start: number, length: number): number {
  let crc = 0xffffffff;
  for (let index = start; index < start + length; index += 1) {
    crc ^= bytes[index]!;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function validatePng(bytes: Uint8Array, maximumDimension = 2048): void {
  if (bytes.length < 45) throw new HttpError(400, "invalid_preview");
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (!signature.every((value, index) => bytes[index] === value)) throw new HttpError(400, "invalid_preview", "Preview must be a PNG image.");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 8;
  let chunks = 0;
  let sawHeader = false;
  let sawImageData = false;
  let sawEnd = false;
  const knownCritical = new Set(["IHDR", "PLTE", "IDAT", "IEND"]);
  while (offset < bytes.length) {
    if (offset + 12 > bytes.length || chunks++ > 2048) throw new HttpError(400, "invalid_preview", "Preview PNG structure is invalid.");
    const length = view.getUint32(offset);
    const typeStart = offset + 4;
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    const chunkEnd = dataEnd + 4;
    if (length > MAX_PREVIEW_BYTES || chunkEnd > bytes.length) throw new HttpError(400, "invalid_preview", "Preview PNG structure is invalid.");
    const type = String.fromCharCode(bytes[typeStart]!, bytes[typeStart + 1]!, bytes[typeStart + 2]!, bytes[typeStart + 3]!);
    if (!/^[A-Za-z]{4}$/.test(type)) throw new HttpError(400, "invalid_preview", "Preview PNG contains an invalid chunk.");
    if (view.getUint32(dataEnd) !== crc32(bytes, typeStart, length + 4)) {
      throw new HttpError(400, "invalid_preview", "Preview PNG checksum is invalid.");
    }
    if (!sawHeader) {
      if (type !== "IHDR" || length !== 13) throw new HttpError(400, "invalid_preview", "Preview PNG header is invalid.");
      const width = view.getUint32(dataStart);
      const height = view.getUint32(dataStart + 4);
      const bitDepth = bytes[dataStart + 8];
      const colorType = bytes[dataStart + 9];
      if (width < 64 || height < 64 || width > maximumDimension || height > maximumDimension) {
        throw new HttpError(400, "invalid_preview", `Preview dimensions must be between 64 and ${maximumDimension} pixels.`);
      }
      if (bitDepth !== 8 || ![2, 3, 4, 6].includes(colorType!) || bytes[dataStart + 10] !== 0 || bytes[dataStart + 11] !== 0 || bytes[dataStart + 12] !== 0) {
        throw new HttpError(400, "invalid_preview", "Preview PNG uses unsupported encoding settings.");
      }
      sawHeader = true;
    } else if (type === "IHDR" || (type.charCodeAt(0) >= 65 && type.charCodeAt(0) <= 90 && !knownCritical.has(type))) {
      throw new HttpError(400, "invalid_preview", "Preview PNG contains an unsupported critical chunk.");
    }
    if (type === "acTL") throw new HttpError(400, "invalid_preview", "Animated previews are not supported.");
    if (type === "IDAT") sawImageData = true;
    if (type === "IEND") {
      if (length !== 0 || chunkEnd !== bytes.length) throw new HttpError(400, "invalid_preview", "Preview PNG ending is invalid.");
      sawEnd = true;
      break;
    }
    offset = chunkEnd;
  }
  if (!sawHeader || !sawImageData || !sawEnd) throw new HttpError(400, "invalid_preview", "Preview PNG is incomplete.");
}

export function validateTags(value: unknown): string[] {
  if (value == null) return [];
  if (!Array.isArray(value) || value.length > 10) throw new HttpError(400, "invalid_tags");
  const out = value.map((item) => plainText(item, "tag", 24, true));
  if (out.some((item) => !/^[\p{L}\p{N}][\p{L}\p{N} _.-]*$/u.test(item))) throw new HttpError(400, "invalid_tags");
  return [...new Map(out.map((item) => [item.toLocaleLowerCase("en-US"), item])).values()];
}

export function validateClassification(
  value: unknown,
  fallback?: ArtworkClassification,
): ArtworkClassification {
  if (value == null && fallback) return fallback;
  if (typeof value !== "string" || !(CLASSIFICATIONS as readonly string[]).includes(value)) {
    throw new HttpError(400, "invalid_classification", "Choose either Handmade or Toolmade.");
  }
  return value as ArtworkClassification;
}

function versionParts(value: string): [number, number, number] | null {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(value);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

export function validateClientVersion(value: unknown, minimumVersion: string): string {
  const clientVersion = typeof value === "string" ? value.trim() : "";
  const client = versionParts(clientVersion);
  const minimum = versionParts(minimumVersion);
  if (!client || clientVersion.length > 32) {
    throw new HttpError(426, "client_update_required", "Update KFPS before uploading community artwork.");
  }
  if (minimum) {
    for (let index = 0; index < 3; index += 1) {
      if (client[index]! > minimum[index]!) break;
      if (client[index]! < minimum[index]!) {
        throw new HttpError(
          426,
          "client_update_required",
          `KFPS ${minimumVersion} or newer is required to upload community artwork.`,
        );
      }
    }
  }
  return clientVersion;
}

export async function validateUpload(
  value: Record<string, unknown>,
  minimumClientVersion: string,
  requireModernClient = true,
): Promise<ValidatedUpload> {
  const clientVersion = value.client_version == null && !requireModernClient
    ? "legacy"
    : validateClientVersion(value.client_version, minimumClientVersion);
  if (value.confirm_rights !== true) {
    throw new HttpError(400, "rights_confirmation_required", "Confirm that you created this artwork or have permission to share it.");
  }
  const title = plainText(value.title, "title", 80, true);
  const description = plainText(value.description, "description", 800, false);
  const category = plainText(value.category, "category", 40, true);
  if (!(CATEGORIES as readonly string[]).includes(category)) throw new HttpError(400, "invalid_category");
  const classification = validateClassification(
    value.classification,
    requireModernClient ? undefined : "toolmade",
  );
  if (value.supporter_only != null && typeof value.supporter_only !== "boolean") {
    throw new HttpError(400, "invalid_supporter_visibility");
  }
  const supporterOnly = value.supporter_only === true;
  const selectedTags = validateTags(value.tags);
  const license = plainText(value.license, "license", 40, true);
  if (!(LICENSES as readonly string[]).includes(license)) throw new HttpError(400, "invalid_license");
  const decodedDesign = decodeDesign(value.design);
  const extracted = extractShapes(decodedDesign);
  const schema = detectDesignSchema(decodedDesign, extracted.shapes);
  if (!schema.known && value.confirm_compatibility !== true) {
    throw new HttpError(
      400,
      "unknown_schema_confirmation_required",
      "This JSON uses an unrecognized format. Confirm that compatibility may be limited before publishing it.",
    );
  }
  const design = canonicalizeDesign(decodedDesign, schema);
  const designText = JSON.stringify(design);
  const designBytes = new TextEncoder().encode(designText);
  if (designBytes.length > MAX_DESIGN_BYTES) throw new HttpError(413, "design_too_large");
  const previewBytes = base64ToBytes(value.preview_base64, MAX_PREVIEW_BYTES);
  validatePng(previewBytes);
  const thumbnailBytes = value.thumbnail_base64 == null
    ? previewBytes
    : base64ToBytes(value.thumbnail_base64, MAX_THUMBNAIL_BYTES);
  if (value.thumbnail_base64 != null) validatePng(thumbnailBytes, 640);
  return {
    clientVersion,
    title,
    description,
    category,
    classification,
    supporterOnly,
    tags: selectedTags,
    games: schema.games,
    license,
    design,
    designBytes,
    previewBytes,
    thumbnailBytes,
    shapeCount: design.shapes.length,
    groupCount: extracted.groupCount,
    usesMasks: design.shapes.some(shapeUsesMask),
    sourceSchema: schema.id,
    schemaLabel: schema.label,
    schemaKnown: schema.known,
    detectedGames: schema.games,
    contentHash: await sha256Hex(designBytes),
    previewHash: await sha256Hex(previewBytes),
    thumbnailHash: await sha256Hex(thumbnailBytes),
  };
}
