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
      mode: "fast_direct",
      answer: "Repo rate is the rate at which RBI lends short-term funds to banks.",
      sources: [],
      formatted_sources: [],
      temporal: {
        intent_detected: false,
        executed: false,
        fallback: false,
        single_version: false,
      },
      metadata: {
        predefined: false,
        top_k: 5,
        model_id: "phi:2.7b",
        requested_mode: "fast",
        executed_mode: "fast",
        routing_reason: "fast_direct_path",
        elapsed_ms: 200,
      },
    });
  });

  it("sends a question with selected mode and renders fast mode badge", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });
    const modeSelect = screen.getByLabelText("Response mode");
    expect(modeSelect).toHaveValue("thinking");
    await user.selectOptions(modeSelect, "fast");
    expect(modeSelect).toHaveValue("fast");

    await user.type(
      screen.getByPlaceholderText(/Ask SAARTHI about RBI regulations/i),
      "What is repo rate?",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("Repo rate is the rate at which RBI lends short-term funds to banks.");
    const assistantModeTag = document.querySelector(".message--assistant .mode-tag");
    expect(assistantModeTag).not.toBeNull();
    expect(assistantModeTag).toHaveTextContent("Fast");

    await waitFor(() => {
      expect(apiMock.addMessage).toHaveBeenCalledTimes(2);
      expect(apiMock.askTemporal).toHaveBeenCalledTimes(1);
      expect(apiMock.askTemporal).toHaveBeenCalledWith(
        expect.objectContaining({ mode: "fast" }),
      );
    });
  });
});
