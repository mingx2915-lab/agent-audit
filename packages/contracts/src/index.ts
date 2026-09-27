export type ActorRole =
  | "visitor"
  | "employee"
  | "sales"
  | "hr"
  | "finance_manager"
  | "admin";

export interface Actor {
  id: string;
  displayName: string;
  role: ActorRole;
}

export type TraceEventType =
  | "input"
  | "source"
  | "retrieval"
  | "authorization"
  | "tool_call"
  | "tool_result"
  | "sink"
  | "model_response";

export interface TraceEvent {
  sequence: number;
  type: TraceEventType;
  summary: string;
  details: Record<string, unknown>;
  occurredAt: string;
}

export interface AssistantQueryRequest {
  actorId: string;
  message: string;
}

export interface AssistantQueryResult {
  queryId: string;
  actor: Actor;
  answer: string;
  traceEvents: TraceEvent[];
}

export interface ContractRole {
  id: ActorRole;
  displayName: string;
}

export interface ResourceRule {
  id: string;
  description: string;
  matchLabels: string[];
  allowedRoles: ActorRole[];
  requireOwnerMatch: boolean;
}

export interface ToolRule {
  id: string;
  description: string;
  toolName: string;
  action: string;
  allowedRoles: ActorRole[];
  requireOwnerMatch: boolean;
  maxRecords: number | null;
  requireApproval: boolean;
}

export type SinkType = "external_message" | "customer_export";

export interface SinkRule {
  id: string;
  description: string;
  sinkType: SinkType;
  matchLabels: string[];
  allowedRoles: ActorRole[];
  allowExternal: boolean;
  requireApproval: boolean;
  blockedSourceTrustLevels: string[];
}

export interface SecurityContract {
  id: string;
  name: string;
  version: number;
  roles: ContractRole[];
  resourceRules: ResourceRule[];
  toolRules: ToolRule[];
  sinkRules: SinkRule[];
}

export type ContractChangeKind = "added" | "removed" | "changed";

export interface ContractFieldChange {
  path: string;
  kind: ContractChangeKind;
  beforeValue: unknown;
  afterValue: unknown;
}

export type FindingCategory =
  | "resource_authorization_bypass"
  | "tool_authorization_bypass"
  | "external_sink_policy_violation"
  | "tool_business_policy_violation";

export type FindingSeverity = "high" | "critical";

export interface Finding {
  id: string;
  category: FindingCategory;
  severity: FindingSeverity;
  title: string;
  summary: string;
  contractBasis: "explicit_rule" | "default_deny";
  ruleId: string | null;
  evidenceSequences: number[];
}

export interface SemanticReview {
  performed: boolean;
  explanation: string | null;
}

export interface TraceEvaluationRequest {
  traceEvents: TraceEvent[];
  includeSemanticReview: boolean;
}

export interface TraceEvaluationResult {
  status: "passed" | "failed";
  contractId: string;
  contractVersion: number;
  findings: Finding[];
  semanticReview: SemanticReview;
}

export type AttackerType = "outside_in" | "inside_out";

export interface AttackCase {
  id: string;
  name: string;
  description: string;
  attackerType: AttackerType;
  actorId: string;
  message: string;
  targetProfileId: string;
  expectedFindingCategories: FindingCategory[];
}

export interface BlockedExecution {
  executionStatus: "blocked";
  queryResult: null;
  blockedReason: string;
  traceEvents: TraceEvent[];
  evaluation: TraceEvaluationResult;
}

export type AttackExecutionResult = {
  case: AttackCase;
  queryResult: AssistantQueryResult;
  evaluation: TraceEvaluationResult;
} | (BlockedExecution & { case: AttackCase });

export type AttackPlanBasisType =
  | "resource_owner_scope"
  | "tool_owner_scope"
  | "source_sink"
  | "tool_record_limit";

export type AttackPlanTargetKind =
  | "knowledge_document"
  | "customer_record"
  | "external_sink"
  | "customer_export";

