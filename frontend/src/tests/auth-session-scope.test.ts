import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/api/client";
import { storage } from "../lib/storage";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("auth session scoping", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stores admin and employee tokens independently", () => {
    storage.setToken("employee-token", "employee");
    storage.setToken("admin-token", "admin");

    expect(storage.getToken("employee")).toBe("employee-token");
    expect(storage.getToken("admin")).toBe("admin-token");
    expect(storage.getTokenForPath("/admin/dashboard")).toBe("admin-token");
    expect(storage.getTokenForPath("/chat")).toBe("employee-token");
  });

  it("uses admin token for admin route API calls", async () => {
    storage.setToken("employee-token", "employee");
    storage.setToken("admin-token", "admin");
    window.history.pushState({}, "", "/admin/dashboard");

    const fetchSpy = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({ ok: true }));
    const client = new ApiClient("http://localhost:8000/api/v1");

    await client.get("/health");

    const [, options] = fetchSpy.mock.calls[0] ?? [];
    const headers = (options as RequestInit)?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer admin-token");
  });

  it("uses employee token for employee route API calls", async () => {
    storage.setToken("employee-token", "employee");
    storage.setToken("admin-token", "admin");
    window.history.pushState({}, "", "/");

    const fetchSpy = vi.spyOn(window, "fetch").mockResolvedValue(jsonResponse({ ok: true }));
    const client = new ApiClient("http://localhost:8000/api/v1");

    await client.get("/health");

    const [, options] = fetchSpy.mock.calls[0] ?? [];
    const headers = (options as RequestInit)?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer employee-token");
  });
});
