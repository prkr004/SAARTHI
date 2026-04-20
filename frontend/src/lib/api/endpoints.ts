import { apiClient } from "./client";
import type {
  ActiveUsersResponse,
  AdminUserSummary,
  ApiEnvelope,
  ApiMessage,
  AskRequest,
  AskResponseData,
  AskTemporalRequest,
  AuthTokenResponse,
  BackfillJobCreateResponse,
  BackfillJobListResponse,
  BackfillJobSummary,
  ConversationSummary,
  DocumentListParams,
  DocumentMetadataUpdatePayload,
  DocumentMetadataUpdateResponse,
  DocumentRegistryListResponse,
  DocumentRegistryRecord,
  DocumentSoftDeleteResponse,
  GenerateDocumentRequest,
  IngestionJobCreateResponse,
  IngestionJobListResponse,
  IngestionJobSummary,
  MessageItem,
  ModelsResponseData,
  ReviewUserResponse,
  SummaryJobCreatePayload,
  SummaryJobCreateResponse,
  SummaryJobListResponse,
  SummaryJobSummary,
  UserProfile,
} from "./types";

interface CreateConversationResponse {
  id: number;
  title: string;
}

interface EnsureDefaultConversationResponse {
  conversation_id: number;
}

function unwrapEnvelope<T>(envelope: ApiEnvelope<T>): T {
  if (!envelope.success || envelope.data === null) {
    throw new Error(envelope.error?.message ?? "Unexpected API envelope.");
  }
  return envelope.data;
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    search.set(key, String(value));
  });

  const query = search.toString();
  return query ? `?${query}` : "";
}

