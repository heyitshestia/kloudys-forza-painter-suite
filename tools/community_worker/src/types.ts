export interface Env {
  DB: D1Database;
  ASSETS: R2Bucket;
  API_PROTOCOL: string;
  DEPLOYMENT_ENVIRONMENT?: string;
  ALLOW_TEST_AUTH: string;
  TEST_AUTH_TOKEN?: string;
  AUTO_APPROVE_TEST_UPLOADS: string;
  AUTO_PUBLISH_VALIDATED_UPLOADS: string;
  GITHUB_CLIENT_ID: string;
  ADMIN_TOKEN: string;
  MINIMUM_UPLOAD_VERSION?: string;
  COMPATIBILITY_MINIMUM_UPLOAD_VERSION?: string;
  REQUIRE_MODERN_UPLOAD_CLIENT?: string;
  VERSION_SYNC_ENABLED?: string;
  VERSION_REPOSITORY?: string;
  VERSION_BRANCH?: string;
  SUPPORTER_ENTITLEMENT_KEY_ID?: string;
  SUPPORTER_ENTITLEMENT_MODULUS_HEX?: string;
}

export interface SessionUser {
  id: string;
  provider: "github" | "local-test";
  providerId: string;
  providerLogin: string;
  username: string;
  bio: string;
  websiteUrl: string;
  avatarUrl: string;
  suspended: boolean;
  supporterEntitlementId: string;
  supporterVerifiedUntil: string;
}

export interface CanonicalShape {
  type: number;
  type_word?: number;
  data: number[];
  color: number[];
  mask?: boolean;
  resource_family?: string;
  resource_index?: number;
  source_format?: string;
}

export interface CanonicalDesign {
  format: "kfps.community.v1";
  metadata: {
    shape_count: number;
    source_format: string;
    source_schema: string;
    schema_known: boolean;
    detected_games: string[];
  };
  shapes: CanonicalShape[];
}

export interface DetectedSchema {
  id: string;
  label: string;
  known: boolean;
  games: string[];
}

export type ArtworkClassification = "handmade" | "toolmade";

export interface ValidatedUpload {
  clientVersion: string;
  title: string;
  description: string;
  category: string;
  classification: ArtworkClassification;
  supporterOnly: boolean;
  tags: string[];
  games: string[];
  license: string;
  design: CanonicalDesign;
  designBytes: Uint8Array;
  previewBytes: Uint8Array;
  thumbnailBytes: Uint8Array;
  shapeCount: number;
  groupCount: number;
  usesMasks: boolean;
  sourceSchema: string;
  schemaLabel: string;
  schemaKnown: boolean;
  detectedGames: string[];
  contentHash: string;
  previewHash: string;
  thumbnailHash: string;
}
