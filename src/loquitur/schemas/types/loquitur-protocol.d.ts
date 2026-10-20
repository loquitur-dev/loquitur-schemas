// Generated from loquitur-schemas bundled JSON Schemas.
// Do not hand-edit. Regenerate from loquitur.schemas.typescript.
// Contract: protocol 0.1 closed canonical objects and verification vocabularies.

export type LoquiturJsonObject = Record<string, unknown>;
export type VerificationStatus = "pass" | "warning" | "review" | "fail";
export type RegistryVerdict = "PASS" | "WARN" | "REVIEW" | "FAIL";

export interface ChangeSummary {
  asset_id?: string | null;
  asset_type?: string | null;
  bundle_id: string;
  claims_coverage_delta?: LoquiturJsonObject | null;
  current_bundle_id: string;
  evidence_added?: string[];
  evidence_count_delta?: number | null;
  evidence_removed?: string[];
  fields_changed?: string[] | null;
  freshness_changes?: LoquiturJsonObject | null;
  mark_changed?: boolean | null;
  mark_delta_k?: number | null;
  mark_delta_pct?: number | null;
  material_change?: boolean | null;
  materiality_basis?: LoquiturJsonObject | null;
  materiality_threshold?: LoquiturJsonObject | null;
  object_type: "change_summary";
  previous_bundle_id?: string | null;
  schema_version: "v2";
  snapshot_seq_current?: number | null;
  snapshot_seq_previous?: number | null;
  supersedes_bundle_id?: string | null;
  verdict_changed?: boolean | null;
  verdict_current?: "PASS" | "WARN" | "REVIEW" | "FAIL" | null;
  verdict_previous?: "PASS" | "WARN" | "REVIEW" | "FAIL" | null;
}

export interface CoverageSummary {
  asset_type?: string | null;
  bundle_id: string;
  class_posture?: LoquiturJsonObject[] | null;
  conflicting_document_classes?: string[] | null;
  conflicting_source_groups?: LoquiturJsonObject[] | null;
  coverage: LoquiturJsonObject;
  coverage_status?: string | null;
  document_classes?: LoquiturJsonObject[];
  missing_recommended_document_classes?: string[] | null;
  missing_required_document_classes?: string[] | null;
  object_type: "coverage_summary";
  present_document_classes?: string[] | null;
  readiness: LoquiturJsonObject;
  recommended_document_classes?: string[] | null;
  required_document_classes?: string[] | null;
  schema_version: "v2";
  stale_document_classes?: string[] | null;
  stale_documents?: LoquiturJsonObject[] | null;
}

export interface LineageSummary {
  asset_id?: string | null;
  asset_type?: string | null;
  continuity_status?: string | null;
  current_bundle_id?: string | null;
  current_snapshot_seq?: number | null;
  effective_date_current?: string | null;
  effective_date_previous?: string | null;
  history_count?: number | null;
  latest_bundle_id?: string | null;
  latest_for_asset?: boolean | null;
  latest_snapshot_seq?: number | null;
  object_type: "lineage_summary";
  previous_bundle_id?: string | null;
  previous_snapshot_seq?: number | null;
  schema_version: "v2";
  superseded_by?: string | null;
  supersedes?: string | null;
}

