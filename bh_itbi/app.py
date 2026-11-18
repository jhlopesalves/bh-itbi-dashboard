"""Application factory: initialise data once, never execute the reference notebook."""

import pandas as pd
from dash import Dash

from bh_itbi.callbacks import register_callbacks
from bh_itbi.config import END_YEAR, ROOT, SITE_URL, START_YEAR
from bh_itbi.data import DataError, load_source_metadata, load_transactions
from bh_itbi.layout import build_layout
from bh_itbi.models import load_models
from bh_itbi.text import APP_TITLE, APP_UPDATE_TITLE
from bh_itbi.theme import PAPER


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
        title=APP_TITLE,
        update_title=APP_UPDATE_TITLE,
        serve_locally=True,
    )
    period = f"{START_YEAR}–{END_YEAR}"
    app.index_string = f"""<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    {{%metas%}}
    <meta name="description" content="Panorama analítico do mercado residencial de
    Belo Horizonte a partir dos registros do ITBI: distribuição espacial, séries
    temporais, diagnósticos e índices.">
    <meta name="theme-color" content="{PAPER.upper()}">
    <meta property="og:type" content="website">
    <meta property="og:locale" content="pt_BR">
    <meta property="og:title" content="Painel do Mercado Residencial de Belo Horizonte">
    <meta property="og:description"
          content="ITBI em Belo Horizonte: análise espacial e temporal ({period}).">
    <meta property="og:url" content="{SITE_URL}/">
    <meta property="og:image" content="{SITE_URL}/assets/social-preview.png">
    <meta property="og:image:width" content="1280">
    <meta property="og:image:height" content="640">
    <meta property="og:image:alt"
          content="Mapa e distribuição dos valores declarados ao ITBI em Belo Horizonte.">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Painel do Mercado Residencial de Belo Horizonte">
    <meta name="twitter:description"
          content="Análise espacial e temporal do ITBI em Belo Horizonte ({period}).">
    <meta name="twitter:image" content="{SITE_URL}/assets/social-preview.png">
    <title>{{%title%}}</title>
    {{%favicon%}}
    {{%css%}}
  </head>
  <body>
    {{%app_entry%}}
    <footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer>
  </body>
</html>"""
    app.layout = build_layout(neighbourhoods, models, provenance["source_rows"])
    register_callbacks(app, frame, models)

    @app.server.get("/healthz")
    def health():
        # Production reaches this route only after every required table loaded.
        return {"status": "ok"}

    return app
