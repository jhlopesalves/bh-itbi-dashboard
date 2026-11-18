"""User-visible Portuguese copy."""

from __future__ import annotations

from collections.abc import Mapping

from bh_itbi import config as cfg
from bh_itbi.formatting import (
    age_percent,
    composition_number,
    currency,
    number,
    scaled_currency,
)
from bh_itbi.text.shared import (
    AGE_LABELS,
    COMPOSITION_LABELS,
    TRACE_NAME_EXTRA,
    TRANSACTIONS_HOVER,
    period_text,
)

TAX_BASE_EMPTY_MESSAGE = (
    f"São necessárias {cfg.TAX_BASE_MINIMUM} transações com base válida"
    "<br>por trimestre e tipo."
)
HEAPING_EMPTY_MESSAGE = (
    f"Sem amostra suficiente na janela de {cfg.HEAPING_YEARS[0]}–{cfg.HEAPING_YEARS[1]}"
    f"<br>e de {scaled_currency(cfg.HEAPING_MIN_VALUE)} "
    f"a {scaled_currency(cfg.HEAPING_MAX_VALUE)}."
)
DISTANCE_EMPTY_MESSAGE = (
    f"São necessários {cfg.DISTANCE_MINIMUM} apartamentos por faixa de "
    f"{number(cfg.DISTANCE_BAND_WIDTH_KM)} km<br>e período, com localização de face."
)
TAX_SHARE_AXIS_TITLE = "Parcela das transações"
NOMINAL_DECLARED_AXIS_TITLE = "Valor declarado nominal (R$)"
DISTANCE_AXIS_TITLE = "Distância em linha reta da Praça Sete (km)"
DIAGNOSTICS_EYEBROW = "DIAGNÓSTICOS DOS REGISTROS"
DIAGNOSTICS_DESCRIPTION = (
    "Os filtros compartilhados aplicam-se a esta seção. "
    "Cada análise declara sua janela temporal e sua amostra."
)
TAX_TITLE = "Valor declarado frente à base de cálculo"
TAX_SUBTITLE = (
    "Parcela trimestral de transações com valor declarado inferior "
    "à base de cálculo do ITBI. Base positiva; "
    f"mínimo de {cfg.TAX_BASE_MINIMUM} por trimestre e tipo."
)
TAX_FOOTNOTE = (
    "A divergência entre valor declarado e base tributária é descritiva; "
    "não demonstra subdeclaração ou evasão."
)
TAX_HOVER = (
    "%{customdata[0]}<br>Abaixo da base: %{y:.1%}" + TRANSACTIONS_HOVER + TRACE_NAME_EXTRA
)
HEAPING_TITLE = "Concentração em valores redondos"
HEAPING_SUBTITLE = (
    f"Recorte ∩ {cfg.HEAPING_YEARS[0]}–{cfg.HEAPING_YEARS[1]} · "
    f"{scaled_currency(cfg.HEAPING_MIN_VALUE)} a {scaled_currency(cfg.HEAPING_MAX_VALUE)} · "
    f"faixas centradas a cada {scaled_currency(cfg.HEAPING_BIN_WIDTH)}."
)
HEAPING_OTHER_BINS_LABEL = "Demais faixas"
HEAPING_ROUND_BINS_LABEL = (
    f"Perto de múltiplos de {scaled_currency(cfg.HEAPING_ROUND_MULTIPLE)}"
)
HEAPING_EMPTY_CAPTION = "Sem amostra suficiente para este diagnóstico no recorte ativo."
HEAPING_HOVER = "Faixa centrada em R$ %{x:,.0f}<br>Transações: %{y:,.0f}<extra></extra>"
AGE_TITLE = "Valor real por idade da construção"
FEW_NEIGHBOURHOODS = (
    f"Ajuste indisponível: a seleção tem menos de {cfg.AGE_MIN_NEIGHBOURHOODS} bairros."
)
UNIDENTIFIED_ADJUSTMENT = "Ajuste indisponível: a seleção não identifica todos os efeitos."
MISSING_REFERENCE = (
    f"São necessárias {cfg.AGE_MINIMUM} transações na faixa de referência "
    f"({AGE_LABELS[cfg.AGE_REFERENCE].lower()})."
)
AGE_EMPTY_MESSAGE = (
    f"Sem apartamentos elegíveis no recorte de {cfg.AGE_YEARS[0]}–{cfg.AGE_YEARS[1]}."
)
AGE_METHOD = (
    "Regressão do log do valor real/m² com faixa de idade, log da área, bairro e trimestre, "
    f"ajustada nesta amostra. O IC {number(cfg.AGE_CONFIDENCE_LEVEL * 100)}% usa erros "
    "agrupados por bairro. A diferença observada é entre médias geométricas. "
    "A decomposição é uma identidade contábil do modelo ajustado. "
    "Características não observadas (padrão construtivo, lazer, conservação) "
    "não estão controladas. A diferença ajustada não é uma estimativa causal."
)
AGE_ELIGIBILITY_NOTE = (
    f"A fonte reúne imóveis na planta e prontos na faixa «{AGE_LABELS['new']}». "
    "A triagem do índice hedônico mantém registros sem marcação de valor, com valor "
    f"nominal de R$ {number(cfg.PRICE_PER_M2_MIN)} a R$ {number(cfg.PRICE_PER_M2_MAX)}/m², "
    "área construída positiva e dados completos para o modelo. Não há corte por percentil."
)
AGE_OBSERVED_ONLY_NOTE = "A diferença observada é entre médias geométricas."
AGE_REFERENCE_LABEL = "referência"
AGE_ADJUSTED_LABEL = "ajustado"
DISTANCE_TITLE = "Valor real por distância à Praça Sete"
DISTANCE_SUBTITLE = (
    f"Apartamentos · valores reais · faixas de {number(cfg.DISTANCE_BAND_WIDTH_KM)} km, "
    f"até {cfg.DISTANCE_MAX_KM} km · mínimo de {cfg.DISTANCE_MINIMUM} por faixa e período."
)
DISTANCE_FOOTNOTE = (
    "Distância em linha reta a partir dos centroides de face, não tempo de deslocamento. "
    "Os períodos da legenda são intersectados com o filtro de anos."
)
DISTANCE_HOVER = (
    "%{customdata[0]}–%{customdata[1]} km<br>Mediana: R$ %{y:,.0f}/m²"
    "<br>Transações: %{customdata[2]}<br>%{meta}<extra></extra>"
)


