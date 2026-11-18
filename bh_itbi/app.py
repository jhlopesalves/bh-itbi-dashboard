"""Application factory: initialise data once, never execute the reference notebook."""

import pandas as pd
from dash import Dash

from bh_itbi.callbacks import register_callbacks
from bh_itbi.data import ROOT, DataError, load_source_metadata, load_transactions
from bh_itbi.layout import build_layout
from bh_itbi.models import load_models


def create_app(
    *,
    frame: pd.DataFrame | None = None,
    models: dict | None = None,
    require_prepared: bool = False,
) -> Dash:
    """Build a server; explicit frame injection keeps unit tests fully offline."""
    if frame is None:
        frame = load_transactions(allow_prepare=not require_prepared)
        models = load_models()
        provenance = load_source_metadata(allow_prepare=not require_prepared)
    else:
        provenance = {"source_rows": len(frame)}
    if require_prepared and models is None:
        raise DataError(
            "Modelos preparados ausentes ou incompatíveis. Execute main.py prepare."
        )
    neighbourhoods = sorted(frame["neighbourhood"].dropna().unique().tolist())
    app = Dash(
        __name__,
        assets_folder=str(ROOT / "assets"),
        title="Painel do Mercado Residencial de Belo Horizonte",
        update_title="Atualizando…",
        serve_locally=True,
    )
    app.index_string = """<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    {%metas%}
    <meta name="description" content="Panorama analítico do mercado residencial de
    Belo Horizonte a partir dos registros do ITBI: distribuição espacial, séries
    temporais, diagnósticos e índices.">
    <meta name="theme-color" content="#FAFAF8">
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
  </head>
  <body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
  </body>
</html>"""
    app.layout = build_layout(neighbourhoods, models, provenance["source_rows"])
    register_callbacks(app, frame, models)

    @app.server.get("/healthz")
    def health():
        # Production reaches this route only after every required table loaded.
        return {"status": "ok"}

    return app
