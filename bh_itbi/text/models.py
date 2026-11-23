"""User-visible Portuguese copy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from bh_itbi import config as cfg
from bh_itbi.config import AuditEndpoint
from bh_itbi.formatting import (
    composition_number,
    number,
    quarter_label,
)
from bh_itbi.text.shared import (
    ALL_TYPES_LABEL,
    COMPOSITION_LABELS,
    TYPE_LABELS,
)

MODELS_UNAVAILABLE_BANNER = (
    "Os índices ainda não estão disponíveis nesta instalação. "
    "Consulte a preparação descrita no README."
)
MODELS_EYEBROW = f"POPULAÇÕES FIXAS · {cfg.START_YEAR}–{cfg.END_YEAR}"
MODELS_SECTION_TITLE = "Índice hedônico e padrões de trajetória"
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
SENSITIVITY_NOTE_EYEBROW = "SENSIBILIDADE"
PATTERNS_TITLE = "Padrões de trajetória por bairro"
PATTERN_LABELS = {
    "falling": "Queda e estabilização",
    "stable": "Estáveis",
    "rising": "Alta recente",
}
PATTERN_MEMBERS_SUMMARY = "Bairros deste padrão"
PATTERN_FIRM_LABEL = "Firmes"
PATTERN_BORDERLINE_LABEL = "De fronteira"
PATTERN_MEMBER_HOVER = (
    "<b>%{fullData.name}</b><br>%{x}: %{y:.1f}"
    "<br>No mesmo padrão em %{customdata:.0%} das reamostragens<extra></extra>"
)
PATTERN_CENTRE_HOVER = (
    "Centro do padrão<br>%{x}: %{y:.1f} (EP %{customdata:.1f})<extra></extra>"
)
AUDIT_LINK_TEXT = "Consultar a auditoria"
AUDIT_REPORT_URL = f"{cfg.REPOSITORY_URL}/blob/main/docs/robustness/report.md"
_PATTERN_SHARE_LABELS = {0.25: "um quarto", 1 / 3: "um terço", 0.50: "metade"}
_PATTERN_SHARE_TOLERANCE = 0.05


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


def sensitivity_note(endpoint: AuditEndpoint) -> str:
    """Format the year-scale Huber endpoint and its interval beside the published index."""
    quarter = quarter_label(pd.Period(endpoint["quarter"], freq="Q").start_time)
    return (
        f"Com estimador robusto (Huber, escala anual), o índice no "
        f"{quarter} é {number(endpoint['robust'], 1)} "
        f"(IC 95%: {number(endpoint['robust_lower'], 1)} a "
        f"{number(endpoint['robust_upper'], 1)}), contra "
        f"{number(endpoint['published'], 1)} no modelo publicado. A diferença está associada "
        "sobretudo a registros com valor declarado muito abaixo da avaliação municipal, "
        "mais frequentes em 2016–2019."
    )


def patterns_subtitle(n_neighbourhoods: int, period_minimum: int) -> str:
    """Describe the pattern population, adjustment, period and index base."""
    return (
        f"{TYPE_LABELS['apartment']} · valor real por m² ajustado por área e idade do imóvel · "
        f"medianas por biênio · {number(n_neighbourhoods)} bairros com ao menos "
        f"{number(period_minimum)} registros em cada biênio · "
        f"{cfg.INDEX_BASE} = média do próprio bairro em {cfg.START_YEAR}–{cfg.END_YEAR}."
    )


def pattern_counts(size: int, firm: int) -> str:
    """State the displayed pattern's total, firm and borderline counts."""
    return (
        f"{number(size)} bairros · {number(firm)} firmes · {number(size - firm)} de fronteira"
    )


def patterns_footnote(
    draws: int,
    firm_share: float,
    centre_se: tuple[float, float],
    ari_median: float,
    borderline_share: float,
) -> str:
    """Describe the grouping and its stability from the prepared metadata."""
    nearest = min(_PATTERN_SHARE_LABELS, key=lambda fraction: abs(fraction - borderline_share))
    share = (
        _PATTERN_SHARE_LABELS[nearest]
        if abs(nearest - borderline_share) <= _PATTERN_SHARE_TOLERANCE
        else f"{number(100 * borderline_share)}%"
    )
    largest, rising = centre_se
    return (
        "Agrupamento por k-médias em três padrões, aplicado à forma das trajetórias "
        "(cada bairro centrado na própria média). Linha forte: centro do padrão; linhas finas: "
        f"bairros que ficam no mesmo padrão em pelo menos {number(100 * firm_share)}% de "
        f"{number(draws)} reamostragens; tracejado cinza: bairros de fronteira. "
        "Os centros dos padrões são estáveis "
        f"(erro-padrão de até {number(largest, 1)} ponto nos dois maiores padrões e de "
        f"{number(rising, 1)} no de alta recente), mas a classificação completa não é: "
        f"a concordância mediana entre reamostragens é {number(ari_median, 2)}, "
        f"porque cerca de {share} dos bairros fica entre padrões. "
        "O ajuste considera apenas área e faixa de idade; outras diferenças de composição "
        "permanecem. A classificação anterior, em quatro grupos e sem ajuste, "
        "foi substituída após a auditoria de robustez."
    )
