"""Application factory: initialise data once, never execute the reference notebook."""

from __future__ import annotations

from string import Template

import pandas as pd
from dash import Dash

from bh_itbi.callbacks import register_callbacks
from bh_itbi.config import ROOT, SITE_URL
from bh_itbi.data import DataError, load_source_metadata, load_transactions
from bh_itbi.layout import build_layout
from bh_itbi.models import AuditEndpoint, PreparedModels, load_audit_endpoint, load_models
from bh_itbi.text import shared as text
from bh_itbi.theme import PAPER

INDEX_TEMPLATE = Template(
    (ROOT / "bh_itbi" / "templates" / "index.html").read_text(encoding="utf-8").rstrip("\n")
).substitute(
    site_url=SITE_URL,
    title=text.APP_TITLE,
    theme_color=PAPER.upper(),
    description=text.APP_META_DESCRIPTION,
    open_graph_description=text.APP_OPEN_GRAPH_DESCRIPTION,
    social_description=text.APP_SOCIAL_DESCRIPTION,
    social_image_alt=text.APP_SOCIAL_IMAGE_ALT,
)


def create_app(
    *,
    frame: pd.DataFrame | None = None,
    models: PreparedModels | None = None,
    audit_endpoint: AuditEndpoint | None = None,
    require_prepared: bool = False,
) -> Dash:
    """Build a server; explicit frame injection keeps unit tests fully offline."""
    if frame is None:
        frame = load_transactions(allow_prepare=not require_prepared)
        models = load_models()
        audit_endpoint = load_audit_endpoint()
        provenance = load_source_metadata(allow_prepare=not require_prepared)
        source_rows = provenance["source_rows"]
    else:
        source_rows = len(frame)
    if require_prepared and models is None:
        raise DataError(
            "Prepared models are missing or incompatible. Run python main.py prepare."
        )
    neighbourhoods = sorted(frame["neighbourhood"].dropna().unique().tolist())
    app = Dash(
        __name__,
        assets_folder=str(ROOT / "assets"),
        title=text.APP_TITLE,
        update_title=text.APP_UPDATE_TITLE,
        serve_locally=True,
    )
    app.index_string = INDEX_TEMPLATE
    app.layout = build_layout(neighbourhoods, models, source_rows, audit_endpoint)
    register_callbacks(app, frame, models)

    @app.server.get("/healthz")
    def health() -> dict[str, str]:
        # Production reaches this route only after every required table loaded.
        return {"status": "ok"}

    return app
