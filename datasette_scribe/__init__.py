from datasette import hookimpl
from datasette.permissions import Action
from datasette_vite import vite_entry
import os

# Import route modules to trigger route registration on the shared router
from .routes import pages, api_transcriptions, api_speakers, api_collections
from .router import router, SCRIBE_ACCESS_NAME
from .cli import scribe_cli

_ = (pages, api_transcriptions, api_speakers, api_collections)


@hookimpl
def register_routes():
    return router.routes()


@hookimpl
def extra_template_vars(datasette):
    entry = vite_entry(
        datasette=datasette,
        plugin_package="datasette_scribe",
        vite_dev_path=os.environ.get("DATASETTE_SCRIBE_VITE_PATH"),
    )
    return {"datasette_scribe_vite_entry": entry}


@hookimpl
def register_actions(datasette):
    return [
        Action(
            name=SCRIBE_ACCESS_NAME,
            description="Can access scribe pages",
        ),
    ]


@hookimpl
def register_commands(cli):
    cli.add_command(scribe_cli)


@hookimpl
def database_actions(datasette, actor, database):
    async def inner():
        if actor and (await datasette.allowed(action=SCRIBE_ACCESS_NAME, actor=actor)):
            return [
                {
                    "href": datasette.urls.path(f"/{database}/-/scribe"),
                    "label": "Scribe",
                }
            ]
        return []

    return inner