export interface VerificationReceipt {
  anchor_provider?: string | null;
  anchor_type?: string | null;
  asset_id?: string | null;
  asset_type: string;
  bundle_id: string;
  manifest_sha256: string;
  network?: string | null;
  object_type: "verification_receipt";
  p1_sha256?: string | null;
  policy_id: string;
  policy_pack_sha256?: string | null;
  policy_version: number;
  primary_anchor?: LoquiturJsonObject | null;
  reason_code_vocabulary_version: "loquitur.reason_codes.v1";
  reason_codes: ("AUTHORIZATION_ISSUER_KEY_EXPIRED" | "AUTHORIZATION_ISSUER_KEY_NOT_YET_EFFECTIVE" | "AUTHORIZATION_ISSUER_KEY_REVOKED" | "AUTHORIZATION_ISSUER_KEY_SUSPENDED" | "AUTHORIZATION_ISSUER_NOT_RECOGNISED" | "AUTHORIZATION_SCOPE_MISMATCH" | "AUTHORIZATION_SIGNATURE_NOT_VERIFIED" | "AUTHORIZATION_SIGNING_METHOD_UNSUPPORTED" | "AUTHORIZATION_TRUST_MATERIAL_OUTSIDE_VALIDITY_WINDOW" | "AUTHORIZATION_TRUST_REGISTRY_AMBIGUOUS_KEY" | "AUTHORIZATION_VERIFIED" | "BUNDLE_EXTRA_FILES" | "COMPLETENESS_OFFLINE_CHECKS_SKIPPED" | "COMPLETENESS_OFFLINE_MATERIAL_MISSING" | "COMPLETENESS_OFFLINE_MISSING_CANONICAL_INPUT" | "COMPLETENESS_OFFLINE_MISSING_MANIFEST" | "CONFLICTING_EVIDENCE_DETECTED" | "FRESHNESS_OK" | "FRESHNESS_P1_TIMESTAMP_OOW" | "FRESHNESS_WARNING" | "INTEGRITY_CHECK_FAILED" | "INTEGRITY_OFFLINE_CANONICALIZATION_FAILED" | "INTEGRITY_OFFLINE_ENVELOPE_LINKS_MISMATCH" | "INTEGRITY_OFFLINE_ENVELOPE_SHA_MISMATCH" | "INTEGRITY_OFFLINE_EXTRA_FILES_STRICT" | "INTEGRITY_OFFLINE_FAIL" | "INTEGRITY_OFFLINE_INPUT_HASH_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_FILE_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_SHA_MISMATCH" | "INTEGRITY_OFFLINE_SCHEMA_INVALID" | "INTEGRITY_OK" | "MARK_ASOF_UNPARSEABLE" | "MARK_FAR_OUTSIDE_RANGE" | "MARK_NEAR_BOUNDARY" | "MARK_OFFSET_FROM_MIDPOINT" | "MARK_OUTSIDE_RANGE" | "MARK_STALE" | "MATERIAL_CHANGE_DETECTED" | "METHOD_BINDING_MISSING" | "MISSING_MARK_FIELDS" | "MISSING_REQUIRED_INPUTS" | "NEEDS_REVIEW" | "OFFLINE_CANONICAL_INPUT_MISSING" | "OFFLINE_INPUT_HASH_NOT_VERIFIED" | "OFFLINE_MANIFEST_MISSING" | "OFFLINE_MATERIAL_MISSING" | "OFFLINE_REPLAY_FAILED" | "OFFLINE_REPLAY_REVIEW" | "OFFLINE_REPLAY_SKIPPED" | "OFFLINE_REPLAY_WARN" | "P1_TIMESTAMP_OUT_OF_WINDOW" | "POLICY_BUNDLE_EXTRA_FILES" | "REQUIRED_CLAIMS_PRESENT" | "REQUIRED_EVIDENCE_PRESENT" | "UNSUPPORTED_KEY_CLAIM" | "VOCABULARY_VALUE_INVALID" | "VOCABULARY_VALUE_UNKNOWN")[];
  schema_version: "v2";
  status: VerificationStatus;
  storage?: LoquiturJsonObject[];
  verification_mode: string;
  verified_at: string;
}

