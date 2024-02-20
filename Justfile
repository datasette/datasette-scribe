
flags := ""
BASE_URL := "http://localhost:5000"


js:
  ./node_modules/.bin/esbuild \
    --bundle --minify --format=esm  --jsx-factory=h --jsx-fragment=Fragment {{flags}} \
    --out-extension:.js=.min.js \
    --out-extension:.css=.min.css \
    datasette_scribe/frontend/targets/**/index.tsx \
    --target=safari12 \
    --outdir=datasette_scribe/static


dev:
  DATASETTE_SECRET=abc123 watchexec \
    --signal SIGKILL --restart --clear \
    -e py,ts,tsx,js,html,css,sql -- \
    python -m datasette --root tmp.db tmp2.db \
    -s 'plugins.datasette-scribe.BASE_URL' {{BASE_URL}}