export const api = {
  register(payload: { employee_id: string; full_name: string; password: string; email: string }): Promise<ApiMessage> {
    return apiClient.post<ApiMessage>("/auth/register", payload, { requiresAuth: false });
  },

  login(payload: { employee_id: string; password: string }): Promise<AuthTokenResponse> {
    return apiClient.post<AuthTokenResponse>("/auth/login", payload, { requiresAuth: false });
  },

  me(): Promise<UserProfile> {
    return apiClient.get<UserProfile>("/auth/me");
  },

  logout(): Promise<ApiMessage> {
    return apiClient.post<ApiMessage>("/auth/logout");
  },

  listConversations(): Promise<ConversationSummary[]> {
    return apiClient.get<ConversationSummary[]>("/conversations", { retries: 2 });
  },

  createConversation(title: string): Promise<CreateConversationResponse> {
    return apiClient.post<CreateConversationResponse>("/conversations", { title });
  },

  ensureDefaultConversation(): Promise<EnsureDefaultConversationResponse> {
    return apiClient.post<EnsureDefaultConversationResponse>("/conversations/default");
  },

  renameConversation(conversationId: number, newTitle: string): Promise<CreateConversationResponse> {
    return apiClient.patch<CreateConversationResponse>(`/conversations/${conversationId}`, {
      new_title: newTitle,
    });
  },

  deleteConversation(conversationId: number): Promise<ApiMessage> {
    return apiClient.delete<ApiMessage>(`/conversations/${conversationId}`);
  },

  listMessages(conversationId: number): Promise<MessageItem[]> {
    return apiClient.get<MessageItem[]>(`/conversations/${conversationId}/messages`, { retries: 1 });
  },

  addMessage(conversationId: number, payload: { role: "user" | "assistant"; content: string; sources: unknown[] }): Promise<ApiMessage> {
    return apiClient.post<ApiMessage>(`/conversations/${conversationId}/messages`, payload);
  },

  async listModels(): Promise<ModelsResponseData> {
    const response = await apiClient.get<ApiEnvelope<ModelsResponseData>>("/models", { retries: 2 });
    return unwrapEnvelope(response);
  },

  async ask(payload: AskRequest): Promise<AskResponseData> {
    const response = await apiClient.post<ApiEnvelope<AskResponseData>>("/chat/ask", payload, {
      retries: 1,
      timeoutMs: 90000,
    });
    return unwrapEnvelope(response);
  },

  async askTemporal(payload: AskTemporalRequest): Promise<AskResponseData> {
    const response = await apiClient.post<ApiEnvelope<AskResponseData>>("/chat/ask-temporal", payload, {
      retries: 1,
      timeoutMs: 120000,
    });
    return unwrapEnvelope(response);
  },

  async generateDocument(payload: GenerateDocumentRequest): Promise<Response> {
    return apiClient.requestBlob("/generate-document", {
      method: "POST",
      body: payload,
      retries: 0,
      timeoutMs: 120000,
    });
  },

  listPendingUsers(): Promise<AdminUserSummary[]> {
    return apiClient.get<AdminUserSummary[]>("/admin/users/pending");
  },

  listActiveUsers(): Promise<ActiveUsersResponse> {
    return apiClient.get<ActiveUsersResponse>("/admin/users/active");
  },

  approveUser(userId: number, reviewReason?: string): Promise<ReviewUserResponse> {
    return apiClient.post<ReviewUserResponse>(`/admin/users/${userId}/approve`, {
      review_reason: reviewReason,
    });
  },

  grantUserAccess(employeeId: string, reviewReason?: string): Promise<ReviewUserResponse> {
    return apiClient.post<ReviewUserResponse>("/admin/users/grant-access", {
      employee_id: employeeId,
      review_reason: reviewReason,
    });
  },

  rejectUser(userId: number, reviewReason?: string): Promise<ReviewUserResponse> {
    return apiClient.post<ReviewUserResponse>(`/admin/users/${userId}/reject`, {
      review_reason: reviewReason,
    });
  },

  revokeUserAccess(userId: number, reviewReason?: string): Promise<ReviewUserResponse> {
    return apiClient.post<ReviewUserResponse>(`/admin/users/${userId}/revoke`, {
      review_reason: reviewReason,
    });
  },

  listUserReviewHistory(limit = 100): Promise<{ users: AdminUserSummary[] }> {
    return apiClient.get<{ users: AdminUserSummary[] }>(`/admin/users/history?limit=${limit}`);
  },

  createIngestionJob(files: File[]): Promise<IngestionJobCreateResponse> {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });
    return apiClient.postForm<IngestionJobCreateResponse>("/admin/ingestion/jobs", formData, {
      retries: 0,
      timeoutMs: 120000,
    });
  },

  getIngestionJob(jobId: string): Promise<IngestionJobSummary> {
    return apiClient.get<IngestionJobSummary>(`/admin/ingestion/jobs/${jobId}`);
  },

  listIngestionJobs(limit = 20): Promise<IngestionJobListResponse> {
    return apiClient.get<IngestionJobListResponse>(`/admin/ingestion/jobs?limit=${limit}`);
  },

  createBackfillJob(manifestPath?: string): Promise<BackfillJobCreateResponse> {
    return apiClient.post<BackfillJobCreateResponse>("/admin/backfill/jobs", {
      manifest_path: manifestPath,
    });
  },

  getBackfillJob(jobId: string): Promise<BackfillJobSummary> {
    return apiClient.get<BackfillJobSummary>(`/admin/backfill/jobs/${jobId}`);
  },

  listBackfillJobs(limit = 20): Promise<BackfillJobListResponse> {
    return apiClient.get<BackfillJobListResponse>(`/admin/backfill/jobs?limit=${limit}`);
  },

  listDocuments(params: DocumentListParams = {}): Promise<DocumentRegistryListResponse> {
    const query = buildQuery({
      q: params.q,
      summary_status: params.summary_status,
      include_deleted: params.include_deleted,
      is_deleted: params.is_deleted,
      regulator: params.regulator,
      document_status: params.document_status,
      limit: params.limit,
      offset: params.offset,
    });
    return apiClient.get<DocumentRegistryListResponse>(`/admin/documents${query}`);
  },

  getDocumentDetail(documentId: number, auditLimit = 50): Promise<{ document: DocumentRegistryRecord; audit_log: unknown[] }> {
    return apiClient.get<{ document: DocumentRegistryRecord; audit_log: unknown[] }>(
      `/admin/documents/${documentId}?audit_limit=${auditLimit}`,
    );
  },

  updateDocumentMetadata(documentId: number, payload: DocumentMetadataUpdatePayload): Promise<DocumentMetadataUpdateResponse> {
    return apiClient.patch<DocumentMetadataUpdateResponse>(`/admin/documents/${documentId}`, payload);
  },

  softDeleteDocument(documentId: number, reason?: string): Promise<DocumentSoftDeleteResponse> {
    return apiClient.post<DocumentSoftDeleteResponse>(`/admin/documents/${documentId}/soft-delete`, { reason });
  },

  createSummaryJob(payload: SummaryJobCreatePayload = {}): Promise<SummaryJobCreateResponse> {
    return apiClient.post<SummaryJobCreateResponse>("/admin/summary/jobs", payload);
  },

  getSummaryJob(jobId: string): Promise<SummaryJobSummary> {
    return apiClient.get<SummaryJobSummary>(`/admin/summary/jobs/${jobId}`);
  },

  listSummaryJobs(limit = 20): Promise<SummaryJobListResponse> {
    return apiClient.get<SummaryJobListResponse>(`/admin/summary/jobs?limit=${limit}`);
  },
};
