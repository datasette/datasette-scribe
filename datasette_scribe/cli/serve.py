import threading
import time
import webbrowser
from pathlib import Path

import click

from ..router import SCRIBE_ACCESS_NAME


@click.command(name="serve")
@click.argument("db_path", type=click.Path(exists=True))
@click.option("-p", "--port", type=int, default=8001, help="Port to serve on")
@click.option("--host", default="127.0.0.1", help="Host to serve on")
@click.option("--no-open", is_flag=True, help="Don't open browser automatically")
def scribe_serve(db_path, port, host, no_open):
    "Start Datasette serving a scribe database"
    import uvicorn
    from datasette.app import Datasette

    db_path = Path(db_path)
    db_name = db_path.stem

    ds = Datasette(
        files=[str(db_path)],
        settings={"default_allow_sql": False},
        config={"permissions": {SCRIBE_ACCESS_NAME: True}},
    )

    if not no_open:
        url = f"http://{host}:{port}/{db_name}/-/scribe"

        def open_browser():
            time.sleep(1)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    click.echo(f"Starting Datasette on {host}:{port} ...")
    uvicorn.run(ds.app(), host=host, port=port)
