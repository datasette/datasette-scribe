
BASE_URL := "http://localhost:5000"
dev:
  DATASETTE_SECRET=abc123 watchexec \
    --signal SIGKILL --restart --clear \
    -e py,ts,js,html,css,sql -- \
    python -m datasette --root tmp.db \
    -s 'plugins.datasette-scribe.BASE_URL' {{BASE_URL}}

