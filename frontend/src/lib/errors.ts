import { ApiClientError } from "./api/client";

export function toUserErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 400 && /employee id.*exists/i.test(error.message)) {
      return "An account with this Employee ID already exists. Please sign in or use a different Employee ID.";
    }
    if (error.code === "request_timeout") {
      return "The request took too long. Please try again.";
    }
    if (error.status === 401) {
      if (/invalid credentials|employee id or password is incorrect/i.test(error.message)) {
        return "Employee ID or password is incorrect.";
      }
      return "Your session has expired. Please login again.";
    }
    if (error.status === 403) {
      return error.message;
    }
    if (error.status === 503 && error.code === "model_unavailable") {
      return "Model service is unavailable. Ensure Ollama is running and the model is installed.";
    }
    if (error.status === 503 && error.code === "vector_index_missing") {
      return "Vector index is missing. Run the ingestion pipeline before asking questions.";
    }
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}
