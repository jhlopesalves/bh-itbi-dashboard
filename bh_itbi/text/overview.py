"""User-visible Portuguese copy."""

from __future__ import annotations

from collections.abc import Sequence

from bh_itbi import config as cfg
from bh_itbi.formatting import (
    number,
    number_word,
)
from bh_itbi.text.shared import CITY_REFERENCE_EXTRA, TRACE_NAME_EXTRA, TRANSACTIONS_HOVER

TEMPORAL_HOVER = (
    "<b>%{customdata[0]}</b><br>Mediana: R$ %{y:,.0f}/m²"
    "<br>P25–P75: %{customdata[2]} a %{customdata[3]}" + TRANSACTIONS_HOVER + TRACE_NAME_EXTRA
)
TEMPORAL_REFERENCE_HOVER = (
    "%{customdata[0]}<br>BH: R$ %{y:,.0f}/m²" + TRANSACTIONS_HOVER + TRACE_NAME_EXTRA
)
TRAJECTORIES_HOVER = (
    "%{customdata[0]}<br>Mediana: R$ %{y:,.0f}/m²" + TRANSACTIONS_HOVER + TRACE_NAME_EXTRA
)
CITY_TRAJECTORY_HOVER = (
    "%{customdata[0]}<br>BH: R$ %{y:,.0f}/m²"
    + TRANSACTIONS_HOVER
    + f"<extra>{CITY_REFERENCE_EXTRA}</extra>"
)
MAP_HOVER = (
    "<b>%{customdata[1]}</b><br>%{customdata[2]}"
    "<br>Valor declarado real: R$ %{marker.color:,.0f}/m²"
    "<br>Área construída: %{customdata[3]} m²"
    "<br>%{customdata[4]}<extra></extra>"
)
DISTRIBUTION_LABELS: dict[str, str] = {
    "price_per_m2_brl_real": "Valor declarado real (R$/m²)",
    "price_per_m2_brl": "Valor declarado nominal (R$/m²)",
    "value_declared_brl": "Valor declarado nominal (R$)",
}
TEMPORAL_EMPTY_MESSAGE = (
    f"São necessárias {cfg.TEMPORAL_MINIMUM} transações por mês e tipo.<br>Amplie o recorte."
)
MAP_EMPTY_MESSAGE = "Sem registros neste recorte que atendam aos critérios do mapa."
DISTRIBUTION_EMPTY_MESSAGE = (
    f"São necessários ao menos {cfg.DISTRIBUTION_MINIMUM} valores válidos."
)
MAP_COLORBAR_TITLE = "R$/m²<br>real"
LOG_CURRENCY_AXIS_TITLE = "R$ · escala logarítmica"
DISTRIBUTION_HOVER = (
    "%{customdata[0]} a %{customdata[1]}<br>Transações: %{y:,.0f}" + TRACE_NAME_EXTRA
)
COMPARISON_AXIS_TITLE = f"R$/m², valores reais (IPCA {cfg.IPCA_BASE}) · escala log"
OVERVIEW_EYEBROW = "RESUMO ESTATÍSTICO DO RECORTE"
KPI_COUNT_LABEL = "Transações elegíveis"
KPI_COUNT_UNIT = "registros no recorte ativo"
KPI_LATEST_LABEL = "Mediana real no último ano"
KPI_REAL_LABEL = "Mediana real por m²"
KPI_REAL_UNIT = f"R$/m² · corrigida pelo IPCA de {cfg.IPCA_BASE}"
KPI_COVERAGE_LABEL = "Geolocalização por face"
KPI_COVERAGE_UNIT = "dos registros com centroide de face de quadra"
MAP_TITLE = "Distribuição espacial do valor declarado"
MAP_SUBTITLE = (
    "Cor: valor declarado real por m² (IPCA), em escala fixa para todo o período. "
    "Área do marcador: área construída, em escala fixa. "
    "Um clique filtra pelo bairro informado no registro."
)
MAP_STYLE_LABEL = "Fundo do mapa"
MAP_STYLE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Com ruas", "carto-voyager"),
    ("Sem fundo", "white-bg"),
)
DISTRIBUTION_TITLE = "Distribuição dos valores"
DISTRIBUTION_SUBTITLE = "Todas as observações válidas, sem truncamento das caudas."
DISTRIBUTION_METRIC_LABEL = "Medida da distribuição"
DISTRIBUTION_QUARTILE_LABELS: tuple[str, str, str] = ("P25", "Mediana", "P75")
DISTRIBUTION_EMPTY_SUMMARY = "Amostra insuficiente para resumir esta distribuição."
DISTRIBUTION_FOOTNOTE = (
    "Eixo logarítmico; os valores extremos são preservados. "
    f"Linhas pontilhadas: mediana por tipo (mínimo de {cfg.DISTRIBUTION_MINIMUM} observações). "
    "As barras contam transações em faixas de largura crescente."
)
GEOGRAPHY_NOTE_EYEBROW = "LOCALIZAÇÃO GENERALIZADA"
GEOGRAPHY_NOTE_BODY = (
    "Os pontos são centroides de face de quadra, não localizações exatas dos imóveis. "
    "Ao clicar, o filtro usa o bairro informado no registro, "
    "sem inferir seus limites a partir das coordenadas."
)
TREND_TITLE = "Evolução mensal do valor real"
TREND_SUBTITLE = (
    "Mediana e intervalo interquartil (P25–P75), corrigidos pelo IPCA. "
    f"Mínimo de {cfg.TEMPORAL_MINIMUM} transações por mês e tipo."
)
TREND_FOOTNOTE = (
    "A faixa representa a dispersão entre transações, não um intervalo de confiança. "
    "Com recorte geográfico, a linha pontilhada mantém a referência municipal "
    "do mesmo tipo e período."
)
COMPARISON_TITLE = "Comparação entre bairros"
COMPARISON_SUBTITLE = (
    "Distribuição do preço por m² em cada bairro. Faixa escura: P25–P75; "
    "linha clara: mediana. Escala de densidade comum a todos os bairros."
)
COMPARISON_INTERVAL_SUBTITLE = "Ponto: mediana. Faixa escura: P25–P75. Faixa clara: P10–P90."
_REFERENCE_NEIGHBOURHOODS = (
    f"{number_word(len(cfg.DEFAULT_NEIGHBOURHOODS))} bairros de referência"
)
TRAJECTORIES_TITLE = "Trajetórias trimestrais por bairro"
TRAJECTORIES_SUBTITLE = (
    f"Medianas reais por trimestre, com referência municipal. Mínimo de "
    f"{cfg.NEIGHBOURHOOD_QUARTER_MINIMUM} transações por bairro e trimestre; "
    f"{cfg.TEMPORAL_MINIMUM} para a referência de BH."
)