def heaping_caption(total: int, share: float) -> str:
    """Footnote for the round-number heaping diagnostic card."""
    if total < cfg.HEAPING_MINIMUM:
        return HEAPING_EMPTY_CAPTION
    multiple = scaled_currency(cfg.HEAPING_ROUND_MULTIPLE)
    return (
        f"{number(total)} registros nesta janela; {number(share * 100, 1)}% em faixas "
        f"centradas em múltiplos de {multiple}. A faixa inclui valores próximos "
        "ao múltiplo; não é a proporção de valores exatamente redondos."
    )


def age_row_tooltip(
    label: str,
    count: float,
    geometric_mean: float,
    observed: float,
    adjusted_details: tuple[float, float, float, Mapping[str, float]] | None = None,
) -> list[str]:
    """Build preformatted tooltip lines for one building-age band row."""
    lines = [
        label,
        f"Transações: {number(count)}",
        f"Média geométrica observada: {currency(geometric_mean)}/m²",
        f"Diferença observada: {age_percent(observed, 1)}",
    ]
    if adjusted_details is not None:
        adjusted, lower, upper, contributions = adjusted_details
        ci_pct = number(cfg.AGE_CONFIDENCE_LEVEL * 100)
        lines.extend(
            [
                f"Diferença ajustada: {age_percent(adjusted, 1)}",
                f"IC {ci_pct}%: {age_percent(lower, 1)} a {age_percent(upper, 1)}",
                "Contribuição (log × 100)",
                *(
                    f"{COMPOSITION_LABELS[group]}: {composition_number(val)}"
                    for group, val in contributions.items()
                ),
            ]
        )
    return lines


def age_subtitle(
    property_type: str,
    start_year: int,
    end_year: int,
    *,
    has_neighbourhoods: bool,
    adjusted: bool,
) -> str:
    """Describe the intersection with the fixed apartment cohort in plain words."""
    if property_type == "house":
        return "O tipo de imóvel selecionado não inclui apartamentos."
    start, end = max(start_year, cfg.AGE_YEARS[0]), min(end_year, cfg.AGE_YEARS[1])
    if start > end:
        return (
            f"Apartamentos · janela de {cfg.AGE_YEARS[0]}–{cfg.AGE_YEARS[1]} "
            "fora do período selecionado."
        )
    population = (
        "Apartamentos nos bairros selecionados" if has_neighbourhoods else "Apartamentos"
    )
    ref = AGE_LABELS[cfg.AGE_REFERENCE].lower()
    subtitle = (
        f"{population}, {period_text(start, end)} · diferença em relação a imóveis com {ref}."
    )
    if adjusted:
        subtitle += (
            " Teal: diferença ajustada por bairro, área e trimestre. "
            "Segmentos: quanto a composição acrescenta até a diferença observada."
        )
    return subtitle


def age_note(
    *,
    adjusted: bool,
    quarter_values: Mapping[str, float],
    unavailable: str | None,
    excluded: Mapping[str, int],
) -> str:
    """Explain the age adjustment and add any selection-specific qualifications."""
    if adjusted:
        sentences = [AGE_METHOD]
        for key, value in quarter_values.items():
            if key != cfg.AGE_REFERENCE and abs(value) < cfg.QUARTER_VISIBILITY:
                sentences.append(
                    f"Trimestre: contribuição desprezível ({composition_number(value)}) "
                    f"na faixa {AGE_LABELS[str(key)]}."
                )
    else:
        sentences = [AGE_OBSERVED_ONLY_NOTE]
        if unavailable:
            sentences.insert(0, unavailable)
    if excluded:
        suppressed = ", ".join(
            f"{AGE_LABELS[key]} (n = {number(n)})" for key, n in excluded.items()
        )
        sentences.append(
            f"Faixas excluídas por terem menos de {cfg.AGE_MINIMUM} transações: {suppressed}."
        )
    return " ".join([*sentences, AGE_ELIGIBILITY_NOTE])
