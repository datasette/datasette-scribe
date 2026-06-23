"""Ensure Datasette core is imported before any test module.

datasette-scribe soft-imports datasette-acl (in permissions.py), and acl imports
datasette.app, which loads entry-point plugins. If a test module imports
datasette_scribe *before* datasette.app has finished loading plugins, scribe and
acl get registered with the plugin manager mid-import — before their hookimpls
(register_actions, datasette_acl_roles, startup) are defined — so those hooks
never attach and acl never creates its tables.

Under `datasette serve` core is always imported first, so this only bites the
test session (test_scribe.py imports datasette_scribe at module top). Importing
datasette.app here, in conftest, guarantees the correct load order for the whole
session, matching real runtime behaviour.
"""

import datasette.app  # noqa: F401  (imported for its plugin-loading side effect)
