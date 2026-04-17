export type Role = "user" | "assistant";

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

export interface AskTemporalRequest extends AskRequest {
  comparison_method: "difflib" | "llm" | "both";
}

export interface TemporalPayload {
  intent_detected: boolean;
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
  | "qa"
  | "qa_fallback_non_temporal"
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
