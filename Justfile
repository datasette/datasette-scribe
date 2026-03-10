# Type generation
types-routes:
  uv run python -c 'from datasette_scribe import router; import json;print(json.dumps(router.openapi_document_json()))' \
    | npx --prefix frontend openapi-typescript > frontend/api.d.ts

types-pagedata:
  uv run scripts/typegen-pagedata.py
  for f in frontend/src/page_data/*_schema.json; do \
    npx --prefix frontend json2ts "$f" > "${f%_schema.json}.types.ts"; \
  done

types:
  just types-routes
  just types-pagedata

types-watch:
  watchexec \
    -e py \
    --clear -- \
      just types

# Frontend building
frontend *flags:
    npm run build --prefix frontend {{flags}}

frontend-dev *flags:
    npm run dev --prefix frontend -- --port 5178 {{flags}}

# Formatting
format-frontend *flags:
    npm run format --prefix frontend {{flags}}

format-frontend-check *flags:
    npm run format:check --prefix frontend {{flags}}

format-backend *flags:
    uv run ruff format {{flags}}

format-backend-check *flags:
    uv run ruff format --check {{flags}}

format:
    just format-backend
    just format-frontend

format-check:
    just format-backend-check
    just format-frontend-check

# Type checking
check-frontend:
    npm run check --prefix frontend

check-backend:
    uvx ty check

check:
    just check-backend
    just check-frontend

# Development servers
dev *flags:
    DATASETTE_SECRET=abc123 uv run datasette -p 8005 {{flags}}

dev-with-hmr *flags:
    DATASETTE_SCRIBE_VITE_PATH=http://localhost:5178/ \
    watchexec \
      --stop-signal SIGKILL \
      -e py,html \
      --ignore '*.db' \
      --restart \
      --clear -- \
      just dev {{flags}}