export interface VerificationSummary {
  asset_id?: string | null;
  asset_type?: string | null;
  bundle_id: string;
  freshness_posture?: LoquiturJsonObject | null;
  key_checks?: LoquiturJsonObject[] | LoquiturJsonObject | null;
  key_metrics?: LoquiturJsonObject[];
  object_type: "verification_summary";
  policy_checks?: LoquiturJsonObject | null;
  policy_id?: string | null;
  policy_pack_sha256?: string | null;
  policy_surface?: LoquiturJsonObject | null;
  policy_version?: number | null;
  reason_code_vocabulary_version: "loquitur.reason_codes.v1";
  reason_codes: ("AUTHORIZATION_ISSUER_KEY_EXPIRED" | "AUTHORIZATION_ISSUER_KEY_NOT_YET_EFFECTIVE" | "AUTHORIZATION_ISSUER_KEY_REVOKED" | "AUTHORIZATION_ISSUER_KEY_SUSPENDED" | "AUTHORIZATION_ISSUER_NOT_RECOGNISED" | "AUTHORIZATION_SCOPE_MISMATCH" | "AUTHORIZATION_SIGNATURE_NOT_VERIFIED" | "AUTHORIZATION_SIGNING_METHOD_UNSUPPORTED" | "AUTHORIZATION_TRUST_MATERIAL_OUTSIDE_VALIDITY_WINDOW" | "AUTHORIZATION_TRUST_REGISTRY_AMBIGUOUS_KEY" | "AUTHORIZATION_VERIFIED" | "BUNDLE_EXTRA_FILES" | "COMPLETENESS_OFFLINE_CHECKS_SKIPPED" | "COMPLETENESS_OFFLINE_MATERIAL_MISSING" | "COMPLETENESS_OFFLINE_MISSING_CANONICAL_INPUT" | "COMPLETENESS_OFFLINE_MISSING_MANIFEST" | "CONFLICTING_EVIDENCE_DETECTED" | "FRESHNESS_OK" | "FRESHNESS_P1_TIMESTAMP_OOW" | "FRESHNESS_WARNING" | "INTEGRITY_CHECK_FAILED" | "INTEGRITY_OFFLINE_CANONICALIZATION_FAILED" | "INTEGRITY_OFFLINE_ENVELOPE_LINKS_MISMATCH" | "INTEGRITY_OFFLINE_ENVELOPE_SHA_MISMATCH" | "INTEGRITY_OFFLINE_EXTRA_FILES_STRICT" | "INTEGRITY_OFFLINE_FAIL" | "INTEGRITY_OFFLINE_INPUT_HASH_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_FILE_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_SHA_MISMATCH" | "INTEGRITY_OFFLINE_SCHEMA_INVALID" | "INTEGRITY_OK" | "MARK_ASOF_UNPARSEABLE" | "MARK_FAR_OUTSIDE_RANGE" | "MARK_NEAR_BOUNDARY" | "MARK_OFFSET_FROM_MIDPOINT" | "MARK_OUTSIDE_RANGE" | "MARK_STALE" | "MATERIAL_CHANGE_DETECTED" | "METHOD_BINDING_MISSING" | "MISSING_MARK_FIELDS" | "MISSING_REQUIRED_INPUTS" | "NEEDS_REVIEW" | "OFFLINE_CANONICAL_INPUT_MISSING" | "OFFLINE_INPUT_HASH_NOT_VERIFIED" | "OFFLINE_MANIFEST_MISSING" | "OFFLINE_MATERIAL_MISSING" | "OFFLINE_REPLAY_FAILED" | "OFFLINE_REPLAY_REVIEW" | "OFFLINE_REPLAY_SKIPPED" | "OFFLINE_REPLAY_WARN" | "P1_TIMESTAMP_OUT_OF_WINDOW" | "POLICY_BUNDLE_EXTRA_FILES" | "REQUIRED_CLAIMS_PRESENT" | "REQUIRED_EVIDENCE_PRESENT" | "UNSUPPORTED_KEY_CLAIM" | "VOCABULARY_VALUE_INVALID" | "VOCABULARY_VALUE_UNKNOWN")[];
  reason_context?: LoquiturJsonObject[] | null;
  required_claims_status?: LoquiturJsonObject | null;
  schema_version: "v2";
  status: VerificationStatus;
  supported_vs_declared_summary?: LoquiturJsonObject | null;
  warnings?: string[];
}

