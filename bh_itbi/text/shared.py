"""User-visible Portuguese copy."""

from __future__ import annotations

from collections.abc import Sequence

from bh_itbi import config as cfg

TYPE_LABELS: dict[str, str] = {"apartment": "Apartamentos", "house": "Casas"}
ALL_TYPES_LABEL = "Apartamentos e casas"
PERIOD_LABEL = "Período"
ALL_NEIGHBOURHOODS_LABEL = "Toda a cidade"
UNKNOWN_NEIGHBOURHOOD_LABEL = "Bairro não informado"
CITY_NAME = "Belo Horizonte"
CITY_REFERENCE_EXTRA = "Referência municipal"
TRACE_NAME_EXTRA = "<extra>%{fullData.name}</extra>"
TRANSACTIONS_HOVER = "<br>Transações: %{customdata[1]}"
AGE_LABELS: dict[str, str] = {
    "new": "Até 2 anos / na planta",
    "3_10": "3 a 10 anos",
    "11_25": "11 a 25 anos",
    "26_plus": "26 anos ou mais",
}
COMPOSITION_LABELS: dict[str, str] = {
    "neighbourhood": "Bairro",
    "area": "Área",
    "age_band": "Faixa de idade",
    "property_type": "Tipo",
    "quarter": "Trimestre",
}
DROPDOWN_LABELS: dict[str, str] = {
    "select_all": "Selecionar todos",
    "deselect_all": "Limpar todos",
    "selected_count": "selecionados",
    "search": "Pesquisar",
    "clear_search": "Limpar pesquisa",
    "clear_selection": "Limpar seleção",
    "no_options_found": "Nenhum resultado",
}
TAB_LABELS: tuple[tuple[str, str], ...] = (
    ("overview", "Panorama"),
    ("diagnostics", "Diagnósticos"),
    ("models", "Índices e trajetórias"),
)
APP_TITLE = "Painel do Mercado Residencial de Belo Horizonte"
APP_UPDATE_TITLE = "Atualizando…"
APP_SUBTITLE = "Panorama analítico do mercado residencial a partir dos registros do ITBI."
APP_META_DESCRIPTION = (
    "Panorama analítico do mercado residencial de Belo Horizonte a partir dos registros "
    "do ITBI: distribuição espacial, séries temporais, diagnósticos e índices."
)
APP_SOCIAL_DESCRIPTION = (
    f"Análise espacial e temporal do ITBI em Belo Horizonte ({cfg.START_YEAR}–{cfg.END_YEAR})."
)
APP_OPEN_GRAPH_DESCRIPTION = (
    f"ITBI em Belo Horizonte: análise espacial e temporal ({cfg.START_YEAR}–{cfg.END_YEAR})."
)
APP_SOCIAL_IMAGE_ALT = "Mapa e distribuição dos valores declarados ao ITBI em Belo Horizonte."
SKIP_LINK_TEXT = "Ir para os gráficos"
MASTHEAD_EYEBROW = "BELO HORIZONTE / MG"
MASTHEAD_ABOUT_LINK = "Sobre os dados"
MASTHEAD_META_LABEL = "Base analítica dos registros"
MASTHEAD_PERIOD_DD = f"{cfg.START_YEAR}–{cfg.END_YEAR}"
MASTHEAD_ROWS_DT = "Registros na fonte"
MASTHEAD_REAL_DT = "Valores reais"
MASTHEAD_REAL_DD = f"IPCA, {cfg.IPCA_BASE}"
PROPERTY_TYPE_LABEL = "Tipo de imóvel"
NEIGHBOURHOODS_LABEL = "Bairros"
RESET_FILTERS_LABEL = "Restaurar filtros"
TABLIST_ARIA_LABEL = "Seções do painel"
FILTER_NOTE_ACTIVE = "Filtros aplicados ao panorama e aos diagnósticos."
FILTER_NOTE_MODELS = (
    f"Índices estimados sobre populações fixas de {cfg.START_YEAR}–{cfg.END_YEAR}; "
    "os filtros não se aplicam a esta seção."
)
LOADING_MESSAGE = "Carregando dados…"
REAL_PRICE_AXIS_TITLE = "R$/m² · IPCA"
TRANSACTIONS_AXIS_TITLE = "Transações"


def period_text(start_year: int, end_year: int) -> str:
    """Format an inclusive year interval or single year."""
    return str(start_year) if start_year == end_year else f"{start_year}–{end_year}"


def scope_text(
    property_type: str, start_year: int, end_year: int, neighbourhoods: Sequence[str]
) -> str:
    """Describe the active property type, year range and neighbourhood selection."""
    label = TYPE_LABELS.get(property_type, ALL_TYPES_LABEL)
    names = ", ".join(n.title() for n in neighbourhoods) or ALL_NEIGHBOURHOODS_LABEL
    return f"{label} · {period_text(start_year, end_year)} · {names}"
