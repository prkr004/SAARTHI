import { ApiClientError } from "./api/client";

export function toUserErrorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.code === "request_timeout") {
      return "The request took too long. Please try again.";
    }
    if (error.status === 401) {
      if (/invalid credentials/i.test(error.message)) {
        return error.message;
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