export interface RegistryEntry {
  anchor?: LoquiturJsonObject | null;
  anchored_at?: string | null;
  asset_type: string;
  disclosure_profile: "minimal_public" | "issuer_controlled_bundle" | "partner_authorized_bundle";
  effective_at?: string | null;
  issued_at: string;
  issuer_id: string;
  issuer_key_id: string;
  manifest_hash: string;
  object_type: "registry_entry";
  policy_id: string;
  policy_version: string;
  privacy_classification: "public_commitment";
  reason_code_catalog_version: "loquitur.reason_codes.v1";
  reason_codes: ("AUTHORIZATION_ISSUER_KEY_EXPIRED" | "AUTHORIZATION_ISSUER_KEY_NOT_YET_EFFECTIVE" | "AUTHORIZATION_ISSUER_KEY_REVOKED" | "AUTHORIZATION_ISSUER_KEY_SUSPENDED" | "AUTHORIZATION_ISSUER_NOT_RECOGNISED" | "AUTHORIZATION_SCOPE_MISMATCH" | "AUTHORIZATION_SIGNATURE_NOT_VERIFIED" | "AUTHORIZATION_SIGNING_METHOD_UNSUPPORTED" | "AUTHORIZATION_TRUST_MATERIAL_OUTSIDE_VALIDITY_WINDOW" | "AUTHORIZATION_TRUST_REGISTRY_AMBIGUOUS_KEY" | "AUTHORIZATION_VERIFIED" | "BUNDLE_EXTRA_FILES" | "COMPLETENESS_OFFLINE_CHECKS_SKIPPED" | "COMPLETENESS_OFFLINE_MATERIAL_MISSING" | "COMPLETENESS_OFFLINE_MISSING_CANONICAL_INPUT" | "COMPLETENESS_OFFLINE_MISSING_MANIFEST" | "CONFLICTING_EVIDENCE_DETECTED" | "FRESHNESS_OK" | "FRESHNESS_P1_TIMESTAMP_OOW" | "FRESHNESS_WARNING" | "INTEGRITY_CHECK_FAILED" | "INTEGRITY_OFFLINE_CANONICALIZATION_FAILED" | "INTEGRITY_OFFLINE_ENVELOPE_LINKS_MISMATCH" | "INTEGRITY_OFFLINE_ENVELOPE_SHA_MISMATCH" | "INTEGRITY_OFFLINE_EXTRA_FILES_STRICT" | "INTEGRITY_OFFLINE_FAIL" | "INTEGRITY_OFFLINE_INPUT_HASH_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_FILE_MISMATCH" | "INTEGRITY_OFFLINE_MANIFEST_SHA_MISMATCH" | "INTEGRITY_OFFLINE_SCHEMA_INVALID" | "INTEGRITY_OK" | "MARK_ASOF_UNPARSEABLE" | "MARK_FAR_OUTSIDE_RANGE" | "MARK_NEAR_BOUNDARY" | "MARK_OFFSET_FROM_MIDPOINT" | "MARK_OUTSIDE_RANGE" | "MARK_STALE" | "MATERIAL_CHANGE_DETECTED" | "METHOD_BINDING_MISSING" | "MISSING_MARK_FIELDS" | "MISSING_REQUIRED_INPUTS" | "NEEDS_REVIEW" | "OFFLINE_CANONICAL_INPUT_MISSING" | "OFFLINE_INPUT_HASH_NOT_VERIFIED" | "OFFLINE_MANIFEST_MISSING" | "OFFLINE_MATERIAL_MISSING" | "OFFLINE_REPLAY_FAILED" | "OFFLINE_REPLAY_REVIEW" | "OFFLINE_REPLAY_SKIPPED" | "OFFLINE_REPLAY_WARN" | "P1_TIMESTAMP_OUT_OF_WINDOW" | "POLICY_BUNDLE_EXTRA_FILES" | "REQUIRED_CLAIMS_PRESENT" | "REQUIRED_EVIDENCE_PRESENT" | "UNSUPPORTED_KEY_CLAIM" | "VOCABULARY_VALUE_INVALID" | "VOCABULARY_VALUE_UNKNOWN")[];
  receipt_hash: string;
  receipt_id: string;
  registry_entry_id: string;
  schema_version: "v1";
  signature?: unknown;
  subject_ref_hash: string;
  verdict: RegistryVerdict;
  workflow: string;
}

export interface TrustRegistry {
  effective_at: string;
  entries: LoquiturJsonObject[];
  expires_at: string;
  issued_at: string;
  object_type: "trust_registry";
  registry_operator_id: string;
  registry_version: string;
  schema_version: "v1";
  signature: LoquiturJsonObject;
  trust_registry_id: string;
}

export type LoquiturCanonicalObject =
    ChangeSummary
  | CoverageSummary
  | LineageSummary
  | VerificationReceipt
  | VerificationSummary;

export type LoquiturRegistryObject =
    RegistryEntry
  | TrustRegistry;
