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
    user: { user_id: 1, employee_id: "EMP9001", full_name: "Workspace User" },
    logout: vi.fn(),
  }),
}));

vi.mock("../lib/api/endpoints", () => ({
  api: apiMock,
}));

describe("chat workspace", () => {
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
        id: 21,
        title: "New Chat",
        created_at: "2026-04-07T00:00:00+00:00",
        updated_at: "2026-04-07T00:00:00+00:00",
        message_count: 0,
      },
    ]);
    apiMock.listMessages.mockResolvedValue([]);
    apiMock.createConversation.mockResolvedValue({ id: 55, title: "New Chat" });
    apiMock.renameConversation.mockResolvedValue({ id: 21, title: "Renamed Chat" });
    apiMock.deleteConversation.mockResolvedValue({ message: "deleted" });
    apiMock.ensureDefaultConversation.mockResolvedValue({ conversation_id: 21 });
    apiMock.addMessage.mockResolvedValue({ message: "ok" });
    apiMock.askTemporal.mockResolvedValue({
      mode: "predefined",
      answer: "hello",
      sources: [],
      formatted_sources: [],
      metadata: { predefined: true, top_k: 5, elapsed_ms: 1 },
    });
  });

  it("creates new conversation from sidebar", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByText("Employee Workspace");
    await user.click(screen.getByRole("button", { name: "+ New Chat" }));

    await waitFor(() => {
      expect(apiMock.createConversation).toHaveBeenCalled();
    });
  });

  it("renames and deletes with confirmation helpers", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "prompt").mockReturnValue("Risk Review");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    await screen.findByText("Employee Workspace");

    await user.click(screen.getByRole("button", { name: "Rename New Chat" }));
    await waitFor(() => {
      expect(apiMock.renameConversation).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: "Delete New Chat" }));
    await waitFor(() => {
      expect(apiMock.deleteConversation).toHaveBeenCalled();
    });
  });
});
