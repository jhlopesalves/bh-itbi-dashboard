"""Geometry and Portuguese display values for the age-premium chart."""

from collections.abc import Mapping
from typing import TypedDict

import numpy as np

from bh_itbi.age import AGE_GROUPS, AGE_MINIMUM, AGE_REFERENCE, AGE_YEARS, AgePremiums
from bh_itbi.analysis import AGE_LABELS, Filters
from bh_itbi.figures import (
    COMPOSITION_HUES,
    TEAL,
    composition_number,
    composition_tint,
    currency,
    number,
)

QUARTER_VISIBILITY = 0.005
AGE_FILLS = {
    group: composition_tint(hue, strength=0.75)
    for group, hue in {
        "Bairro": COMPOSITION_HUES["Bairro"],
        "Área": COMPOSITION_HUES["Área"],
        "Trimestre": "#8a929a",
    }.items()
}
AGE_METHOD = (
    "Regressão do log do valor real/m² com faixa de idade, log da área, bairro e trimestre, "
    "ajustada nesta amostra. O IC 95% usa erros agrupados por bairro. "
    "A diferença observada é entre médias geométricas. A decomposição é uma identidade "
    "contábil do modelo ajustado. Características não observadas (padrão construtivo, "
    "lazer, conservação) não estão controladas. A diferença ajustada não é uma "
    "estimativa causal."
)
AGE_ELIGIBILITY_NOTE = (
    "A fonte reúne imóveis na planta e prontos na faixa «Até 2 anos / na planta». "
    "A triagem do índice hedônico mantém registros sem marcação de valor, com valor "
    "nominal de R$ 100 a R$ 200.000/m², área construída positiva e dados completos "
    "para o modelo. Não há corte por percentil."
)


class AgeSegment(TypedDict):
    group: str
    start: float
    end: float
    subtracts: bool
    hidden: bool


class AgeChartRow(TypedDict):
    label: str
    reference: bool
    observed: float
    observed_label: str
    adjusted_label: str
    segments: list[AgeSegment]
    interval: tuple[float, float] | None
    tooltip: list[str]


class AgeChart(TypedDict):
    rows: list[AgeChartRow]
    fills: dict[str, str]
    teal: str
    empty: str


def age_segments(
    adjusted: float, contributions: Mapping[str, float], observed: float
) -> list[AgeSegment]:
    """Stack additions then subtractions. Retain the endpoints of hidden terms."""
    segments: list[AgeSegment] = [
        {
            "group": "Ajustado",
            "start": 0.0,
            "end": adjusted,
            "subtracts": False,
            "hidden": False,
        }
    ]
    ordered = sorted(contributions.items(), key=lambda item: (item[1] < 0, -abs(item[1])))
    end = adjusted
    for group, value in ordered:
        if value == 0:
            continue
        start, end = end, end + value
        segments.append(
            {
                "group": group,
                "start": start,
                "end": end,
                "subtracts": value < 0,
                "hidden": group == "Trimestre" and abs(value) < QUARTER_VISIBILITY,
            }
        )
    # The estimator checks the identity independently. Snap only the residual
    # floating-point error so the final endpoint and marker share a coordinate.
    segments[-1]["end"] = observed
    return segments


def age_percent(points: float, decimals: int = 0) -> str:
    """Display a log difference as a signed relative change in geometric means."""
    percent = float(np.expm1(points) * 100)
    sign = ""
    if round(percent, decimals):
        sign = "−" if percent < 0 else "+"
    return f"{sign}{number(abs(percent), decimals)}%"


def age_chart_data(result: AgePremiums) -> AgeChart:
    """Keep axis coordinates in log points and send preformatted tooltip strings."""
    rows: list[AgeChartRow] = []
    visible = set()
    for key, row in result.table.iterrows():
        label = AGE_LABELS[str(key)]
        observed = float(row["observed"])
        reference = key == AGE_REFERENCE
        observed_percent = age_percent(observed)
        tooltip = [
            label,
            f"Transações: {number(row['n'])}",
            f"Média geométrica observada: {currency(row['geometric_mean'])}/m²",
            f"Diferença observada: {age_percent(observed, 1)}",
        ]
        adjusted_label = ""
        segments = []
        interval = None
        if not reference and "adjusted" in row:
            adjusted = float(row["adjusted"])
            adjusted_percent = age_percent(adjusted)
            contributions = {group: float(row[group]) for group in AGE_GROUPS}
            segments = age_segments(adjusted, contributions, observed)
            visible.update(segment["group"] for segment in segments if not segment["hidden"])
            lower, upper = float(row["lower"]), float(row["upper"])
            interval = (lower, upper)
            adjusted_label = f"ajustado {adjusted_percent}"
            tooltip.extend(
                [
                    f"Diferença ajustada: {age_percent(adjusted, 1)}",
                    f"IC 95%: {age_percent(lower, 1)} a {age_percent(upper, 1)}",
                    "Contribuição (log × 100)",
                    *(
                        f"{group}: {composition_number(v)}"
                        for group, v in contributions.items()
                    ),
                ]
            )
        rows.append(
            {
                "label": label,
                "reference": reference,
                "observed": observed,
                "observed_label": "referência"
                if reference
                else f"observado {observed_percent}",
                "adjusted_label": adjusted_label,
                "segments": segments,
                "interval": interval,
                "tooltip": tooltip,
            }
        )
    return {
        "rows": rows,
        "fills": {group: fill for group, fill in AGE_FILLS.items() if group in visible},
        "teal": TEAL,
        "empty": result.unavailable or "Sem apartamentos elegíveis no recorte de 2023–2025.",
    }


def age_subtitle(filters: Filters, *, adjusted: bool) -> str:
    """Describe the intersection with the fixed apartment cohort in plain words."""
    if filters.property_type == "house":
        return "O tipo de imóvel selecionado não inclui apartamentos."
    start, end = max(filters.start_year, AGE_YEARS[0]), min(filters.end_year, AGE_YEARS[1])
    if start > end:
        return "Apartamentos · janela de 2023–2025 fora do período selecionado."
    population = (
        "Apartamentos nos bairros selecionados" if filters.neighbourhoods else "Apartamentos"
    )
    period = str(start) if start == end else f"{start}–{end}"
    subtitle = f"{population}, {period} · diferença em relação a imóveis com 26 anos ou mais."
    if adjusted:
        subtitle += (
            " Teal: diferença ajustada por bairro, área e trimestre. "
            "Segmentos: quanto a composição acrescenta até a diferença observada."
        )
    return subtitle


def age_note(result: AgePremiums) -> str:
    """Explain the adjustment and add any selection-specific qualifications."""
    if "adjusted" in result.table:
        sentences = [AGE_METHOD]
        for key, value in result.table["Trimestre"].items():
            if key != AGE_REFERENCE and abs(value) < QUARTER_VISIBILITY:
                sentences.append(
                    f"Trimestre: contribuição desprezível ({composition_number(value)}) "
                    f"na faixa {AGE_LABELS[str(key)]}."
                )
    else:
        sentences = ["A diferença observada é entre médias geométricas."]
        if result.unavailable:
            sentences.insert(0, result.unavailable)
    if result.excluded:
        suppressed = ", ".join(
            f"{AGE_LABELS[key]} (n = {number(n)})" for key, n in result.excluded.items()
        )
        sentences.append(
            f"Faixas excluídas por terem menos de {AGE_MINIMUM} transações: {suppressed}."
        )
    return " ".join([*sentences, AGE_ELIGIBILITY_NOTE])
