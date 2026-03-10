from pathlib import Path
import json
from datasette_scribe.page_data import __exports__

for e in __exports__:
    p = Path(".") / "frontend" / "src" / "page_data" / (f"{e.__name__}_schema.json")
    p.write_text(json.dumps(e.model_json_schema(), indent=2))