export interface AttackPlan {
  id: string;
  name: string;
  description: string;
  basisType: AttackPlanBasisType;
  basisRuleId: string;
  attackerType: AttackerType;
  actorId: string;
  targetKind: AttackPlanTargetKind;
  targetId: string;
  message: string;
  targetProfileId: string;
  expectedFindingCategories: FindingCategory[];
}

/**
 * Safe projection used by the first-run import flow.  These fields are copied
 * from a real ContractAttackPlanner result and are sufficient to launch the
 * existing executable-plan route without exposing the generated message.
 */
export interface DocumentImportPlanSummary {
  id: string;
  name: string;
  description: string;
  basisType: AttackPlanBasisType;
  basisRuleId: string;
  attackerType: AttackerType;
  actorId: string;
  targetKind: AttackPlanTargetKind;
  targetId: string;
  targetProfileId: string;
}

export interface AttackPlanChange {
  planId: string;
  kind: ContractChangeKind;
  basisType: AttackPlanBasisType | null;
  basisRuleId: string | null;
}

export interface SecurityContractPreview {
  contractId: string;
  activeVersion: number;
  candidateVersion: number;
  fieldChanges: ContractFieldChange[];
  planChanges: AttackPlanChange[];
  currentPlans: AttackPlan[];
  candidatePlans: AttackPlan[];
}

export type AttackPlanExecutionResult = {
  plan: AttackPlan;
  queryResult: AssistantQueryResult;
  evaluation: TraceEvaluationResult;
} | (BlockedExecution & { plan: AttackPlan });

export type ScanState =
  | "profiling"
  | "contract_analysis"
  | "goal_selection"
  | "variant_generation"
  | "execution"
  | "trace_observation"
  | "mutate"
  | "stopped";

export type ScanStopReason =
  | "finding_detected"
  | "no_new_variant"
  | "max_rounds_reached";

export interface ScanStateTransition {
  sequence: number;
  state: ScanState;
  summary: string;
  occurredAt: string;
}

export interface AttackVariant {
  id: string;
  parentAttemptId: string | null;
  round: number;
  actorId: string;
  attackerType: AttackerType;
  basisRuleId: string;
  targetKind: AttackPlanTargetKind;
  targetId: string;
  message: string;
  mutationReason: string;
}

export interface AttackAttempt {
  id: string;
  scanId: string;
  round: number;
  status: "passed" | "finding";
  variant: AttackVariant;
  queryResult: AssistantQueryResult;
  evaluation: TraceEvaluationResult;
  durationMs: number;
}

export interface StartScanRequest {
  planId: string;
  maxRounds: 2 | 3;
}

export interface RedTeamScan {
  id: string;
  planId: string;
  contractId: string;
  contractVersion: number;
  targetProfileId: string;
  provider: string;
  model: string | null;
  maxRounds: number;
  status: "completed";
  stopReason: ScanStopReason;
  stateTransitions: ScanStateTransition[];
  attempts: AttackAttempt[];
  startedAt: string;
  completedAt: string;
  durationMs: number;
}

export interface TargetProfileSnapshot {
  id: string;
  name: string;
  enforceResourceAuthorization: boolean;
  enforceToolAuthorization: boolean;
  enforceSinkAuthorization: boolean;
}

export interface AuditRuntimeSnapshot {
  provider: string;
  model: string | null;
  retrieverEngine: RetrievalEngineId;
  retrieverModel: string | null;
  retrieverDimensions: number | null;
  indexedDocumentCount: number;
}

export interface PersistedReplay {
  id: string;
  createdAt: string;
  replay: ReplayResult;
}

export type StartPersistedReplayRequest = Record<string, never>;

export interface AuditRunSummary {
  scanId: string;
  planId: string;
  contractId: string;
  contractVersion: number;
  targetProfileId: string;
  status: RedTeamScan["status"];
  stopReason: ScanStopReason;
  attemptCount: number;
  findingCount: number;
  replayCount: number;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  runtimeSnapshot: AuditRuntimeSnapshot;
}

