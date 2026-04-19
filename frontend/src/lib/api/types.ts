export type Role = "user" | "assistant";
export type UserRole = "admin" | "user";
export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiEnvelope<T> {
  success: boolean;
  request_id: string;
  timestamp: string;
  data: T | null;
  error: ApiErrorPayload | null;
}

export interface ApiMessage {
  message: string;
}

export interface UserProfile {
  user_id: number;
  employee_id: string;
  full_name: string;
  role: UserRole;
  approval_status: ApprovalStatus;
  email?: string | null;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: UserProfile;
}

export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageItem {
  role: Role;
  content: string;
  sources: SourceItem[];
}

export interface SourceItem {
  content?: string;
  metadata?: Record<string, unknown>;
  document_name?: string;
  document_link?: string | null;
  page?: number | null;
  snippet?: string;
}

export interface ModelConfig {
  id: string;
  name: string;
  label: string;
  category: string;
  parameters: string;
  description: string;
  ram_needed: string;
  suitable_for: string;
  speed: string;
  quality: string;
  recommended: boolean;
}

export interface ModelsResponseData {
  models: ModelConfig[];
  recommended_model: string;
}

export interface AskRequest {
  question: string;
  model_id?: string;
  top_k: number;
}

export type AskMode = "fast" | "thinking";

export interface AskTemporalRequest extends AskRequest {
  comparison_method: "difflib" | "llm" | "both";
  mode?: AskMode;
}

export interface TemporalPayload {
  intent_detected: boolean;
  intent_class?: string;
  executed: boolean;
  fallback: boolean;
  fallback_reason?: string;
  single_version: boolean;
  document_title?: string;
  current_date?: string;
  previous_date?: string;
  comparison?: Record<string, unknown> | null;
}

export type AssistantMode =
  | "predefined"
  | "fast_direct"
  | "qa"
  | "qa_fallback_non_temporal"
  | "drafting_stub"
  | "temporal_comparison"
  | "temporal_fallback"
  | "temporal_single_version";

export interface AskResponseData {
  mode: AssistantMode;
  answer: string;
  sources: SourceItem[];
  formatted_sources: SourceItem[];
  temporal?: TemporalPayload;
  metadata: {
    predefined: boolean;
    top_k: number;
    model_id?: string;
    comparison_method?: string;
    requested_mode?: AskMode;
    executed_mode?: AskMode;
    routing_reason?: string;
    elapsed_ms: number;
  };
}

export interface FrontendMessage extends MessageItem {
  id: string;
  mode?: AssistantMode;
  temporal?: TemporalPayload;
  pending?: boolean;
}

export interface GenerateDocumentRequest {
  document_type: "circular" | "press_release" | "advisory";
  query: string;
  audience: string;
}

export interface AdminUserSummary {
  id: number;
  employee_id: string;
  full_name: string;
  email?: string | null;
  role: UserRole;
  approval_status: ApprovalStatus;
  created_at: string;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  review_reason?: string | null;
  reviewer_employee_id?: string | null;
  reviewer_name?: string | null;
}

export interface ReviewUserResponse {
  message: string;
  user: AdminUserSummary;
  warning?: string | null;
}

export type IngestionJobStatus = "queued" | "running" | "completed" | "failed";

export interface IngestionJobSummary {
  job_id: string;
  created_by: number;
  created_by_employee_id?: string | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  status: IngestionJobStatus;
  total_files: number;
  processed_files: number;
  total_chunks: number;
  progress_percent: number;
  current_file?: string | null;
  error_message?: string | null;
}

export interface IngestionJobCreateResponse {
  message: string;
  job: IngestionJobSummary;
}

export interface IngestionJobListResponse {
  jobs: IngestionJobSummary[];
}

export interface ActiveUsersResponse {
  users: AdminUserSummary[];
}
