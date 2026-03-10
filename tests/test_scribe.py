from datasette_scribe import __name__ as plugin_name


def test_plugin_name():
    assert plugin_name == "datasette_scribe"