export interface AuditRunDetail {
  scan: RedTeamScan;
  planSnapshot: AttackPlan;
  contractSnapshot: SecurityContract;
  targetProfileSnapshot: TargetProfileSnapshot;
  runtimeSnapshot: AuditRuntimeSnapshot;
  replays: PersistedReplay[];
}

export interface RemediationRecommendation {
  id: string;
  title: string;
  summary: string;
  configurationPath:
    | "targetProfile.enforceResourceAuthorization"
    | "targetProfile.enforceToolAuthorization"
    | "targetProfile.enforceSinkAuthorization";
  beforeValue: boolean;
  afterValue: boolean;
}

export interface ReplayAttempt {
  profileId: string;
  executionStatus: "completed" | "blocked";
  queryResult: AssistantQueryResult | null;
  traceEvents: TraceEvent[];
  evaluation: TraceEvaluationResult;
  blockedReason: string | null;
}

export interface ReplayResult {
  id: string;
  plan: AttackPlan;
  remediation: RemediationRecommendation;
  before: ReplayAttempt;
  after: ReplayAttempt;
  status: "passed" | "failed";
}

export type DifferentialTaskType = "resource_access" | "tool_access";
export type DifferentialTargetKind = "knowledge_document" | "customer_record";
export type DifferentialDecision = "allowed" | "denied";
export type DifferentialTargetProfileId =
  | "secure"
  | "vulnerable_observe_only"
  | "vulnerable_tool_observe_only";

export interface DifferentialTask {
  id: string;
  name: string;
  description: string;
  taskType: DifferentialTaskType;
  actorIds: string[];
  targetKind: DifferentialTargetKind;
  targetId: string;
  message: string;
  toolName: string | null;
  action: string | null;
  supportedTargetProfileIds: DifferentialTargetProfileId[];
  defaultTargetProfileId: DifferentialTargetProfileId;
}

export interface StartDifferentialAuditRequest {
  taskId: string;
  targetProfileId: DifferentialTargetProfileId;
}

export interface DifferentialAuditRow {
  id: string;
  actor: Actor;
  targetKind: DifferentialTargetKind;
  targetId: string;
  expectedDecision: DifferentialDecision;
  actualDecision: DifferentialDecision;
  matched: boolean;
  ruleId: string | null;
  executionStatus: "completed" | "blocked";
  queryId: string | null;
  evidenceSequences: number[];
  traceEvents: TraceEvent[];
  findings: Finding[];
  blockedReason: string | null;
}

export interface DifferentialAuditResult {
  id: string;
  task: DifferentialTask;
  targetProfileId: DifferentialTargetProfileId;
  contractId: string;
  contractVersion: number;
  status: "passed" | "failed";
  mismatchCount: number;
  rows: DifferentialAuditRow[];
}

export type RetrievalEngineId = "tfidf" | "embedding";

export interface RetrievalRankedDocument {
  rank: number;
  documentId: string;
  title: string;
  score: number;
}

export interface RetrievalEvaluationCaseResult {
  caseId: string;
  query: string;
  expectedDocumentId: string;
  tfidfResults: RetrievalRankedDocument[];
  embeddingResults: RetrievalRankedDocument[];
  tfidfExpectedRank: number | null;
  embeddingExpectedRank: number | null;
}

export interface RetrievalEvaluationMetrics {
  caseCount: number;
  tfidfTop1Hits: number;
  embeddingTop1Hits: number;
  tfidfMrr: number;
  embeddingMrr: number;
}

export interface RetrievalEvaluationResult {
  id: string;
  selectedEngine: "embedding";
  modelName: string;
  dimensions: number;
  indexedDocumentCount: number;
  cases: RetrievalEvaluationCaseResult[];
  metrics: RetrievalEvaluationMetrics;
}

export type GroundTruthCategory =
  | "normal_behavior"
  | "internal_authorization"
  | "outside_in_source_sink"
  | "tool_threshold_replay";

export type GroundTruthExecutionType = "assistant_query" | "attack_plan" | "replay";

export type GroundTruthExecutionStatus = "completed" | "blocked";