def kpi_coverage_value(geocoded: int, total: int) -> str:
    """Format the face-geocoded percentage KPI or a dash when empty."""
    return f"{number(100 * geocoded / total, 1)}%" if total else "—"


def kpi_latest_unit(latest_year: int) -> str:
    """Display the selected end year and the real-price reference period."""
    return f"R$/m² · {latest_year} · corrigida pelo IPCA de {cfg.IPCA_BASE}"


def kpi_coverage_note(geocoded: int, total: int) -> str:
    """Format the geocoded record count subtitle."""
    return f"{number(geocoded)} de {number(total)} registros"


def map_caption(shown: int, screened: int) -> str:
    """Describe the trimmed and sampled point count drawn on the map."""
    return (
        f"{number(shown)} pontos de {number(screened)} "
        f"registros entre P{cfg.MAP_LOWER_PERCENTILE} e P{cfg.MAP_UPPER_PERCENTILE} "
        f"do valor real por m² de {cfg.START_YEAR}–{cfg.END_YEAR} (escala fixa), "
        "após exigir localização de face "
        f"e área positiva. Amostra de até {number(cfg.MAP_SAMPLE_SIZE)} pontos; "
        "os indicadores usam todo o recorte elegível."
    )


def comparison_caption(
    comparison_names: Sequence[str], *, has_neighbourhood_filter: bool
) -> str:
    """Caption for the quarterly neighbourhood trajectories card."""
    names = ", ".join(name.title() for name in comparison_names)
    scope = (
        "Os bairros selecionados também filtram o mapa e o resumo."
        if has_neighbourhood_filter
        else f"Sem filtro de bairro, exibem-se {_REFERENCE_NEIGHBOURHOODS}."
    )
    return (
        f"Comparação: {names}. {scope} "
        "A referência de Belo Horizonte preserva tipo e período, sem filtro geográfico."
    )


def comparison_note(
    *,
    has_neighbourhood_filter: bool,
    excluded: int,
    missing_ridge_curve: bool,
    show_interval_legend: bool,
) -> str:
    """Footnote for the neighbourhood comparison ridgeline/interval card."""
    note = (
        "A mediana da cidade inclui todos os bairros para o tipo de imóvel "
        "e o período selecionados."
    )
    if not has_neighbourhood_filter:
        note += f" Sem seleção, exibem-se {_REFERENCE_NEIGHBOURHOODS}."
    if excluded == 1:
        note += f" 1 bairro com menos de {cfg.COMPARISON_MINIMUM} transações não exibido."
    elif excluded:
        note += (
            f" {number(excluded)} bairros com menos de "
            f"{cfg.COMPARISON_MINIMUM} transações não exibidos."
        )
    if missing_ridge_curve:
        note += (
            " Curvas indisponíveis na escala comum de densidade são exibidas como intervalos."
        )
    if show_interval_legend:
        note += " Nos resumos, o ponto marca a mediana e a faixa clara cobre P10–P90."
    return note
