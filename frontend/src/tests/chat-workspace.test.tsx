import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
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

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-path">{location.pathname}</div>;
}

const FAST_REPLY = {
  mode: "fast_direct",
  answer: "quick",
  sources: [],
  formatted_sources: [],
  metadata: { predefined: false, top_k: 5, elapsed_ms: 5 },
};

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

  it("falls back to New chat when conversation title is blank", async () => {
    const user = userEvent.setup();
    apiMock.listConversations.mockResolvedValueOnce([
      {
        id: 33,
        title: "   ",
        created_at: "2026-04-07T00:00:00+00:00",
        updated_at: "2026-04-07T00:00:00+00:00",
        message_count: 0,
      },
    ]);

    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("button", { name: "Rename New chat" });
    await user.type(screen.getByPlaceholderText("Search chats"), "new");

    expect(screen.queryByText('No chats match "new".')).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rename New chat" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete New chat" })).toBeInTheDocument();
  });

  it("creates new conversation from sidebar", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });
    await user.click(screen.getByRole("button", { name: "New chat" }));

    await waitFor(() => {
      expect(apiMock.createConversation).toHaveBeenCalled();
    });
  });

  it("prefills composer from starters and prompt library without auto-sending", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });

    await user.click(screen.getByRole("button", { name: "Digital Lending Obligations" }));
    const input = screen.getByLabelText("Ask SAARTHI a question");
    expect(input).toHaveValue("Summarize key obligations for digital lending apps under RBI guidelines.");
    await waitFor(() => expect(input).toHaveFocus());
    expect(apiMock.askTemporal).toHaveBeenCalledTimes(0);

    await user.click(screen.getByRole("button", { name: "Prompt Library" }));
    await user.click(screen.getByRole("button", { name: /KYC Due Diligence Steps/i }));

    expect(input).toHaveValue("Explain customer due diligence steps under the RBI KYC Master Direction.");
    await waitFor(() => expect(input).toHaveFocus());
    expect(apiMock.askTemporal).toHaveBeenCalledTimes(0);
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
    await screen.findByRole("heading", { name: "SAARTHI" });

    await user.click(screen.getByRole("button", { name: "Rename New Chat" }));
    await waitFor(() => {
      expect(apiMock.renameConversation).toHaveBeenCalled();
    });

    await user.click(screen.getByRole("button", { name: "Delete New Chat" }));
    await waitFor(() => {
      expect(apiMock.deleteConversation).toHaveBeenCalled();
    });
  });

  it("updates composer response mode and includes it in ask payload", async () => {
    const user = userEvent.setup();
    apiMock.askTemporal.mockResolvedValueOnce(FAST_REPLY);

    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });

    const thinkToggle = screen.getByRole("button", { name: "Think mode" });
    const fastToggle = screen.getByRole("button", { name: "Fast mode" });
    expect(thinkToggle).toHaveAttribute("aria-pressed", "true");
    expect(fastToggle).toHaveAttribute("aria-pressed", "false");

    await user.click(fastToggle);
    expect(fastToggle).toHaveAttribute("aria-pressed", "true");

    await user.type(screen.getByPlaceholderText(/Ask SAARTHI about RBI regulations/i), "Quick test");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("quick");
    const assistantModeTag = document.querySelector(".message--assistant .mode-tag");
    expect(assistantModeTag).not.toBeNull();
    expect(assistantModeTag).toHaveTextContent("Fast");

    await waitFor(() => {
      expect(apiMock.askTemporal).toHaveBeenCalledWith(
        expect.objectContaining({ mode: "fast" }),
      );
    });
  });

  it("keeps user on the same route when stop is clicked", async () => {
    const user = userEvent.setup();

    apiMock.askTemporal.mockImplementationOnce(() => new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={["/admin/chat"]}>
        <LocationProbe />
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });
    await user.type(screen.getByPlaceholderText(/Ask SAARTHI about RBI regulations/i), "Stop test");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await user.click(await screen.findByRole("button", { name: "Stop generating response" }));
    expect(screen.getByTestId("location-path")).toHaveTextContent("/admin/chat");
  });

  it("keeps employee chat route stable when stop is clicked", async () => {
    const user = userEvent.setup();

    apiMock.askTemporal.mockImplementationOnce(() => new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={["/"]}>
        <LocationProbe />
        <ChatPage />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: "SAARTHI" });
    await user.type(screen.getByPlaceholderText(/Ask SAARTHI about RBI regulations/i), "Stop test employee");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await user.click(await screen.findByRole("button", { name: "Stop generating response" }));
    expect(screen.getByTestId("location-path")).toHaveTextContent("/");
  });
});
