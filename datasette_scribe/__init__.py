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


try:
    from datasette_sidebar.hookspecs import SidebarApp
    # TODO clean this up
    def _first_visible_db(datasette):
        for name in datasette.databases:
            if name != "_internal":
                return name
        return "_internal"

    @hookimpl
    def datasette_sidebar_apps(datasette):
        return [
            SidebarApp(
                label="Scribe",
                description="Audio transcription manager",
                href=lambda db: f"/{db}/-/scribe" if db else f"/{_first_visible_db(datasette)}/-/scribe",
                icon='<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V14.5h2a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1h2v-1.525A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/></svg>',
                color="#6c63ff",
            ),
        ]

except ImportError:
    pass
