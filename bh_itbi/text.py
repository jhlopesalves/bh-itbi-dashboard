"""Portuguese user-facing copy, titles, notes and captions built from config constants."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bh_itbi import config as cfg
from bh_itbi.formatting import age_percent, composition_number, currency, number

# ---------- Shared vocabulary & labels ----------
TYPE_LABELS: dict[str, str] = {"apartment": "Apartamentos", "house": "Casas"}
ALL_TYPES_LABEL = "Apartamentos e casas"
ALL_NEIGHBOURHOODS_LABEL = "Toda a cidade"
UNKNOWN_NEIGHBOURHOOD_LABEL = "Bairro não informado"
CITY_NAME = "Belo Horizonte"
CITY_REFERENCE_EXTRA = "Referência municipal"

AGE_LABELS: dict[str, str] = {
    "new": "Até 2 anos / na planta",
    "3_10": "3 a 10 anos",
    "11_25": "11 a 25 anos",
    "26_plus": "26 anos ou mais",
}
DISTRIBUTION_LABELS: dict[str, str] = {
    "price_per_m2_brl_real": "Valor declarado real (R$/m²)",
    "price_per_m2_brl": "Valor declarado nominal (R$/m²)",
    "value_declared_brl": "Valor declarado nominal (R$)",
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

# ---------- Application, masthead & controls ----------
APP_TITLE = "Painel do Mercado Residencial de Belo Horizonte"
APP_UPDATE_TITLE = "Atualizando…"
APP_SUBTITLE = "Panorama analítico do mercado residencial a partir dos registros do ITBI."
SKIP_LINK_TEXT = "Ir para os gráficos"
MASTHEAD_EYEBROW = "BELO HORIZONTE / MG"
MASTHEAD_ABOUT_LINK = "Sobre os dados"
MASTHEAD_META_LABEL = "Base analítica dos registros"
MASTHEAD_PERIOD_DT = "Período"
MASTHEAD_PERIOD_DD = f"{cfg.START_YEAR}–{cfg.END_YEAR}"
MASTHEAD_ROWS_DT = "Registros na fonte"
MASTHEAD_REAL_DT = "Valores reais"
MASTHEAD_REAL_DD = f"IPCA, {cfg.IPCA_BASE}"

PROPERTY_TYPE_LABEL = "Tipo de imóvel"
PERIOD_LABEL = "Período"
NEIGHBOURHOODS_LABEL = "Bairros"
RESET_FILTERS_LABEL = "Restaurar filtros"
TABLIST_ARIA_LABEL = "Seções do painel"
FILTER_NOTE_ACTIVE = "Filtros aplicados ao panorama e aos diagnósticos."
FILTER_NOTE_MODELS = (
    f"Índices estimados sobre populações fixas de {cfg.START_YEAR}–{cfg.END_YEAR}; "
    "os filtros não se aplicam a esta seção."
)

# ---------- Empty states & chart axes ----------
EMPTY_SELECTION_MESSAGE = "Sem transações elegíveis neste recorte."
LOADING_MESSAGE = "Carregando dados…"
TEMPORAL_EMPTY_MESSAGE = (
    f"São necessárias {cfg.TEMPORAL_MINIMUM} transações por mês e tipo.<br>Amplie o recorte."
)
MAP_EMPTY_MESSAGE = "Sem registros com localização de face e área válida neste recorte."
DISTRIBUTION_EMPTY_MESSAGE = (
    f"São necessários ao menos {cfg.DISTRIBUTION_MINIMUM} valores válidos."
)
TAX_BASE_EMPTY_MESSAGE = (
    f"São necessárias {cfg.TAX_BASE_MINIMUM} transações com base válida"
    "<br>por trimestre e tipo."
)
HEAPING_EMPTY_MESSAGE = (
    f"Sem amostra suficiente na janela de {cfg.HEAPING_YEARS[0]}–{cfg.HEAPING_YEARS[1]}"
    f"<br>e de R$ {number(cfg.HEAPING_MIN_VALUE // 1000)} mil "
    f"a R$ {number(cfg.HEAPING_MAX_VALUE // 1_000_000)} milhão."
)
DISTANCE_EMPTY_MESSAGE = (
    f"São necessários {cfg.DISTANCE_MINIMUM} apartamentos por faixa de "
    f"{number(cfg.DISTANCE_BAND_WIDTH_KM)} km<br>e período, com localização de face."
)

REAL_PRICE_AXIS_TITLE = "R$/m² · IPCA"
MAP_COLORBAR_TITLE = "R$/m²<br>nominal"
LOG_CURRENCY_AXIS_TITLE = "R$ · escala logarítmica"
TRANSACTIONS_AXIS_TITLE = "Transações"
COMPARISON_AXIS_TITLE = f"R$/m², valores reais (IPCA {cfg.IPCA_BASE}) · escala log"
TAX_SHARE_AXIS_TITLE = "Parcela das transações"
NOMINAL_DECLARED_AXIS_TITLE = "Valor declarado nominal (R$)"
DISTANCE_AXIS_TITLE = "Distância em linha reta da Praça Sete (km)"
CLUSTER_INDEX_AXIS_TITLE = f"Índice · {cfg.START_YEAR} = 100"

# ---------- Overview tab ----------
OVERVIEW_EYEBROW = "RESUMO ESTATÍSTICO DO RECORTE"
KPI_COUNT_LABEL = "Transações elegíveis"
KPI_COUNT_UNIT = "registros no recorte ativo"
KPI_NOMINAL_LABEL = "Mediana nominal por m²"
KPI_NOMINAL_UNIT = "R$/m² · valor declarado"
KPI_REAL_LABEL = "Mediana real por m²"
KPI_REAL_UNIT = f"R$/m² · corrigida pelo IPCA de {cfg.IPCA_BASE}"
KPI_COVERAGE_LABEL = "Geolocalização por face"
KPI_COVERAGE_UNIT = "dos registros com centroide de face de quadra"

MAP_TITLE = "Distribuição espacial do valor declarado"
MAP_SUBTITLE = (
    "Cor: valor declarado nominal por m². Área do marcador: área construída. "
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

TRAJECTORIES_TITLE = "Trajetórias trimestrais por bairro"
TRAJECTORIES_SUBTITLE = (
    f"Medianas reais por trimestre, com referência municipal. Mínimo de "
    f"{cfg.NEIGHBOURHOOD_QUARTER_MINIMUM} transações por bairro e trimestre; "
    f"{cfg.TEMPORAL_MINIMUM} para a referência de BH."
)

# ---------- Diagnostics tab ----------
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

HEAPING_TITLE = "Concentração em valores redondos"
HEAPING_SUBTITLE = (
    f"Recorte ∩ {cfg.HEAPING_YEARS[0]}–{cfg.HEAPING_YEARS[1]} · "
    f"R$ {number(cfg.HEAPING_MIN_VALUE // 1000)} mil a "
    f"R$ {number(cfg.HEAPING_MAX_VALUE // 1_000_000)} milhão · "
    f"faixas centradas a cada R$ {number(cfg.HEAPING_BIN_WIDTH // 1000)} mil."
)
HEAPING_OTHER_BINS_LABEL = "Demais faixas"
HEAPING_ROUND_BINS_LABEL = (
    f"Perto de múltiplos de R$ {number(cfg.HEAPING_ROUND_MULTIPLE // 1000)} mil"
)
HEAPING_EMPTY_CAPTION = "Sem amostra suficiente para este diagnóstico no recorte ativo."

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
    f"ajustada nesta amostra. O IC {number(cfg.HEDONIC_CONFIDENCE_LEVEL * 100)}% usa erros "
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

DISTANCE_TITLE = "Valor real por distância à Praça Sete"
DISTANCE_SUBTITLE = (
    f"Apartamentos · valores reais · faixas de {number(cfg.DISTANCE_BAND_WIDTH_KM)} km, "
    f"até {cfg.DISTANCE_MAX_KM} km · mínimo de {cfg.DISTANCE_MINIMUM} por faixa e período."
)
DISTANCE_FOOTNOTE = (
    "Distância em linha reta a partir dos centroides de face, não tempo de deslocamento. "
    "Os períodos da legenda são intersectados com o filtro de anos."
)

# ---------- Models tab ----------
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
    f"Apartamentos e casas · escala log, 1º tri. {cfg.START_YEAR} = 100 · faixas: "
    "contribuição de cada característica observada para a diferença entre "
    "a média bruta e o índice (log × 100)."
)
HEDONIC_RAW_TRACE_NAME = "Média bruta"
HEDONIC_INDEX_TRACE_NAME = f"Índice hedônico · IC {number(cfg.HEDONIC_CONFIDENCE_LEVEL * 100)}%"

CLUSTERS_TITLE = "Agrupamento de trajetórias por similaridade"
CLUSTERS_MEMBERS_SUMMARY = "Composição de cada grupo"
CLUSTER_GROUP_LABEL = "Grupo de trajetórias"
CLUSTER_ALL_GROUPS_LABEL = "Todos os grupos"

# ---------- Methodology & footer ----------
METHODOLOGY_SUMMARY = "Dados, critérios e limites de interpretação"
METHODOLOGY_OBSERVED_HEADING = "O que é observado"
METHODOLOGY_OBSERVED_P1 = (
    "Valores declarados à autoridade tributária na data de pagamento do ITBI. "
    "A fonte de BH não distingue a natureza da transferência; "
    "os registros não podem ser tratados como vendas de mercado verificadas."
)
METHODOLOGY_OBSERVED_P2 = (
    "Apartamentos e casas sem sinalização em value_flag e com valor nominal "
    f"entre R$ {number(cfg.PRICE_PER_M2_MIN)} e R$ {number(cfg.PRICE_PER_M2_MAX)}/m², "
    "inclusive. As contagens do painel são de registros elegíveis, não de todo o ITBI. "
    "Medianas do resumo e distribuições exigem ao menos cinco observações."
)
METHODOLOGY_TIME_HEADING = "Tempo, moeda e dispersão"
METHODOLOGY_TIME_P1 = (
    f"Janela de exploração: {cfg.START_YEAR}–{cfg.END_YEAR}, como nas séries do notebook. "
    f"Valores reais vêm da própria fonte, corrigidos pelo IPCA para {cfg.IPCA_BASE}; "
    "não são recalculados no painel. Valores nominais de vários anos não descontam a inflação."
)
METHODOLOGY_TIME_P2 = (
    "Quartis usam interpolação linear do pandas. "
    "Períodos sem amostra suficiente permanecem como lacunas; "
    "P25–P75 não é um intervalo de confiança. "
    "O diagnóstico exige também área construída positiva."
)
METHODOLOGY_GEO_HEADING = "Geografia e proveniência"
_P_LOW = round(cfg.MAP_TRIM_QUANTILES[0] * 100)
_P_HIGH = round(cfg.MAP_TRIM_QUANTILES[1] * 100)
METHODOLOGY_GEO_P1 = (
    f"O mapa mostra até {number(cfg.MAP_SAMPLE_SIZE)} registros com área positiva "
    "e centroide de face, após restringir o valor nominal/m² "
    f"a P{_P_LOW}–P{_P_HIGH} do recorte. Centroides de CEP e bairro não "
    "entram no mapa. Não há deslocamento artificial dos pontos. "
    "Os resumos e as séries usam todos os registros elegíveis, "
    "independentemente da amostra desenhada."
)
METHODOLOGY_GEO_P2_PREFIX = (
    f"Fonte: Prefeitura de Belo Horizonte, dados abertos. Tratamento: {cfg.REPO_ID}. "
    "Licença dos dados de BH: CC-BY. Trabalho derivado e não oficial. "
)
METHODOLOGY_DICTIONARY_LINK = "Dicionário e limitações"
METHODOLOGY_VERSION_LINK = "Versão da fonte"
FOOTER_BRAND = "Mercado Residencial de Belo Horizonte"
FOOTER_PROVENANCE = (
    "Fonte: Prefeitura de Belo Horizonte, dados abertos. "
    f"Tratamento: {cfg.REPO_ID} (Hugging Face). Trabalho derivado e não oficial."
)
FOOTER_SOURCE_LINK = "Consultar a fonte"


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


def kpi_coverage_value(geocoded: int, total: int) -> str:
    """Format the face-geocoded percentage KPI or a dash when empty."""
    return f"{number(100 * geocoded / total, 1)}%" if total else "—"


def kpi_coverage_note(geocoded: int, total: int) -> str:
    """Format the geocoded record count subtitle."""
    return f"{number(geocoded)} de {number(total)} registros"


def map_caption(shown: int, screened: int) -> str:
    """Describe the trimmed and sampled point count drawn on the map."""
    return (
        f"{number(shown)} pontos de {number(screened)} "
        f"registros entre P{_P_LOW} e P{_P_HIGH}, após exigir localização de face "
        f"e área positiva. Amostra de até {number(cfg.MAP_SAMPLE_SIZE)} pontos; "
        "os indicadores usam todo o recorte elegível."
    )


def comparison_caption(
    comparison_names: Sequence[str], *, has_neighbourhood_filter: bool
) -> str:
    """Caption for the quarterly neighbourhood trajectories card."""
    names = ", ".join(name.title() for name in comparison_names)
    scope = (
        "Os bairros selecionados também filtram o mapa e o resumo. "
        if has_neighbourhood_filter
        else "Sem filtro de bairro, exibem-se cinco bairros de referência. "
    )
    return (
        f"Comparação: {names}. {scope}"
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
        note += " Sem seleção, exibem-se cinco bairros de referência."
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


def heaping_caption(total: int, share: float) -> str:
    """Footnote for the round-number heaping diagnostic card."""
    if total < cfg.HEAPING_MINIMUM:
        return HEAPING_EMPTY_CAPTION
    multiple_k = number(cfg.HEAPING_ROUND_MULTIPLE // 1000)
    return (
        f"{number(total)} registros nesta janela; {number(share * 100, 1)}% em faixas "
        f"centradas em múltiplos de R$ {multiple_k} mil. A faixa inclui valores próximos "
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
        ci_pct = number(cfg.HEDONIC_CONFIDENCE_LEVEL * 100)
        lines.extend(
            [
                f"Diferença ajustada: {age_percent(adjusted, 1)}",
                f"IC {ci_pct}%: {age_percent(lower, 1)} a {age_percent(upper, 1)}",
                "Contribuição (log × 100)",
                *(
                    f"{group}: {composition_number(val)}"
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
        "causal. A base 100 é uma normalização."
    )
    for group, value in final_contributions.items():
        if abs(value) < cfg.COMPOSITION_LABEL_THRESHOLD:
            note += (
                f" {group}: contribuição desprezível ({composition_number(value)}) "
                "no último trimestre."
            )
    if any(value > 0 for value in final_contributions.values()):
        note += (
            " Faixas acima do índice indicam características cuja mudança de composição "
            "elevou a média bruta."
        )
    return note


def clusters_subtitle(n_neighbourhoods: int) -> str:
    """Subtitle for the k-means neighbourhood trajectory clusters card."""
    return (
        f"Apartamentos · K-médias, quatro grupos · {number(n_neighbourhoods)} bairros "
        f"com ao menos {cfg.CLUSTER_YEAR_MINIMUM} registros em cada um dos dez anos · "
        f"{cfg.START_YEAR} = 100."
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
    return f"Grupo {group_id} · {count} bairros"