export type GroundTruthOutcome =
  | "evaluation_passed"
  | "evaluation_failed"
  | "replay_passed"
  | "replay_failed";

export interface GroundTruthCase {
  id: string;
  name: string;
  description: string;
  category: GroundTruthCategory;
  executionType: GroundTruthExecutionType;
  actorId: string | null;
  message: string | null;
  targetProfileId: DifferentialTargetProfileId | "vulnerable_sink_observe_only" | null;
  planId: string | null;
  expectedOutcome: GroundTruthOutcome;
  expectedFindingCategories: FindingCategory[];
  expectedExecutionStatus: GroundTruthExecutionStatus;
}

export interface GroundTruthCaseResult {
  caseId: string;
  name: string;
  category: GroundTruthCategory;
  executionType: GroundTruthExecutionType;
  expectedOutcome: GroundTruthOutcome;
  actualOutcome: GroundTruthOutcome;
  expectedFindingCategories: FindingCategory[];
  actualFindingCategories: FindingCategory[];
  expectedExecutionStatus: GroundTruthExecutionStatus;
  actualExecutionStatus: GroundTruthExecutionStatus;
  matched: boolean;
  attemptCount: number;
  providerCallCount: number;
  durationMs: number;
}

export interface ProviderUsageMetrics {
  callCount: number;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  estimatedCostUsd: number | null;
}

export type ProviderProbeId =
  | "target.connectivity"
  | "target.tool_calling"
  | "attack.connectivity"
  | "attack.strict_json";

export type ProviderProbeStatus = "passed" | "failed";
export type ProviderRole = "target" | "attack";
export type ProviderReadinessStatus = "ready" | "partial" | "unavailable";
export type PlanCompatibilityStatus = "compatible" | "incompatible";

export interface ProviderProbeResult {
  id: ProviderProbeId;
  status: ProviderProbeStatus;
  durationMs: number;
  detail: string | null;
}

export interface ProviderRoleReadiness {
  role: ProviderRole;
  provider: string;
  model: string | null;
  status: ProviderReadinessStatus;
  probes: ProviderProbeResult[];
}

export interface PlanCompatibilityResult {
  planId: string;
  basisType: AttackPlanBasisType;
  status: PlanCompatibilityStatus;
  requiredProbeIds: ProviderProbeId[];
  failedProbeIds: ProviderProbeId[];
}

export interface ProviderReadinessResult {
  id: string;
  checkedAt: string;
  status: ProviderReadinessStatus;
  targetProvider: ProviderRoleReadiness;
  attackProvider: ProviderRoleReadiness;
  planCompatibility: PlanCompatibilityResult[];
}

export type EmptyProviderReadinessRequest = Record<string, never>;

/** Runtime protocol selected by the user or confirmed by endpoint inspection. */
export type ProviderConnectionKind =
  | "ollama"
  | "openai_compatible"
  | "anthropic_compatible"
  | "agent_audit_adapter";

export type ProviderAuthMode = "none" | "bearer" | "x_api_key";

export interface ProviderConnectionSettings {
  kind: ProviderConnectionKind;
  baseUrl: string;
  model: string;
  /** Missing in an old F-027 file is read as `none` by the API. */
  authMode: ProviderAuthMode;
}

/** Public metadata for one model returned by an OpenAI-compatible `/v1/models`. */
export interface ProviderModelCandidate {
  id: string;
  object: "model" | null;
  created: number | null;
  ownedBy: string | null;
}

export type ProviderProtocol =
  | "ollama"
  | "openai_compatible"
  | "anthropic_compatible"
  | "agent_audit_adapter";
export type ProtocolInspectionStatus = "available" | "unavailable";

/** Fixed, non-secret capability declaration returned by a bridge manifest. */
export interface ProviderCapabilityManifest {
  text: boolean;
  toolCalling: boolean;
  structuredOutput: boolean;
  usage: boolean;
}

