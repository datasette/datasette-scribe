import click

from .add import scribe_add
from .import_json import scribe_import_json
from .serve import scribe_serve


@click.group(name="scribe")
def scribe_cli():
    "Transcribe audio files"


scribe_cli.add_command(scribe_add)
scribe_cli.add_command(scribe_import_json)
scribe_cli.add_command(scribe_serve)
