"""Application factory: initialise data once, never execute the reference notebook."""

import pandas as pd
from dash import Dash

from bh_itbi.callbacks import register_callbacks
from bh_itbi.data import ROOT, load_source_metadata, load_transactions
from bh_itbi.layout import build_layout
from bh_itbi.models import load_models


def create_app(*, frame: pd.DataFrame | None = None, models: dict | None = None) -> Dash:
    """Build a server; explicit frame injection keeps unit tests fully offline."""
    if frame is None:
        frame = load_transactions()
        models = load_models()
        provenance = load_source_metadata()
    else:
        provenance = {"source_rows": len(frame)}
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
    <meta name="theme-color" content="#F7F4EE">
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
    return app
