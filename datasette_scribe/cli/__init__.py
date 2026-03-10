import click

from .add import scribe_add
from .serve import scribe_serve


@click.group(name="scribe")
def scribe_cli():
    "Transcribe audio files"


scribe_cli.add_command(scribe_add)
scribe_cli.add_command(scribe_serve)
