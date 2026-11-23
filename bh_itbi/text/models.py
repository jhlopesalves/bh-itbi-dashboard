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

TRAJECTORY_INDEX_AXIS_TITLE = f"Índice · {cfg.START_YEAR} = {cfg.INDEX_BASE}"
MODELS_UNAVAILABLE_BANNER = (
    "Os índices ainda não estão disponíveis nesta instalação. "
    "Consulte a preparação descrita no README."
)
MODELS_EYEBROW = f"POPULAÇÕES FIXAS · {cfg.START_YEAR}–{cfg.END_YEAR}"
MODELS_SECTION_TITLE = "Índice hedônico e trajetórias por bairro"
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
TRAJECTORIES_MODEL_TITLE = "Trajetórias anuais por bairro"
TRAJECTORIES_NEIGHBOURHOODS_LABEL = "Bairros"
TRAJECTORIES_MEDIAN_LABEL = "Mediana entre os bairros"
TRAJECTORIES_AUDIT_LINK_TEXT = "Consultar a auditoria"
TRAJECTORIES_FOOTNOTE = (
    "Linhas finas: bairros; linha escura: mediana entre os bairros em cada ano. "
    "As medianas não são ajustadas pela composição das transações: a entrada de imóveis "
    "novos ou vendidos na planta pode elevar a mediana de um bairro sem que os imóveis "
    "existentes se valorizem. A base em 2016 transfere a incerteza amostral desse ano para "
    "toda a trajetória. A classificação dos bairros em quatro grupos foi retirada do painel "
    "por não se manter estável na auditoria de robustez."
)
TRAJECTORY_HOVER = (
    "<b>%{customdata[0]}</b><br>%{x}<br>Índice: %{y:.1f}"
    "<br>Transações: %{customdata[1]:,.0f}" + TRACE_NAME_EXTRA
)
TRAJECTORY_MEDIAN_HOVER = "%{x}<br>Mediana entre os bairros: %{y:.1f}" + TRACE_NAME_EXTRA


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


def trajectories_subtitle(n_neighbourhoods: int) -> str:
    """Describe the coverage, statistic and index base of the trajectories."""
    return (
        f"{TYPE_LABELS['apartment']} · medianas anuais observadas · "
        f"{number(n_neighbourhoods)} bairros com ao menos {cfg.CLUSTER_YEAR_MINIMUM} "
        f"registros em cada um dos {number_word(len(cfg.YEARS))} anos · "
        f"{cfg.START_YEAR} = {cfg.INDEX_BASE}."
    )
