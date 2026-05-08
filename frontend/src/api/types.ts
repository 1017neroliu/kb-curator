/** TypeScript types matching backend Pydantic schemas */

// ============================================================
// Enumerations
// ============================================================

export type ChangeType = 'new_info' | 'policy_change' | 'contradiction' | 'correction' | 'redundant';
export type ConflictType = 'semantic' | 'structural' | 'temporal';
export type DecisionType = 'accept_new' | 'keep_old' | 'merge' | 'ignore' | 'delete' | 'archive';
export type UpdateStrategy = 'append' | 'create' | 'replace' | 'delete' | 'archive';
export type EntryStatus = 'active' | 'archived' | 'deprecated';
export type ReviewTaskType = 'conflict_resolution' | 'quality_action' | 'deprecation';
export type ReviewTaskStatus = 'pending' | 'in_progress' | 'resolved' | 'expired';
export type Severity = 'info' | 'warning' | 'critical';
export type QualityIssueType = 'low_hit_rate' | 'high_negative_feedback' | 'expired' | 'orphan_entity' | 'metadata_inconsistency';
export type SourceType = 'wiki' | 'confluence' | 'jira' | 'file' | 'conversation_log' | 'webpage';
export type InspectionType = 'full' | 'incremental' | 'targeted';

// ============================================================
// Auth
// ============================================================

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ============================================================
// Data Source
// ============================================================

export interface DataSourceCreate {
  kb_id: string;
  name: string;
  source_type: SourceType;
  connection_config: Record<string, unknown>;
  poll_interval_minutes: number;
  enabled: boolean;
}

export interface DataSourceUpdate {
  name?: string;
  connection_config?: Record<string, unknown>;
  poll_interval_minutes?: number;
  enabled?: boolean;
}

export interface DataSourceRead {
  id: string;
  kb_id: string;
  name: string;
  source_type: string;
  connection_config: Record<string, unknown>;
  poll_interval_minutes: number;
  last_polled_at: string | null;
  last_fingerprint: string | null;
  enabled: boolean;
  created_at: string;
}

// ============================================================
// Change Event
// ============================================================

export interface ChangeEventCreate {
  kb_id: string;
  source_id: string;
  change_type: ChangeType;
  title: string;
  content_before?: string | null;
  content_after?: string | null;
  fingerprint_before?: string | null;
  fingerprint_after?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ChangeEventRead {
  id: string;
  kb_id: string;
  source_id: string;
  change_type: ChangeType;
  title: string;
  content_before: string | null;
  content_after: string | null;
  detected_at: string;
}

// ============================================================
// Knowledge Entry
// ============================================================

export interface KnowledgeEntryCreate {
  kb_id: string;
  title: string;
  content: string;
  source_id: string;
  source_url?: string | null;
  tags?: string[];
  expires_at?: string | null;
  metadata?: Record<string, unknown>;
}

export interface KnowledgeEntryUpdate {
  title?: string | null;
  content?: string | null;
  tags?: string[] | null;
  status?: EntryStatus | null;
  expires_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface KnowledgeEntryRead {
  id: string;
  kb_id: string;
  title: string;
  content: string;
  source_id: string;
  source_url: string | null;
  version: number;
  status: EntryStatus;
  tags: string[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  metadata: Record<string, unknown>;
}

// ============================================================
// Knowledge Graph
// ============================================================

export interface KGEntityCreate {
  kb_id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

export interface KGEntityRead {
  id: string;
  kb_id: string;
  name: string;
  entity_type: string;
  properties: Record<string, unknown>;
  entry_ids: string[];
  confidence: number;
  created_at: string;
}

export interface KGRelationCreate {
  kb_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

export interface KGRelationRead {
  id: string;
  kb_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  properties: Record<string, unknown>;
  confidence: number;
  created_at: string;
}

export interface GraphStats {
  kb_id: string;
  entity_count: number;
  relation_count: number;
  orphan_entity_count: number;
}

// ============================================================
// Conflict
// ============================================================

export interface ConflictRead {
  id: string;
  kb_id: string;
  change_event_id: string;
  conflict_type: ConflictType;
  existing_entry_id: string | null;
  existing_entity_id: string | null;
  new_content: string;
  existing_content: string;
  summary: string;
  severity: Severity;
  detected_at: string;
}

// ============================================================
// Review & Decision
// ============================================================

export interface ReviewTaskRead {
  id: string;
  kb_id: string;
  conflict_id: string | null;
  task_type: ReviewTaskType;
  title: string;
  description: string;
  status: ReviewTaskStatus;
  assigned_to: string | null;
  auto_resolve_at: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ReviewTaskUpdate {
  task_status?: ReviewTaskStatus | null;
  assigned_to?: string | null;
}

export interface DecisionRequest {
  decision_type: DecisionType;
  rationale: string;
  merge_content?: string | null;
}

export interface DecisionRead {
  id: string;
  review_task_id: string;
  decision_type: DecisionType;
  rationale: string;
  decided_by: string;
  merge_content: string | null;
  decided_at: string;
}

// ============================================================
// Quality
// ============================================================

export interface QualityIssue {
  entry_id: string;
  issue_type: QualityIssueType;
  severity: Severity;
  detail: string;
  suggestion: string;
}

export interface QualityReportRead {
  id: string;
  kb_id: string;
  inspection_type: InspectionType;
  total_entries: number;
  issues: QualityIssue[];
  score: number;
  inspected_at: string;
}

// ============================================================
// Search
// ============================================================

export interface SearchRequest {
  query: string;
  top_k?: number;
  filters?: Record<string, unknown>;
}

export interface SearchResult {
  entry_id: string;
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

// ============================================================
// Execution Result
// ============================================================

export interface ExecutionResult {
  success: boolean;
  status: string;
  thread_id: string | null;
  operations_completed: number;
  errors: string[];
  duration_ms: number;
}

// ============================================================
// Knowledge Base
// ============================================================

export interface KnowledgeBaseOverview {
  kb_id: string;
  total_entries: number;
  active_entries: number;
  archived_entries: number;
  deprecated_entries: number;
  data_sources_count: number;
}

// ============================================================
// QA (Question Answering)
// ============================================================

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface QARequest {
  kb_id: string;
  question: string;
  history?: ChatMessage[];
  top_k?: number;
  graph_expand_depth?: number;
}

export interface QASource {
  source_type: 'vector' | 'graph';
  chunk_id?: string | null;
  entry_id?: string | null;
  content?: string | null;
  score?: number | null;
  entity_id?: string | null;
  entity_name?: string | null;
  relation_type?: string | null;
  neighbor_name?: string | null;
}

export interface QAResponse {
  answer: string;
  sources: QASource[];
  question: string;
  kb_id: string;
}

export interface QASSESourceEvent {
  type: 'sources';
  sources: QASource[];
}

export interface QASSETokenEvent {
  type: 'token';
  content: string;
}