/** Versioned enterprise bridge manifest (currently `agent_audit_adapter.v1`). */
export interface AgentAuditAdapterManifest {
  protocol: "agent_audit_adapter";
  protocolVersion: "agent_audit_adapter.v1";
  capabilities: ProviderCapabilityManifest;
}

export type CanonicalMessageRole = "system" | "user" | "assistant" | "tool";

export interface CanonicalMessage {
  role: CanonicalMessageRole;
  content: string | null;
  toolCallId?: string;
  toolCalls?: CanonicalToolCall[];
  name?: string;
}

export interface CanonicalToolDefinition {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

export interface CanonicalToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface CanonicalUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

/** Versioned enterprise bridge completion request/response payloads. */
export interface CanonicalCompletionRequest {
  protocolVersion: "agent_audit_adapter.v1";
  model: string;
  messages: CanonicalMessage[];
  tools?: CanonicalToolDefinition[];
  maxTokens: number;
}

export interface CanonicalCompletionResponse {
  content: string | null;
  toolCalls?: CanonicalToolCall[];
  usage?: CanonicalUsage | null;
}

/** Non-secret result of inspecting one explicitly supplied Runtime origin. */
export interface ProtocolInspectionResult {
  status: ProtocolInspectionStatus;
  protocol: ProviderProtocol | null;
  /** Normalized service base, ending in `/v1` for OpenAI-compatible APIs. */
  baseUrl: string;
  models: ProviderModelCandidate[];
  diagnostic: string | null;
  modelsEnumerated: boolean;
  /** Present only when the selected protocol exposes a valid fixed manifest. */
  protocolVersion?: "agent_audit_adapter.v1" | null;
  capabilities?: ProviderCapabilityManifest | null;
  manifest?: AgentAuditAdapterManifest | null;
}

export type OllamaDiscoveryStatus = "available" | "unavailable";

export interface OllamaModelCandidate {
  name: string;
  sizeBytes: number | null;
  modifiedAt: string | null;
}

export interface OllamaDiscoveryResult {
  endpoint: string;
  status: OllamaDiscoveryStatus;
  models: OllamaModelCandidate[];
  diagnostic: string | null;
}

export interface ProviderSetupState {
  configured: boolean;
  settings: ProviderConnectionSettings | null;
  /** Whether a credential is available in the current process boundary. */
  credentialConfigured: boolean;
  runtimeSnapshot: AuditRuntimeSnapshot;
}

export type DocumentImportStatus = "ready" | "unsupported" | "invalid";
export type DocumentSensitivity = "public" | "confidential";
export type DocumentBusinessScope = "general" | "customer" | "finance" | "hr";
export type DocumentTrustLevel = "trusted" | "untrusted";

/** Stable machine-readable causes paired with a human-readable diagnostic. */
export type DocumentImportDiagnosticCode =
  | "unsupported_format"
  | "invalid_utf8"
  | "parse_failed"
  | "encrypted"
  | "no_text"
  | "too_large"
  | "read_failed";

/** Text selected by the native shell. Paths are relative to that selection only. */
export interface DocumentImportSource {
  sourceId: string;
  displayName: string;
  relativePath: string;
  extension: string;
  sizeBytes: number;
  content: string | null;
  diagnostic: string | null;
  /** Native picker hint; the API always validates and recomputes status. */
  status?: DocumentImportStatus | null;
  diagnosticCode?: DocumentImportDiagnosticCode | null;
}

export interface DocumentImportMetadata {
  title: string;
  sensitivity: DocumentSensitivity;
  businessScope: DocumentBusinessScope;
  ownerId: string | null;
  trustLevel: DocumentTrustLevel;
}

export interface DocumentImportDraft {
  source: DocumentImportSource;
  metadata: DocumentImportMetadata;
}

export interface DocumentAuthorizationPreview {
  actorId: string;
  role: ActorRole;
  allowed: boolean;
  ruleId: string | null;
}

export interface DocumentImportPreviewItem {
  sourceId: string;
  displayName: string;
  relativePath: string;
  status: DocumentImportStatus;
  titleSuggestion: string;
  contentPreview: string | null;
  diagnostic: string | null;
  diagnosticCode: DocumentImportDiagnosticCode | null;
  metadata: DocumentImportMetadata;
  authorization: DocumentAuthorizationPreview[];
}

export interface DocumentImportPreviewRequest {
  documents: DocumentImportDraft[];
}

export interface DocumentImportPreview {
  contractId: string;
  contractVersion: number;
  items: DocumentImportPreviewItem[];
  readyCount: number;
  skippedCount: number;
  executablePlans: DocumentImportPlanSummary[];
  planDiagnostic: string | null;
}

export interface WorkspaceDocumentSummary {
  id: string;
  title: string;
  ownerId: string | null;
  labels: string[];
  sourceType: string;
  trustLevel: string;
}

export interface DocumentIndexMetadata {
  engineId: "tfidf" | "embedding";
  modelName: string | null;
  dimensions: number | null;
  indexedDocumentCount: number;
}

export interface DocumentCatalog {
  workspaceName: string | null;
  documents: WorkspaceDocumentSummary[];
  retriever: DocumentIndexMetadata;
}

export interface DocumentImportCommitRequest {
  documents: DocumentImportDraft[];
}

export interface DocumentImportSkippedItem {
  sourceId: string;
  displayName: string;
  status: Exclude<DocumentImportStatus, "ready">;
  diagnostic: string;
  diagnosticCode: DocumentImportDiagnosticCode | null;
}

export interface DocumentImportResult {
  imported: WorkspaceDocumentSummary[];
  skipped: DocumentImportSkippedItem[];
  retriever: DocumentIndexMetadata;
  executablePlans: DocumentImportPlanSummary[];
  planDiagnostic: string | null;
}

/** One allowlisted category that may contribute local operational metadata. */
export interface DiagnosticCategory {
  id: "logs" | "runtime" | "sidecar" | "workspace";
  label: string;
  available: boolean;
  count: number;
}

/** Read-only disclosure shown before a user explicitly exports diagnostics. */
export interface DiagnosticPreview {
  included: DiagnosticCategory[];
  excluded: string[];
  localOnly: true;
  suggestedFilename: string;
  disclaimer: string;
}

export interface DiagnosticFile {
  path: string;
  category: string;
  sizeBytes: number;
  sha256: string;
}

/** Machine-readable facts embedded in a local diagnostic ZIP. */
export interface DiagnosticManifest {
  schemaVersion: 1;
  createdAt: string;
  operationId: string;
  productVersion: string;
  included: DiagnosticCategory[];
  excluded: string[];
  runtime: Record<string, unknown>;
  sidecar: Record<string, unknown> | null;
  workspace: Record<string, unknown> | null;
  files: DiagnosticFile[];
  disclaimer: string;
}

/** Portable user-facing identity for one Workspace below the application workspaces root. */
export interface WorkspaceSummary {
  id: string;
  name: string;
  relativeDirectory: string;
  contractId: string;
  contractVersion: number;
  documentCount: number;
  historyIncluded: boolean;
  active: boolean;
}

/** Pure inspection result for an AgentAudit Workspace backup archive. */
export interface WorkspaceBackupPreview {
  formatVersion: 1;
  workspace: WorkspaceSummary;
  archiveSizeBytes: number;
  createdAt: string;
}

/** Result of restoring an archive as a new, non-active Workspace. */
export interface WorkspaceRestoreResult {
  workspace: WorkspaceSummary;
  restored: true;
  restartRequired: true;
}

/** Explicit preparation of one direct Workspace child before activation. */
export interface WorkspaceActivationPreparationRequest {
  relativeDirectory: string;
}

export interface WorkspaceActivationPreparation {
  prepared: true;
  relativeDirectory: string;
  workspaceSchemaVersion: number;
  sqliteSchemaVersion: number;
}

export type OllamaDiscoveryRequest = Record<string, never>;

export interface ProviderCandidateReadinessRequest {
  settings: ProviderConnectionSettings;
  /** One-time credential value; never returned or persisted by the API. */
  credential?: string;
}

export interface SaveProviderSettingsRequest {
  settings: ProviderConnectionSettings;
  /** One-time credential value; never returned or persisted by the API. */
  credential?: string;
}

export interface ProviderInspectionRequest {
  kind: ProviderConnectionKind;
  baseUrl: string;
  authMode: ProviderAuthMode;
  /** One-time credential value; never returned or persisted by the API. */
  credential?: string;
}

export interface BenchmarkMetrics {
  caseCount: number;
  matchedCaseCount: number;
  categoryCounts: Record<GroundTruthCategory, number>;
  normalCaseCount: number;
  violationCaseCount: number;
  replayCaseCount: number;
  attackSuccessRate: number | null;
  detectionRecall: number | null;
  falsePositiveRate: number | null;
  policyViolationAccuracy: number | null;
  meanAttempts: number | null;
  meanScanTimeMs: number | null;
  replayPassRate: number | null;
  providerUsage: ProviderUsageMetrics;
  scanTimeMs: number;
}

export interface BenchmarkResult {
  id: string;
  cases: GroundTruthCaseResult[];
  metrics: BenchmarkMetrics;
}

export type CIGateStatus = "passed" | "failed";

export interface CIGateCheck {
  id: string;
  actual: boolean | number | null;
  expected: boolean | number;
  passed: boolean;
}

export interface CIGateResult {
  id: string;
  generatedAt: string;
  status: CIGateStatus;
  contractId: string;
  contractVersion: number;
  runtimeSnapshot: AuditRuntimeSnapshot;
  checks: CIGateCheck[];
  failedCheckIds: string[];
  benchmark: BenchmarkResult;
}

export type AcceptanceRunStatus = "completed";
export type AcceptanceVerdict = "passed" | "failed";

export interface AcceptanceRun {
  id: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  status: AcceptanceRunStatus;
  verdict: AcceptanceVerdict;
  contractSnapshot: SecurityContract;
  planSnapshots: AttackPlan[];
  profileSnapshots: TargetProfileSnapshot[];
  runtimeSnapshot: AuditRuntimeSnapshot;
  providerReadiness: ProviderReadinessResult;
  retrievalEvaluation: RetrievalEvaluationResult;
  differentialAudits: DifferentialAuditResult[];
  ciGate: CIGateResult;
  guidedScan: RedTeamScan;
  guidedReplay: ReplayResult;
  findingCategories: FindingCategory[];
  findingCount: number;
}

export interface AcceptanceRunSummary {
  id: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  status: AcceptanceRunStatus;
  verdict: AcceptanceVerdict;
  contractId: string;
  contractVersion: number;
  runtimeSnapshot: AuditRuntimeSnapshot;
  readinessStatus: ProviderReadinessStatus;
  gateStatus: CIGateStatus;
  benchmarkCaseCount: number;
  benchmarkMatchedCaseCount: number;
  findingCount: number;
  findingCategories: FindingCategory[];
  guidedReplayStatus: "passed" | "failed";
}

export interface AcceptanceMetricDelta {
  id: string;
  previous: boolean | number | null;
  current: boolean | number | null;
  delta: number | null;
}

export interface AcceptanceRunComparison {
  current: AcceptanceRunSummary;
  previous: AcceptanceRunSummary | null;
  contractChanged: boolean;
  runtimeChanged: boolean;
  readinessChanged: boolean;
  gateStatusChanged: boolean;
  gateMetricDeltas: AcceptanceMetricDelta[];
  addedFailedCheckIds: string[];
  resolvedFailedCheckIds: string[];
  addedMismatchedCaseIds: string[];
  resolvedMismatchedCaseIds: string[];
  addedFindingCategories: FindingCategory[];
  resolvedFindingCategories: FindingCategory[];
}

export type EmptyAcceptanceRunRequest = Record<string, never>;

export interface AttackChainReport {
  id: string;
  generatedAt: string;
  title: string;
  executiveSummary: string;
  replay: ReplayResult;
  markdown: string;
}
