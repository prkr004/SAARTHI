# Phase 4 Frontend Deliverables

## UI Map

1. `/login`
- Login form (Employee ID, Password)
- Error state messaging
- Link to registration

2. `/register`
- Registration form (Full Name, Employee ID, Password, Confirm Password)
- Client-side password policy validation
- Success + error feedback

3. `/`
- Protected chat workspace
- Sidebar:
  - User identity summary
  - New chat action
  - Conversation list
  - Rename and delete actions with confirmation dialogs
  - Logout action
- Main panel:
  - Workspace header
  - Model selector and model metadata
  - Alert/notice zone
  - Message history timeline
  - Welcome prompt chips when chat is empty
  - Composer (keyboard friendly Enter-to-send, Shift+Enter newline)
  - Compliance disclaimer footer

4. `*`
- Not found page with return link

## Component Map

### Routing and auth shell
- `src/routes/AppRouter.tsx`
- `src/routes/ProtectedRoute.tsx`
- `src/context/AuthContext.tsx`
- `src/hooks/useAuth.ts`

### API and data layer
- `src/lib/api/client.ts`
- `src/lib/api/endpoints.ts`
- `src/lib/api/types.ts`
- `src/lib/storage.ts`
- `src/lib/errors.ts`

### Page components
- `src/pages/LoginPage.tsx`
- `src/pages/RegisterPage.tsx`
- `src/pages/ChatPage.tsx`
- `src/pages/NotFoundPage.tsx`

### Reusable UI components
- `src/components/auth/AuthCard.tsx`
- `src/components/layout/AppShell.tsx`
- `src/components/layout/Sidebar.tsx`
- `src/components/chat/ModelSelector.tsx`
- `src/components/chat/MessageComposer.tsx`
- `src/components/chat/MessageBubble.tsx`
- `src/components/chat/SourceList.tsx`
- `src/components/chat/TemporalPanel.tsx`

## Parity With Streamlit

1. Secure auth flows
- Login, register, and logout implemented.
- Protected route gating for chat workspace.

2. Persistent multi-chat workspace
- List, create, rename, and delete conversations.
- Conversation switching and message history loading.

3. Ask flow parity
- User message persisted.
- Assistant answer generated through temporal-aware backend endpoint.
- Assistant response persisted.

4. Source rendering parity
- Source links/snippets are shown for assistant responses.

5. Temporal behavior parity
- Supports predefined, standard QA, temporal comparison, temporal fallback, and single-version output modes.

6. Model selector parity
- Model list loaded from API.
- Selected model persisted in local storage.

## Intentional Improvements

1. Better architecture boundaries
- API access and state handling are separated from UI components.

2. Centralized error handling
- Shared mapping for network/timeouts/model/index issues.

3. Retry and timeout strategy
- API client includes transient retry and timeout controls.

4. Request trace readiness
- Frontend architecture supports request-level diagnostics from API headers.

5. Responsive shell
- Desktop split layout and mobile sidebar overlay.

6. Accessibility uplift
- Form labels, status/alert regions, keyboard submit in composer, semantic sections.

## Testing Coverage (Phase 4)

1. `src/tests/auth-flow.test.tsx`
- Login submit path
- Register mismatch validation path

2. `src/tests/chat-workspace.test.tsx`
- Conversation creation action
- Rename and delete action flow

3. `src/tests/ask-flow.test.tsx`
- End-to-end ask flow rendering assistant response and source mode label

## Remaining Gaps Before Phase 5 Hardening

1. End-to-end browser automation is not yet added (Playwright/Cypress).
2. No dedicated toast/notification system yet (using inline notices).
3. No optimistic concurrency handling for simultaneous multi-tab edits.
4. No frontend performance telemetry yet (web vitals + API timing dashboards).
5. No i18n/localization framework yet.
6. No design token build pipeline yet (currently CSS variables in one stylesheet).
