"""Production WSGI server: load build artefacts once and never prepare at runtime."""

from bh_itbi.app import create_app

server = create_app(require_prepared=True).server
