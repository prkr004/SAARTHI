import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "../pages/ChatPage";

const apiMock = vi.hoisted(() => ({
  listModels: vi.fn(),
  listConversations: vi.fn(),
  ensureDefaultConversation: vi.fn(),
  listMessages: vi.fn(),
  createConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  addMessage: vi.fn(),
  askTemporal: vi.fn(),
}));

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { user_id: 2, employee_id: "EMP9101", full_name: "Ask User" },
    logout: vi.fn(),
  }),
}));

vi.mock("../lib/api/endpoints", () => ({
  api: apiMock,
}));

describe("question ask flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.listModels.mockResolvedValue({
      models: [
        {
          id: "phi:2.7b",
          name: "Phi 2.7B",
          label: "Fast",
          category: "lightweight",
          parameters: "2.7 billion",
          description: "demo",
          ram_needed: "4-6 GB",
          suitable_for: "demo",
          speed: "Very Fast",
          quality: "Good",
          recommended: true,
        },
      ],
      recommended_model: "phi:2.7b",
    });
    apiMock.listConversations.mockResolvedValue([
      {
        id: 88,
        title: "Regulatory Chat",
        created_at: "2026-04-07T00:00:00+00:00",
        updated_at: "2026-04-07T00:00:00+00:00",
        message_count: 0,
      },
    ]);
    apiMock.listMessages.mockResolvedValue([]);
    apiMock.ensureDefaultConversation.mockResolvedValue({ conversation_id: 88 });
    apiMock.addMessage.mockResolvedValue({ message: "saved" });
    apiMock.askTemporal.mockResolvedValue({
      mode: "temporal_comparison",
      answer: "Disclosure rules were strengthened in the latest circular.",
      sources: [],
      formatted_sources: [
        {
          document_name: "RBI Guidelines on Digital Lending",
          document_link: "https://www.rbi.org.in",
          page: 4,
          snippet: "Updated disclosure rules...",
          metadata: { page: 4 },
        },
      ],
      temporal: {
        intent_detected: true,
        executed: true,
        fallback: false,
        single_version: false,
        document_title: "RBI Guidelines on Digital Lending",
      },
      metadata: { predefined: false, top_k: 5, model_id: "phi:2.7b", elapsed_ms: 200 },
    });
  });

  it("sends a question and renders assistant response with sources", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });
    await user.type(
      screen.getByPlaceholderText(/Ask SAARTHI about RBI regulations/i),
      "How has digital lending changed?",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("Disclosure rules were strengthened in the latest circular.");
    expect(screen.getByText("Temporal Compare")).toBeInTheDocument();
    await user.click(screen.getByText("Sources"));
    expect(screen.getByRole("link", { name: "RBI Guidelines on Digital Lending" })).toBeInTheDocument();
    expect(screen.getByText("p. 4")).toBeInTheDocument();

    await waitFor(() => {
      expect(apiMock.addMessage).toHaveBeenCalledTimes(2);
      expect(apiMock.askTemporal).toHaveBeenCalledTimes(1);
    });
  });
});
