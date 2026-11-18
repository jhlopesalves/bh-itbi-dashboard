"""User-visible Portuguese copy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bh_itbi import config as cfg
from bh_itbi.formatting import (
    composition_number,
    number,
    number_word,
)
from bh_itbi.text.shared import (
    ALL_TYPES_LABEL,
    COMPOSITION_LABELS,
    TRACE_NAME_EXTRA,
    TYPE_LABELS,
)

CLUSTER_INDEX_AXIS_TITLE = f"Índice · {cfg.START_YEAR} = {cfg.INDEX_BASE}"
MODELS_UNAVAILABLE_BANNER = (
    "Os índices ainda não estão disponíveis nesta instalação. "
    "Consulte a preparação descrita no README."
)
MODELS_EYEBROW = f"POPULAÇÕES FIXAS · {cfg.START_YEAR}–{cfg.END_YEAR}"
MODELS_SECTION_TITLE = "Índice hedônico e agrupamento de trajetórias"
MODELS_DESCRIPTION = (
    "Estimativas sobre a amostra fixa descrita em cada análise. "
    "Os filtros do panorama não alteram estes resultados."
)
MODEL_METRIC_OBSERVATIONS = "observações no modelo hedônico"
MODEL_METRIC_NEIGHBOURHOODS = (
    f"bairros com ao menos {cfg.HEDONIC_NEIGHBOURHOOD_MINIMUM} registros"
)
MODEL_METRIC_R2 = "R² · log do valor declarado real por m²"
HEDONIC_TITLE = "Preço ajustado, média bruta e o que separa as duas"
HEDONIC_SUBTITLE = (
    f"{ALL_TYPES_LABEL} · escala log, 1º tri. {cfg.START_YEAR} = {cfg.INDEX_BASE} · faixas: "
    "contribuição de cada característica observada para a diferença entre "
    "a média bruta e o índice (log × 100)."
)
HEDONIC_RAW_TRACE_NAME = "Média bruta"
HEDONIC_INDEX_LABEL = "Índice hedônico"
_HEDONIC_CI_PERCENT = f"{number(cfg.HEDONIC_CONFIDENCE_LEVEL * 100)}%"
_HEDONIC_CI = f"IC {_HEDONIC_CI_PERCENT}"
HEDONIC_INDEX_TRACE_NAME = f"{HEDONIC_INDEX_LABEL} · {_HEDONIC_CI}"
CLUSTERS_TITLE = "Agrupamento de trajetórias por similaridade"
CLUSTERS_MEMBERS_SUMMARY = "Composição de cada grupo"
CLUSTER_GROUP_LABEL = "Grupo de trajetórias"
CLUSTER_ALL_GROUPS_LABEL = "Todos os grupos"
CLUSTER_TRAJECTORY_HOVER = (
    "%{x}<br>Índice: %{y:.1f}<br>Transações: %{customdata[0]:,.0f}" + TRACE_NAME_EXTRA
)
CLUSTER_CENTRE_HOVER = "%{x}<br>Centro do grupo: %{y:.1f}" + TRACE_NAME_EXTRA


def hedonic_note(final_contributions: Mapping[str, float]) -> str:
    """Explain the hedonic estimand and include groups without direct labels."""
    note = (
        "Regressão do log do valor declarado real/m² com controles de log da área, "
        "faixa de idade, tipo, bairro e trimestre; erros agrupados por bairro. "
        "A média bruta é a média geométrica da mesma amostra. As faixas são uma "
        "identidade contábil do modelo ajustado: variação do log médio bruto = "
        "variação do índice + Σ β × variação das médias das características. "
        "Mudanças em características não observadas (conservação, andar, acabamento) "
        "não aparecem nas faixas e podem afetar o índice; o índice não é uma estimativa "
        f"causal. A base {cfg.INDEX_BASE} é uma normalização."
    )
    for group, value in final_contributions.items():
        if abs(value) < cfg.COMPOSITION_LABEL_THRESHOLD:
            label = COMPOSITION_LABELS[group]
            note += (
                f" {label}: contribuição desprezível ({composition_number(value)}) "
                "no último trimestre."
            )
    if any(value > 0 for value in final_contributions.values()):
        note += (
            " Faixas acima do índice indicam características cuja mudança de composição "
            "elevou a média bruta."
        )
    return note


def hedonic_hover(groups: Sequence[str]) -> str:
    """Label the adjusted index, its interval and the composition terms in order."""
    contributions = "".join(
        f"<br>{COMPOSITION_LABELS[group]}: %{{customdata[{i}]}}"
        for i, group in enumerate(groups, start=5)
    )
    return (
        f"<b>%{{customdata[0]}}</b><br>{HEDONIC_INDEX_LABEL}: %{{customdata[1]}}"
        f"<br>{_HEDONIC_CI}: %{{customdata[2]}} a %{{customdata[3]}}"
        f"<br>{HEDONIC_RAW_TRACE_NAME}: %{{customdata[4]}}<br><br>Composição (log × 100)"
        f"{contributions}<extra></extra>"
    )


def clusters_subtitle(n_neighbourhoods: int) -> str:
    """Subtitle for the k-means neighbourhood trajectory clusters card."""
    return (
        f"{TYPE_LABELS['apartment']} · K-médias, {number_word(cfg.CLUSTER_K)} grupos · "
        f"{number(n_neighbourhoods)} bairros com ao menos {cfg.CLUSTER_YEAR_MINIMUM} "
        f"registros em cada um dos {number_word(len(cfg.YEARS))} anos · "
        f"{cfg.START_YEAR} = {cfg.INDEX_BASE}."
    )


def clusters_footnote(silhouette: float) -> str:
    """Footnote for the k-means neighbourhood trajectory clusters card."""
    return (
        "Linhas finas: bairros; linhas fortes: centros dos grupos. "
        "O número de grupos é uma escolha analítica, não um ótimo estimado. "
        f"Silhueta: {number(silhouette, 2)}; há sobreposição entre trajetórias. "
        "Os grupos descrevem a forma da evolução, não o nível de preços "
        "ou regiões administrativas."
    )


def cluster_group_heading(group_id: int, count: int) -> str:
    """Heading and trace label for one trajectory cluster group."""
    return f"{cluster_group_name(group_id)} · {count} bairros"


def cluster_group_name(group_id: int) -> str:
    """Label a numbered group in the selector and in the corresponding figure."""
    return f"Grupo {group_id}"
