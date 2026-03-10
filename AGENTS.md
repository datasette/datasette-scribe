# datasette-scribe

Datasette plugin for audio transcription using the Mistral Voxtral API. Users submit audio URLs, the plugin transcribes them, and stores timestamped, speaker-diarized segments in SQLite.

## Architecture

Two codebases in one repo: a Python Datasette plugin (backend) and a Svelte 5 + TypeScript frontend built with Vite.

```
datasette_scribe/       # Python plugin package
  __init__.py            # Plugin hooks: register_routes, extra_template_vars, database_actions
  router.py              # Shared Router instance + check_permission() decorator
  routes.py              # All GET/POST route handlers + render_page() helper
  page_data.py           # Pydantic models for page data AND API request/response types
  voxtral_api.py         # Mistral transcription API client (httpx)
  schema.sql             # SQLite schema (transcriptions, transcription_entries)
  templates/
    scribe_base.html    # Base Jinja2 template: loads Vite entry + embeds pageData JSON

frontend/
  vite.config.ts         # Vite config with custom page-data-types plugin
  api.d.ts               # Auto-generated OpenAPI types (from just types-routes)
  src/
    store.svelte.ts      # Global Svelte 5 $state store (appState)
    page_data/
      load.ts            # loadPageData<T>() utility
      *_schema.json      # Auto-generated JSON schemas (from just types-pagedata)
      *.types.ts          # Auto-generated TypeScript types (from schemas)
    *Page.svelte         # Page-level components
    *_view.ts            # Vite entry points that mount page components

scripts/
  typegen-pagedata.py    # Generates JSON schemas from Pydantic __exports__
```

## Key Patterns

### Type-safe page data pipeline

Single source of truth flows from Python to TypeScript:

1. Define Pydantic models in `page_data.py`, add to `__exports__` list
2. `just types-pagedata` generates `*_schema.json` files via `scripts/typegen-pagedata.py`, then generates `*.types.ts` via `json2ts`
3. The Vite plugin also generates `.types.ts` on `buildStart` and on HMR when schemas change
4. Route handlers construct Pydantic instances, pass to `render_page()` which calls `.model_dump()`
5. Template embeds as `<script type="application/json" id="pageData">`
6. Frontend calls `loadPageData<GeneratedType>()` to get typed data

### Type-safe API calls

1. API routes use `Annotated[RequestModel, Body()]` for typed request parsing and `output=ResponseModel` for OpenAPI spec
2. `just types-routes` generates `frontend/api.d.ts` from the router's OpenAPI document
3. Frontend uses `openapi-fetch` client typed with `paths` from `api.d.ts`

### Adding a new page

1. Add Pydantic model to `page_data.py` with a comment showing the route pattern, add to `__exports__`
2. Add route in `routes.py` using `render_page()` helper
3. Create `SomePage.svelte` component and `some_view.ts` entry point
4. Add entry to `rollupOptions.input` in `vite.config.ts`
5. Run `just types` to regenerate all type definitions

### Adding a new API endpoint

1. Add request/response Pydantic models to `page_data.py`
2. Add route in `routes.py` with `Annotated[Model, Body()]` parameter and `output=ResponseModel`
3. Run `just types-routes` to regenerate `api.d.ts`
4. Use `openapi-fetch` client in frontend components

### Changing route paths or parameters

Whenever you modify a route's URL pattern or its path parameters (add, remove, rename), run `just types-routes` to regenerate `frontend/api.d.ts`. Never hand-edit `api.d.ts` — it is auto-generated.

### Route registration

Routes use `datasette-plugin-router`. URL path parameters require `str` type annotation (the router checks `param.annotation is str` to resolve URL vars). Routes are decorated with `@router.GET(regex)` / `@router.POST(regex)` then `@check_permission()`.

### Schema migration

Schema uses `CREATE TABLE IF NOT EXISTS` and is executed on every page load via `ensure_schema()`. No migration system — delete DB files manually when schema changes.

## Commands

```
just types              # Regenerate all types (routes + pagedata)
just types-routes       # Regenerate frontend/api.d.ts from OpenAPI spec
just types-pagedata     # Regenerate JSON schemas + TypeScript types from Pydantic models
just types-watch        # Watch .py files and re-run just types

just check              # Run both backend + frontend type checking
just check-backend      # Run ty (Python type checker)
just check-frontend     # Run svelte-check + tsc

just format             # Format both backend + frontend
just format-check       # Check formatting without writing

just dev                # Run datasette dev server on port 8005
just dev-with-hmr       # Run with Vite HMR + auto-restart on Python/HTML changes
just frontend-dev       # Run Vite dev server on port 5178
just frontend           # Production build of frontend
```

## Environment Variables

- `MISTRAL_API_KEY` — required for Voxtral transcription API
- `DATASETTE_SCRIBE_VITE_PATH` — set to Vite dev server URL (e.g. `http://localhost:5178/`) for HMR during development
- `DATASETTE_SECRET` — Datasette session secret (set to `abc123` in dev)
