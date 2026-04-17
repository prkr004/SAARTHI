import { apiClient } from "./client";
import type {
  ApiEnvelope,
  ApiMessage,
  AskRequest,
  AskResponseData,
  AskTemporalRequest,
  AuthTokenResponse,
  ConversationSummary,
  GenerateDocumentRequest,
  MessageItem,
  ModelsResponseData,
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

export const api = {
  register(payload: { employee_id: string; full_name: string; password: string }): Promise<ApiMessage> {
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
};
