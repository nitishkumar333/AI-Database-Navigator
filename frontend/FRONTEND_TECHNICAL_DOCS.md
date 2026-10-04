# SQLNav — Frontend Technical Documentation

> **Version:** 0.2.5 | **Framework:** Next.js 14 (App Router) | **Language:** TypeScript
> **Run:** `npm run dev` | **Port:** 3000

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Folder Structure](#2-folder-structure)
3. [Routing Model](#3-routing-model)
4. [Context / State Management](#4-context--state-management)
5. [Pages](#5-pages)
6. [Components](#6-components)
7. [Type System](#7-type-system)
8. [Utilities](#8-utilities)
9. [UI Component Library](#9-ui-component-library)
10. [Styling & Design System](#10-styling--design-system)
11. [Key Data Flows](#11-key-data-flows)
12. [API Communication](#12-api-communication)
13. [Dependencies](#13-dependencies)
14. [Where to Change Things](#14-where-to-change-things)

---

## 1. Architecture Overview

```
app/layout.tsx  (Root - wraps all context providers)
      |
      +-- Context Provider Stack (nested)
      |     ToastProvider
      |     AuthProvider
      |     RouterProvider
      |     QueryProvider (backend health + sendQuery)
      |     SessionProvider (device fingerprint)
      |     CollectionProvider (connections + KB suggestions)
      |     ConversationProvider (chat state)
      |     SidebarProvider (UI)
      |
      +-- SidebarComponent (navigation)
      |
      +-- app/page.tsx (Single page app router)
            |
            +-- if not authenticated --> LoginPage
            +-- if onboarding incomplete --> OnboardingPage
            +-- if page=chat --> ChatPage
            +-- if page=collection --> CollectionPage
            +-- if page=settings --> SettingsPage
            +-- if page=knowledge --> KnowledgeBasePage
```

The frontend is a **Single Page Application (SPA)** built with Next.js App Router. Navigation between "pages" is done via URL search params (`?page=chat`, `?page=settings`) managed by `RouterContext` — there is no server-side routing beyond the single `/` route.

---

## 2. Folder Structure

```
frontend/
├── package.json                 # Dependencies, scripts
├── next.config.js               # Next.js config (static export support)
├── tailwind.config.ts           # Tailwind theme customization
├── tsconfig.json                # TypeScript config
├── components.json              # shadcn/ui component config
├── postcss.config.mjs
|
├── app/                         # Next.js App Router root
|   ├── layout.tsx               # Root layout: providers + sidebar + metadata
|   ├── page.tsx                 # Root page: auth guard + page routing logic
|   ├── globals.css              # Global CSS variables, Tailwind base, animations
|   ├── getDeviceId.ts           # FingerprintJS hook for device-based session ID
|   ├── icon.svg                 # App favicon
|   ├── types.d.ts               # Global type declarations
|   |
|   ├── pages/                   # Full-page view components
|   |   ├── ChatPage.tsx         # Main chat interface (NL to SQL query + results)
|   |   ├── CollectionPage.tsx   # Database schema explorer (tables, columns, preview)
|   |   ├── KnowledgeBasePage.tsx # Knowledge base management (create/delete KB groups)
|   |   ├── LoginPage.tsx        # Login + register forms
|   |   ├── OnboardingPage.tsx   # First-time setup (connect DB + create KB)
|   |   └── SettingsPage.tsx     # Database connection management
|   |
|   ├── components/
|   |   ├── host.ts              # API base URL (NEXT_PUBLIC_API_URL or localhost:8000)
|   |   ├── types.ts             # Conversation + initialConversation types
|   |   |
|   |   ├── contexts/            # React Context providers (global state)
|   |   |   ├── AuthContext.tsx       # Auth state, login/register/logout, onboarding status
|   |   |   ├── RouterContext.tsx     # Client-side page routing via URL search params
|   |   |   ├── SessionContext.tsx    # Device ID (FingerprintJS), session init
|   |   |   ├── SocketContext.tsx     # sendQuery() REST call, backend health polling
|   |   |   ├── CollectionContext.tsx # DB connections, KB groups, suggestions cache
|   |   |   ├── ConversationContext.tsx # All chat conversation state + CRUD
|   |   |   ├── ChatContext.tsx       # (Minimal) chat-specific shared state
|   |   |   ├── DisplayContext.tsx    # Display state (active display index)
|   |   |   ├── ProcessingContext.tsx # Query processing flag
|   |   |   ├── ToastContext.tsx      # Toast notifications + confirm modals
|   |   |
|   |   ├── chat/                # Chat interface components
|   |   |   ├── QueryInput.tsx        # Text area input + send button (bottom of chat)
|   |   |   ├── RenderChat.tsx        # Main chat message list renderer
|   |   |   ├── MergeDisplays.tsx     # Merges multiple result displays
|   |   |   ├── RenderDisplay.tsx     # Routes a display to its component
|   |   |   |
|   |   |   ├── components/           # Chat UI sub-components
|   |   |   |   ├── CitationBubble.tsx     # Citation reference bubble
|   |   |   |   ├── CollectionSelection.tsx # DB connection dropdown in chat
|   |   |   |   ├── DisplayIcon.tsx         # Icon for display type
|   |   |   |   ├── DisplayPagination.tsx   # Pagination through result pages
|   |   |   |   ├── KnowledgeBaseSelection.tsx # KB group selector in chat
|   |   |   |   ├── MarkdownFormat.tsx      # Renders markdown with syntax highlighting
|   |   |   |   ├── MergedDisplayTabs.tsx   # Tabs when multiple displays are merged
|   |   |   |   └── ViewCodeButton.tsx      # Show/hide generated SQL code
|   |   |   |
|   |   |   └── displays/             # Result display components by type
|   |   |       ├── Generic/
|   |   |       |   ├── BoringGeneric.tsx   # Fallback plain table display
|   |   |       |   └── TextDisplay.tsx     # Text/markdown response display
|   |   |       ├── Product/
|   |   |       |   ├── ProductCard.tsx     # Single product card
|   |   |       |   ├── ProductDisplay.tsx  # Product grid container
|   |   |       |   └── ProductView.tsx     # Full product detail view
|   |   |       ├── QueryCode/
|   |   |       |   └── CodeView.tsx        # SQL code viewer + copy + execute
|   |   |       └── SystemMessages/
|   |   |           ├── ErrorMessageDisplay.tsx        # Error message bubble
|   |   |           ├── InfoMessageDisplay.tsx         # Info message bubble
|   |   |           ├── RateLimitMessageDisplay.tsx    # Rate limit error with timer
|   |   |           ├── SuggestionDisplay.tsx          # Clickable follow-up suggestions
|   |   |           ├── UserMessageDisplay.tsx         # User's sent message bubble
|   |   |           └── WarningDisplay.tsx             # Warning message bubble
|   |   |
|   |   ├── explorer/            # Database schema explorer components
|   |   |   ├── DataTable.tsx         # Data grid with rich cell rendering
|   |   |   └── components/
|   |   |       └── DataCell.tsx      # Individual cell renderer (type-aware formatting)
|   |   |
|   |   ├── navigation/          # Sidebar + navigation components
|   |   |   ├── SidebarComponent.tsx  # Main sidebar (nav items, user info, logout)
|   |   |   ├── HomeSubMenu.tsx       # Conversation list in sidebar
|   |   |   ├── SettingsSubMenu.tsx   # Settings submenu
|   |   |   ├── CopyButton.tsx        # Reusable copy-to-clipboard button
|   |   |   ├── DeleteButton.tsx      # Delete button with confirm dialog
|   |   |   ├── RateLimitDialog.tsx   # Rate limit info dialog
|   |   |   └── SidebarButton.tsx     # Generic sidebar button
|   |   |
|   |   └── shared/              # Shared form components
|   |       ├── ConnectionForm.tsx    # Form to create/test DB connections
|   |       └── KnowledgeBaseForm.tsx # Form to create KB groups (table multi-select)
|   |
|   ├── types/                   # TypeScript type definitions
|   |   ├── chat.ts              # Message, Query, all Payload types
|   |   ├── displays.ts          # ProductPayload, TicketPayload, ChartPayload types
|   |   └── objects.ts           # Collection, Model, Settings, Toast types
|   |
|   └── utils/                   # Frontend utilities
|       └── detectProductdata.ts  # Heuristic detection of product-like query results
|
├── components/
|   └── ui/                      # shadcn/ui component library (Radix UI based)
|       ├── button.tsx, card.tsx, dialog.tsx, input.tsx, label.tsx
|       ├── select.tsx, table.tsx, tabs.tsx, toast.tsx, toaster.tsx
|       ├── sidebar.tsx, sheet.tsx, separator.tsx, skeleton.tsx
|       ├── badge.tsx, avatar.tsx, breadcrumb.tsx, carousel.tsx
|       ├── checkbox.tsx, collapsible.tsx, command.tsx
|       ├── dropdown-menu.tsx, hover-card.tsx, popover.tsx, tooltip.tsx
|       └── alert-dialog.tsx
|
├── hooks/
|   ├── useMobile.tsx            # Detects mobile viewport
|   └── useToast.ts              # Toast hook (used by shadcn Toaster)
|
└── lib/
    └── utils.ts                 # Tailwind cn() utility (clsx + tailwind-merge)
```

---

## 3. Routing Model

The app uses a **custom client-side router** built on URL search params — NOT Next.js file-based routing.

### `app/components/contexts/RouterContext.tsx`

- `currentPage` — one of: `"chat"`, `"collection"`, `"settings"`, `"knowledge"`.
- `changePage(page, params, replace, guarded)` — updates URL search params and `currentPage` state.
  - `replace=true` — replaces history entry instead of pushing.
  - `guarded=true` — shows a confirm modal before navigating (uses `ToastContext.showConfirmModal`).

### URL Structure

```
/?page=chat&conversation={uuid}
/?page=collection&collection={connectionName}
/?page=settings
/?page=knowledge
```

### Page Guard Chain (`app/page.tsx`)

```typescript
if (isLoading)         --> Loading spinner
if (!isAuthenticated)  --> LoginPage
if (!onboarding_complete) --> OnboardingPage
if (page === "chat")   --> ChatPage
if (page === "collection") --> CollectionPage
if (page === "settings") --> SettingsPage
if (page === "knowledge") --> KnowledgeBasePage
```

**To add a new page:**
1. Create `app/pages/NewPage.tsx`.
2. Add `"newpage"` to `validPages` array in `RouterContext.tsx`.
3. Add `{currentPage === "newpage" && <NewPage />}` in `page.tsx`.
4. Add a sidebar item in `SidebarComponent.tsx`.

---

## 4. Context / State Management

Contexts are nested in `layout.tsx` in dependency order. Each is a React Context with a Provider component.

### `AuthContext` — `app/components/contexts/AuthContext.tsx`

**State:**
- `user: AuthUser | null` — `{ id, email, username, is_guest? }`
- `token: string` — JWT Bearer token (also persisted in `localStorage.auth_token`)
- `isAuthenticated: boolean` — derived: `!!user && !!token`
- `isLoading: boolean` — true during initial token validation
- `onboardingStatus: OnboardingStatus | null` — `{ has_connection, has_knowledge_base, onboarding_complete }`

**Key functions:**
- `login(email, password)` — POST to `/api/auth/login`, saves token, fetches user + onboarding status.
- `register(email, username, password)` — POST to `/api/auth/register`, then auto-login.
- `guestLogin()` — POST to `/api/auth/guest-login`, resets stale connection/KB localStorage keys, saves token, fetches user info and preloaded onboarding status.
- `logout()` — clears token + user from state and localStorage.
- `getToken()` — returns current token (state or localStorage fallback).
- `refreshOnboardingStatus()` — re-fetches onboarding status from backend.

**Persistence:** Token stored in `localStorage.auth_token`. On app load, stored token is validated via `GET /api/auth/me`.

---

### `RouterContext` — `app/components/contexts/RouterContext.tsx`

**State:** `currentPage: string`

**Key function:** `changePage(page, params, replace, guarded)` — manages URL params + optional confirm modal for unsaved changes.

Reads the `?page=` URL param via `useSearchParams()` on mount and whenever URL changes.

---

### `QueryContext` — `app/components/contexts/SocketContext.tsx`

**Exported as:** `QueryProvider` / `QueryContext`

**State:** `backendOnline: boolean`

**Key function:** `sendQuery(question, connection_id, knowledge_base_id, conversation_id, query_id)` — makes POST to `/api/query/chat`. Handles 401 (clears auth) and other error statuses.

Health check polls `GET /health` every 120 seconds.

---

### `SessionContext` — `app/components/contexts/SessionContext.tsx`

**State:**
- `id: string | null` — device fingerprint ID (FingerprintJS, cached in localStorage)
- `initialized: boolean` — true after first successful backend connection
- `fetchCollectionFlag: boolean` — toggled to trigger collection refetch
- `unsavedChanges: boolean` — tracks if user has unsaved edits (used to guard navigation)

**Key functions:**
- `triggerFetchCollection()` — toggles `fetchCollectionFlag` to force CollectionContext to refetch.
- `updateUnsavedChanges(bool)` — sets the unsaved changes guard flag.

---

### `CollectionContext` — `app/components/contexts/CollectionContext.tsx`

**State:**
- `collections: Collection[]` — mapped from connections for compatibility.
- `connections: Connection[]` — list of user's DB connections.
- `loadingCollections: boolean`

**Key functions:**
- `fetchCollections()` — GET `/api/connections`, maps to both `connections` and `collections`.
- `fetchSuggestions(connectionId, knowledgeBaseId, forceRefresh)` — POST `/api/suggestions/initial`. Results cached in `suggestionsCache` (a React `useRef` dictionary keyed by `connId_kbId`).
- `clearSuggestionsCache()` — clears the in-memory suggestions cache.

**Connection type:**
```typescript
type Connection = {
  id: number;
  name: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  created_at?: string;
};
```

---

### `ConversationContext` — `app/components/contexts/ConversationContext.tsx`

This is the **largest and most complex context**. It manages all chat state.

**State:**
- `conversations: Conversation[]` — all loaded conversations with their queries/messages.
- `currentConversation: string | null` — UUID of the active conversation.
- `creatingNewConversation: boolean` — debounce flag.

**Key functions:**

| Function | Description |
|---|---|
| `startNewConversation()` | Creates a new local Conversation object with a UUID. Backend creation is deferred until first message. |
| `removeConversation(id)` | DELETE `/api/conversations/{id}`, removes from state. |
| `selectConversation(id)` | Sets current conversation + navigates to chat page. |
| `setConversationTitle(title, id)` | PUT `/api/conversations/{id}` + updates state. |
| `addQueryToConversation(convId, query, queryId)` | Lazily creates conversation on backend (first message trigger). Adds user message to state. |
| `addMessageToConversation(messages, convId, queryId)` | Appends messages to a specific query within a conversation. |
| `finishQuery(convId, queryId)` | Marks query as finished (sets `finished=true`, `query_end`). |
| `handleConversationError(convId)` | Sets `error=true` on a conversation. |
| `addSuggestionToConversation(convId, queryId, connId, kbId)` | POST `/api/suggestions/conversation`, appends suggestion message to conversation. |

**Backend sync:** On mount, fetches all conversation list + full details for each. Calls `rebuildConversation()` to reconstruct frontend data structures from backend message format.

**`rebuildConversation(detail)`** — Groups messages by `query_id`, rebuilds `Query` and `Message` objects from the raw backend response.

---

### `ToastContext` — `app/components/contexts/ToastContext.tsx`

Provides toast notifications and modal dialogs.

**Key functions:**
- `showSuccessToast(title, description?)` — green success notification.
- `showErrorToast(title, description?)` — red error notification.
- `showConfirmModal(title, description, onConfirm)` — confirmation dialog (used by guarded navigation).

---

### `ChatContext` — `app/components/contexts/ChatContext.tsx`

Minimal context scoped to the ChatPage for sharing local chat state between sub-components.

---

### `DisplayContext` — `app/components/contexts/DisplayContext.tsx`

Tracks which display index is currently active (for paginated/merged result views).

---

## 5. Pages

### `app/pages/ChatPage.tsx`

The main application page. (~479 lines)

**Responsibilities:**
- Connection and KB selection (persisted in localStorage).
- Sends queries via `QueryContext.sendQuery()`.
- Builds response messages and dispatches to `ConversationContext`.
- Loads initial query suggestions via `CollectionContext.fetchSuggestions()`.
- Renders `RenderChat` for the message list and `QueryInput` for input.

**Key local state:**
- `selectedConnectionId: number | null` — stored in `localStorage.selected_connection_id`.
- `selectedKnowledgeBaseId: number | null` — stored in `localStorage.selected_knowledge_base_id`.
- `randomPrompts: string[]` — initial AI-generated suggestions shown on empty state.

**Query dispatch flow:**
```
handleSendQuery(query)
  |
  +-- addQueryToConversation(convId, query, queryId)    // Adds user message
  +-- setConversationStatus("Thinking...", convId)
  +-- sendQuery(query, connId, kbId, convId, queryId)   // REST call
  |
  result received:
  |
  +-- if result.rows + detectProductData() --> add "result" message (ProductDisplay)
  +-- else --> add "result" message (generic table)
  +-- add "text" message (response_text)
  +-- finishQuery(convId, queryId)
  +-- setConversationTitle(generated name, convId)
  +-- addSuggestionToConversation(convId, queryId, connId, kbId)
```

**Product detection:** Uses `detectProductData(rows, columns)` to auto-detect if results look like a product catalog and renders `ProductDisplay` instead of a generic table.

---

### `app/pages/CollectionPage.tsx`

Database schema explorer page. (~450 lines)

**URL param:** `?collection={connectionName (display string)}`

**Responsibilities:**
- Finds connection ID from connection name.
- Fetches table list via GET `/api/schema/{connId}/tables`.
- On table select: fetches columns via GET `/api/schema/{connId}/tables/{table}/columns`.
- Fetches preview data via GET `/api/schema/{connId}/tables/{table}/preview`.
- Shows columns metadata (type, nullable, PK, FK) and preview rows.
- Renders `DataTable` component for preview data.

**Local types:**
```typescript
type TableInfo = { name: string; column_count: number; }
type ColumnInfo = { name: string; type: string; nullable: boolean; default: string|null; is_primary_key: boolean; foreign_key: {...} | null; }
type PreviewData = { columns: string[]; rows: Record<string, unknown>[]; }
```

---

### `app/pages/KnowledgeBasePage.tsx`

Knowledge base group management. (~311 lines)

**Responsibilities:**
- Lists existing KB groups per connection.
- Shows form to create new KB groups (table multi-select).
- Deletes KB groups.
- Uses `KnowledgeBaseForm` component for creation form.

**Key functions:**
- `fetchKnowledgeGroups(connId)` — GET `/api/knowledge/{connId}/groups`.
- `deleteKnowledgeGroup(groupId)` — DELETE `/api/knowledge/group/{groupId}`.

---

### `app/pages/SettingsPage.tsx`

Database connection management. (~191 lines)

**Responsibilities:**
- Lists user's DB connections.
- Shows `ConnectionForm` for adding new connections.
- Deletes connections.
- Redirects to Knowledge Base page after successful connection creation.

**Key functions:**
- `loadConnections()` — GET `/api/connections`.
- `deleteConnection(connId)` — DELETE `/api/connections/{connId}`, then refetches CollectionContext.

---

### `app/pages/LoginPage.tsx`

Authentication page with Login, Register, and 1-Click Guest Login. (~approx 15KB)

**Responsibilities:**
- Login form (email + password).
- Register form (email + username + password).
- 1-Click Guest Login button with animated highlight and demo badge.
- Calls `AuthContext.login()` / `AuthContext.register()` / `AuthContext.guestLogin()`.
- Shows error messages on failure.

---

### `app/pages/OnboardingPage.tsx`

Guided first-time setup flow. (~approx 10KB)

**Responsibilities:**
- Step 1: Create database connection (embeds `ConnectionForm`).
- Step 2: Create knowledge base (embeds `KnowledgeBaseForm`).
- Calls `refreshOnboardingStatus()` after each step.
- On completion, transitions to main app.

---

## 6. Components

### Chat Components

#### `app/components/chat/QueryInput.tsx`

The text input at the bottom of the chat. Receives:

```typescript
interface QueryInputProps {
  handleSendQuery: (query: string) => void;
  query_length: number;
  currentStatus: string;          // "Thinking..." | ""
  addDisplacement: (n: number) => void;   // Visual effects
  addDistortion: (n: number) => void;
  selectSettings: () => void;
  selectedConnectionId: number | null;
  onConnectionChange: (id: number | null) => void;
  selectedKnowledgeBaseId: number | null;
  onKnowledgeBaseChange: (id: number | null) => void;
}
```

- Textarea is **disabled** when no KB is selected.
- Enter key submits (Shift+Enter for newline).
- Shows selected KB name as a pill with close button.
- Fetches KB group details to display name + table count.

#### `app/components/chat/RenderChat.tsx`

Main message list renderer (~16KB). Iterates over all queries in the current conversation and renders each message using the appropriate display component.

Routes messages by `message.type`:
- `"User"` → `UserMessageDisplay`
- `"error"` → `ErrorMessageDisplay`
- `"rate_limit_error"` → `RateLimitMessageDisplay`
- `"warning"` → `WarningDisplay`
- `"suggestion"` → `SuggestionDisplay`
- `"result"` → `RenderDisplay` (routes to specific result display)
- `"text"` → `TextDisplay` (markdown)
- `"status"` → status indicator

#### `app/components/chat/components/KnowledgeBaseSelection.tsx`

Dropdown to select a knowledge base group. Fetches from GET `/api/knowledge/user/groups/all`. Groups by connection. Shows connection name and table count for each KB.

#### `app/components/chat/components/CollectionSelection.tsx`

Dropdown to select a database connection. Reads from `CollectionContext.connections`.

#### `app/components/chat/components/ViewCodeButton.tsx`

Toggle button to show/hide the generated SQL. Renders `CodeView` component in a popover.

#### `app/components/chat/components/MarkdownFormat.tsx`

Renders markdown text with GitHub-flavored markdown and syntax highlighting (react-markdown + react-syntax-highlighter + remark-gfm).

#### `app/components/chat/components/DisplayPagination.tsx`

Handles pagination through a large result set split across multiple display pages.

#### `app/components/chat/displays/QueryCode/CodeView.tsx`

Shows the generated SQL with:
- Syntax highlighting.
- Copy to clipboard button.
- "Run" button to re-execute the SQL via POST `/api/query/{conn_id}/execute-sql`.

#### `app/components/chat/displays/Product/ProductDisplay.tsx`

Renders a grid of `ProductCard` components when results are detected as product data.

#### `app/components/chat/displays/Generic/TextDisplay.tsx`

Renders the LLM's natural language response text using `MarkdownFormat`.

#### `app/components/chat/displays/SystemMessages/SuggestionDisplay.tsx`

Renders clickable suggestion chips. On click, calls `handleSendQuery` with the suggestion text.

#### `app/components/chat/displays/SystemMessages/RateLimitMessageDisplay.tsx`

Shows rate limit error with retry countdown timer and a "Rate Limit Info" button.

---

### Navigation Components

#### `app/components/navigation/SidebarComponent.tsx`

Main application sidebar. Only renders when `isAuthenticated && onboarding_complete`.

- **Header:** App logo + backend online/offline indicator.
- **Nav items:** Chat, Knowledge Base, Database Connections.
- **Middle section:** `HomeSubMenu` (conversation list).
- **Footer:** User avatar (first letter of username), email, logout button.

**Active state:** A nav item is highlighted when `currentPage` matches its mode array.

#### `app/components/navigation/HomeSubMenu.tsx`

Renders the list of conversations in the sidebar. Shows conversation name, allows selection and deletion (via `DeleteButton`).

---

### Shared Components

#### `app/components/shared/ConnectionForm.tsx`

Form for creating a database connection (~10KB). Fields: Name, Host, Port, Database, Username, Password.

- "Test Connection" button calls POST `/api/connections/test`.
- "Save" calls POST `/api/connections`.
- Shows success/error state inline.

#### `app/components/shared/KnowledgeBaseForm.tsx`

Form for creating a knowledge base group (~10KB).

- Loads available tables from GET `/api/schema/{connId}/tables`.
- Multi-select checkboxes for table selection.
- Name input.
- Submit calls POST `/api/knowledge/{connId}/group`.

---

### Explorer Components

#### `app/components/explorer/DataTable.tsx`

Rich data table for preview data. Uses `DataCell` for individual cell rendering.

#### `app/components/explorer/components/DataCell.tsx`

Type-aware cell renderer. Detects and formats:
- URLs → clickable links.
- Image URLs → inline image previews.
- Booleans → badge.
- JSON strings → formatted display.
- Long text → truncated with expand.
- Numbers → right-aligned.
- Dates → formatted.

---

## 7. Type System

### `app/components/types.ts`

```typescript
type Conversation = {
  id: string;            // UUID
  name: string;
  queries: { [queryId: string]: Query };  // Map of query ID to Query
  current: string;       // Current status text (e.g., "Thinking...")
  timestamp: Date;
  initialized: boolean;  // Has at least one query
  error: boolean;
};
```

### `app/types/chat.ts`

```typescript
type Query = {
  id: string;
  query: string;          // The user's NL question
  messages: Message[];
  finished: boolean;
  query_start: Date;
  query_end: Date | null;
  NER: NERPayload | null;
  index: number;
};

type Message = {
  type: "result" | "error" | "text" | "User" | "suggestion" | "warning" | ...;
  conversation_id: string;
  id: string;
  user_id: string;
  query_id: string;
  payload: ResultPayload | TextPayload | ErrorPayload | SuggestionPayload | ...;
};

type ResultPayload = {
  type: "table" | "product" | "generic" | "text" | ...;
  metadata: any;
  code: CodePayload;      // { language, title, text } - holds generated SQL
  objects: ...[];         // The actual rows
};

type SuggestionPayload = {
  error: string;
  suggestions: string[];
};
```

### `app/types/displays.ts`

Rich payload types for specialized display components:

- `ProductPayload` — name, price, image, brand, category, rating, etc.
- `TicketPayload` — support ticket fields.
- `ThreadPayload` / `SingleMessagePayload` — conversation message types.
- `DocumentPayload` — document with title, author, content.
- `BarPayload`, `HistogramPayload`, `ScatterOrLinePayload` — chart data.

---

## 8. Utilities

### `app/getDeviceId.ts` — `useDeviceId()`

React hook that:
1. Checks `localStorage.device_id` first.
2. Falls back to FingerprintJS to generate a stable visitor ID.
3. Caches result in localStorage.

Returns a stable string ID used as the session identifier.

### `app/utils/detectProductdata.ts`

**`detectProductData(rows, columns)`** — Heuristic function that decides if query results look like a product catalog:

1. Detects an image column (by name pattern like `image/photo/thumbnail` AND having actual HTTP image URLs in values).
2. Builds a `fieldMapping` mapping ProductPayload fields to actual column names.
3. Returns `isProduct: true` only if there's an image column AND at least a name or price column.

**`mapRowsToProducts(rows, fieldMapping)`** — Converts raw row objects to `ProductPayload[]` using the detected field mapping.

**Column name patterns matched:**
- `name` → product_name, title, item_name
- `price` → price, cost, amount, msrp, mrp
- `image` → image, img, photo, thumbnail, picture
- `brand` → brand, manufacturer, vendor
- `category` → category, type, class, department
- `rating` → rating, score, stars
- `id` → id, product_id, sku, asin
- etc.

**To add a new product field pattern:** Edit `FIELD_PATTERNS` in `detectProductdata.ts`.

### `lib/utils.ts`

```typescript
export function cn(...inputs: ClassValue[]): string  // Tailwind class merging
```

---

## 9. UI Component Library

Located in `components/ui/`. All are based on **Radix UI** primitives with Tailwind styling, generated via **shadcn/ui**.

| Component | File | Usage |
|---|---|---|
| Button | `button.tsx` | All clickable buttons |
| Card | `card.tsx` | Content containers |
| Dialog | `dialog.tsx` | Modal dialogs |
| AlertDialog | `alert-dialog.tsx` | Confirm dialogs (used by DeleteButton, RouterContext) |
| Input | `input.tsx` | Text inputs in forms |
| Label | `label.tsx` | Form labels |
| Select | `select.tsx` | Dropdown selects |
| Table | `table.tsx` | Data tables |
| Tabs | `tabs.tsx` | Tab panels (CollectionPage) |
| Toast / Toaster | `toast.tsx`, `toaster.tsx` | Notifications |
| Sidebar | `sidebar.tsx` | Full sidebar component with all sub-parts |
| Sheet | `sheet.tsx` | Slide-in panels |
| Separator | `separator.tsx` | Visual dividers |
| Skeleton | `skeleton.tsx` | Loading placeholders |
| Badge | `badge.tsx` | Status badges |
| Checkbox | `checkbox.tsx` | KnowledgeBaseForm table selection |
| Carousel | `carousel.tsx` | (available) |
| Command | `command.tsx` | Command palette pattern |
| DropdownMenu | `dropdown-menu.tsx` | Dropdown menus |
| HoverCard | `hover-card.tsx` | Hover preview cards |
| Popover | `popover.tsx` | Popovers (ViewCodeButton) |
| Tooltip | `tooltip.tsx` | Tooltips |

**To add a new shadcn component:** Run `npx shadcn-ui@latest add {component-name}` and it will be added to `components/ui/`.

---

## 10. Styling & Design System

### Fonts (`app/layout.tsx`)
- **Body text:** `Space Grotesk` (CSS var: `--font-text`)
- **Headings:** `Manrope` (CSS var: `--font-heading`)

### CSS Variables (`app/globals.css`)

The design system uses CSS custom properties for theming:

| Variable | Usage |
|---|---|
| `--background` | Main page background |
| `--background_alt` | Slightly elevated surfaces (input areas) |
| `--foreground_alt` | Borders and dividers |
| `--primary` | Primary text color |
| `--secondary` | Muted text |
| `--muted-foreground` | Placeholder text |
| `--accent` | Brand accent color |
| `--warning` | Warning state color |

### Tailwind Config (`tailwind.config.ts`)

Extends default Tailwind with:
- Custom colors mapped to CSS variables.
- Sidebar-specific color tokens.
- Animation utilities (`tailwindcss-animate`).

### Custom Animations (`app/globals.css`)

- `pulsing` — animated opacity pulse for "offline" status indicator.
- `pulsing_color` — colored pulse for "online" indicator.
- `shine` — shimmer animation for "Thinking..." status text.
- `fade-in` — fade-in entrance animation for sidebar.

---

## 11. Key Data Flows

### Full Chat Query Flow

```
User types in QueryInput textarea, presses Enter or Send button
        |
        v
QueryInput.triggerQuery(query)
        |
        v  [disabled if no KB selected]
ChatPage.handleSendQuery(query)
        |
        +-- ConversationContext.addQueryToConversation(convId, query, queryId)
        |     |
        |     +-- If first message: POST /api/conversations (lazy creation)
        |     +-- Adds user message to conversation state
        |
        +-- ConversationContext.setConversationStatus("Thinking...", convId)
        |
        +-- QueryContext.sendQuery(query, connId, kbId, convId, queryId)
              |
              v
        POST /api/query/chat
              |
        [backend processes NL to SQL - see backend docs]
              |
        Response: { success, generated_sql, columns, rows, response_text }
              |
              v
        ChatPage builds messages:
              |
              +-- if rows exist + detectProductData() -> type="result", payload.type="product"
              +-- else if rows exist -> type="result", payload.type="table"
              +-- type="text", payload.type="response" (the response_text markdown)
              |
              +-- ConversationContext.addMessageToConversation(messages, convId, queryId)
              +-- ConversationContext.finishQuery(convId, queryId)
              +-- ConversationContext.setConversationTitle(auto-title, convId)
              +-- ConversationContext.addSuggestionToConversation(convId, queryId, connId, kbId)
                    |
                    v
              POST /api/suggestions/conversation
                    |
              Append suggestion message to conversation
```

### Conversation History Loading Flow

```
App starts, user is authenticated
        |
        v
ConversationContext useEffect (on mount + auth change)
        |
        +-- GET /api/conversations         (list with message counts)
        |
        +-- For each conversation:
        |     GET /api/conversations/{id}  (full detail with messages)
        |     rebuildConversation(detail)  (reconstruct frontend data structures)
        |
        +-- setConversations(fullConversations)
        +-- startNewConversation()         (always start with a fresh empty chat)
```

### Onboarding Flow

```
AuthContext.onboardingStatus.onboarding_complete === false
        |
        v
page.tsx renders OnboardingPage
        |
Step 1: ConnectionForm
        +-- POST /api/connections/test  (test before save)
        +-- POST /api/connections       (save)
        +-- refreshOnboardingStatus()   (check has_connection)
        |
Step 2: KnowledgeBaseForm
        +-- GET /api/schema/{connId}/tables  (load tables to choose from)
        +-- POST /api/knowledge/{connId}/group (create KB)
        +-- refreshOnboardingStatus()   (check onboarding_complete)
        |
onboarding_complete === true
        v
page.tsx renders ChatPage
```

---

## 12. API Communication

### Base URL (`app/components/host.ts`)

```typescript
export const host =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NEXT_PUBLIC_IS_STATIC !== "true" ? "http://localhost:8000" : "");
```

All API calls use `fetch()` with:
```
Authorization: Bearer {token}
Content-Type: application/json
```

Token is retrieved from `AuthContext.getToken()` which falls back to `localStorage.auth_token`.

### Error Handling Patterns

- **401** → `clearAuth()` (logs user out, redirects to login).
- **429** → Rate limit — displayed as `RateLimitMessageDisplay` with retry timer.
- **Network errors** → Caught and converted to error message in conversation.

### API Endpoints Called by Frontend

| Context/Component | Endpoint | Purpose |
|---|---|---|
| AuthContext | POST `/api/auth/register` | Register |
| AuthContext | POST `/api/auth/login` | Login |
| AuthContext | POST `/api/auth/guest-login` | 1-Click Guest login |
| AuthContext | GET `/api/auth/me` | Validate token |
| AuthContext | GET `/api/auth/onboarding-status` | Check onboarding |
| QueryContext | GET `/health` | Backend health check |
| QueryContext | POST `/api/query/chat` | NL to SQL query |
| CollectionContext | GET `/api/connections` | Load connections |
| CollectionContext | POST `/api/suggestions/initial` | Initial suggestions |
| ConversationContext | GET `/api/conversations` | Load conversation list |
| ConversationContext | GET `/api/conversations/{id}` | Load conversation detail |
| ConversationContext | POST `/api/conversations` | Create conversation |
| ConversationContext | PUT `/api/conversations/{id}` | Rename conversation |
| ConversationContext | DELETE `/api/conversations/{id}` | Delete conversation |
| ConversationContext | POST `/api/suggestions/conversation` | Follow-up suggestions |
| SettingsPage | GET `/api/connections` | Load connections |
| SettingsPage | POST `/api/connections/test` | Test connection |
| SettingsPage | POST `/api/connections` | Save connection |
| SettingsPage | DELETE `/api/connections/{id}` | Delete connection |
| CollectionPage | GET `/api/schema/{id}/tables` | List tables |
| CollectionPage | GET `/api/schema/{id}/tables/{t}/columns` | Table columns |
| CollectionPage | GET `/api/schema/{id}/tables/{t}/preview` | Table preview |
| KnowledgeBasePage | GET `/api/knowledge/{id}/groups` | Load KB groups |
| KnowledgeBasePage | POST `/api/knowledge/{id}/group` | Create KB group |
| KnowledgeBasePage | DELETE `/api/knowledge/group/{id}` | Delete KB group |
| KnowledgeBaseForm | GET `/api/schema/{id}/tables` | Load tables for selection |
| QueryInput | GET `/api/knowledge/user/groups/all` | Load all KB groups |
| CodeView | POST `/api/query/{id}/execute-sql` | Execute edited SQL |

---

## 13. Dependencies

**Key dependencies and their purpose:**

| Package | Purpose |
|---|---|
| `next` (14.2.25) | App framework |
| `react` / `react-dom` (18) | UI library |
| `typescript` | Type safety |
| `tailwindcss` | Utility CSS |
| `framer-motion` | Animations (page transitions, message entrances) |
| `@radix-ui/*` | Headless UI primitives for shadcn components |
| `react-icons` | Icon library (MdChatBubbleOutline, GoDatabase, etc.) |
| `react-markdown` | Markdown rendering for LLM responses |
| `react-syntax-highlighter` | SQL / code syntax highlighting |
| `remark-gfm` | GitHub-flavored markdown support |
| `uuid` | UUID generation for conversation/query IDs |
| `@fingerprintjs/fingerprintjs` | Device fingerprinting for session ID |
| `recharts` | Charts (bar, line, scatter) |
| `lucide-react` | Additional icon set |
| `class-variance-authority` | Component variant styling (shadcn) |
| `tailwind-merge` | Safe Tailwind class merging |
| `clsx` | Conditional class names |
| `embla-carousel-react` | Carousel component |

---

## 14. Where to Change Things

| Goal | File(s) to Edit |
|---|---|
| Change backend API URL | `app/components/host.ts` - NEXT_PUBLIC_API_URL env var OR default localhost:8000 |
| Add a new page | Create in `app/pages/`, add to `validPages` in `RouterContext.tsx`, add render in `page.tsx`, add sidebar item in `SidebarComponent.tsx` |
| Add a new sidebar nav item | `app/components/navigation/SidebarComponent.tsx` - items array in useEffect |
| Change app title/metadata | `app/layout.tsx` - metadata object |
| Change fonts | `app/layout.tsx` - font imports, `app/globals.css` - CSS variables |
| Change color theme | `app/globals.css` - CSS custom properties AND `tailwind.config.ts` |
| Add a new message display type | Create component in `app/components/chat/displays/`, add case in `RenderChat.tsx` |
| Change how NL results are rendered | `app/pages/ChatPage.tsx` - handleSendQuery() message building logic |
| Add product field detection pattern | `app/utils/detectProductdata.ts` - FIELD_PATTERNS object |
| Change query suggestions behavior | `app/components/contexts/CollectionContext.tsx` - fetchSuggestions() |
| Change conversation follow-up suggestions | `app/components/contexts/ConversationContext.tsx` - addSuggestionToConversation() |
| Change how conversations are loaded from backend | `app/components/contexts/ConversationContext.tsx` - fetchConversationsFromBackend() and rebuildConversation() |
| Add fields to ConnectionForm | `app/components/shared/ConnectionForm.tsx` - add form fields + update fetch body |
| Add fields to KnowledgeBaseForm | `app/components/shared/KnowledgeBaseForm.tsx` - add form fields |
| Change rate limit error display | `app/components/chat/displays/SystemMessages/RateLimitMessageDisplay.tsx` |
| Change SQL code viewer | `app/components/chat/displays/QueryCode/CodeView.tsx` |
| Change how markdown is rendered | `app/components/chat/components/MarkdownFormat.tsx` |
| Change DataTable cell rendering | `app/components/explorer/components/DataCell.tsx` |
| Add a new shadcn UI component | Run `npx shadcn-ui@latest add {name}`, it goes to `components/ui/` |
| Change localStorage keys used | Search for `localStorage.getItem`/`localStorage.setItem` across context files |
| Change backend health check interval | `app/components/contexts/SocketContext.tsx` - setInterval(checkHealth, 120000) |
| Change auth token expiry handling | `app/components/contexts/AuthContext.tsx` - validateToken() |
| Change the "Thinking..." status label | `app/pages/ChatPage.tsx` - setConversationStatus("Thinking...", ...) |
