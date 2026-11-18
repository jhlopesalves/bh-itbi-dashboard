"""Portuguese editorial layout; analytical content is supplied by callbacks."""

from dash import dcc, html

from bh_itbi.data import IPCA_BASE, REPO_ID, REVISION, YEARS
from bh_itbi.figures import (
    CLUSTER_COLORS,
    COMPOSITION_LABEL_THRESHOLD,
    DISTRIBUTION_LABELS,
    TEAL,
    composition_number,
    empty_figure,
    number,
)
from bh_itbi.models import COMPOSITION_TERMS
from bh_itbi.urls import DEFAULT_MAP_STYLE, DEFAULT_METRIC, QUERY_OPTIONS, default_controls

COMPARISON_SUBTITLE = (
    "Distribuição do preço por m² em cada bairro. Faixa escura: P25–P75; "
    "linha clara: mediana. Escala de densidade comum a todos os bairros."
)
COMPARISON_INTERVAL_SUBTITLE = "Ponto: mediana. Faixa escura: P25–P75. Faixa clara: P10–P90."

GRAPH_CONFIG = {
    "displaylogo": False,
    "locale": "pt-BR",
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "sendChartToCloud"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "mercado-residencial-bh"},
}
DROPDOWN_LABELS = {
    "select_all": "Selecionar todos",
    "deselect_all": "Limpar todos",
    "selected_count": "selecionados",
    "search": "Pesquisar",
    "clear_search": "Limpar pesquisa",
    "clear_selection": "Limpar seleção",
    "no_options_found": "Nenhum resultado",
}


def dropdown(identifier: str, **kwargs):
    return dcc.Dropdown(
        id=identifier, className="control-dropdown", labels=DROPDOWN_LABELS, **kwargs
    )


def graph(identifier: str, *, height=360, map_view=False):
    """Give Plotly an explicit frame to avoid percentage-height cycles in a grid."""
    config = GRAPH_CONFIG | ({"scrollZoom": True} if map_view else {})
    return dcc.Graph(
        id=identifier,
        figure=empty_figure("Carregando dados…", height),
        config=config,
        responsive=True,
        className="plot",
        style={"height": height, "width": "100%"},
    )


def card(title, subtitle, body, *, class_name="", extra=None):
    """Keep the body flat: Dash does not resolve nested lists of components."""
    return html.Section(
        [
            html.Div(
                [
                    html.Div([html.H2(title), html.P(subtitle, className="chart-subtitle")]),
                    extra,
                ],
                className="card-heading",
            ),
            *(body if isinstance(body, list) else [body]),
        ],
        className=f"chart-card {class_name}",
    )


def metric(label, identifier, unit, note=None):
    return html.Div(
        [
            html.P(label, className="metric-label"),
            html.Div("—", id=identifier, className="metric-value"),
            html.P(unit, className="metric-unit"),
            html.P(note, className="metric-note") if note else None,
        ],
        className="metric",
    )


def overview_panel():
    return html.Div(
        [
            html.Div(
                [
                    html.P("RESUMO ESTATÍSTICO DO RECORTE", className="eyebrow"),
                    html.P(
                        id="scope-label",
                        className="scope-label",
                        role="status",
                        **{"aria-live": "polite"},
                    ),
                ],
                className="section-line",
            ),
            html.Div(
                [
                    metric("Transações elegíveis", "kpi-count", "registros no recorte ativo"),
                    metric("Mediana nominal por m²", "kpi-nominal", "R$/m² · valor declarado"),
                    metric(
                        "Mediana real por m²",
                        "kpi-real",
                        f"R$/m² · corrigida pelo IPCA de {IPCA_BASE}",
                    ),
                    html.Div(
                        [
                            html.P("Geolocalização por face", className="metric-label"),
                            html.Div("—", id="kpi-coverage", className="metric-value"),
                            html.P(
                                "dos registros com centroide de face de quadra",
                                className="metric-unit",
                            ),
                            html.P(id="kpi-coverage-note", className="metric-note"),
                        ],
                        className="metric",
                    ),
                ],
                className="metrics",
            ),
            html.Div(
                [
                    card(
                        "Distribuição espacial do valor declarado",
                        "Cor: valor declarado nominal por m². Área do marcador: área "
                        "construída. Um clique filtra pelo bairro informado no registro.",
                        [
                            graph("geo-map", height=540, map_view=True),
                            html.P(id="map-caption", className="card-footnote", role="status"),
                        ],
                        class_name="map-card",
                        extra=html.Div(
                            [
                                html.Label(
                                    "Fundo do mapa", htmlFor="map-style", className="sr-only"
                                ),
                                dropdown(
                                    "map-style",
                                    options=[
                                        {"label": "Com ruas", "value": "carto-voyager"},
                                        {"label": "Sem fundo", "value": "white-bg"},
                                    ],
                                    value=DEFAULT_MAP_STYLE,
                                    clearable=False,
                                    searchable=False,
                                ),
                            ],
                            className="map-style-field",
                        ),
                    ),
                    card(
                        "Distribuição dos valores",
                        "Todas as observações válidas, sem truncamento das caudas.",
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Medida da distribuição",
                                        htmlFor="distribution-metric",
                                        className="sr-only",
                                    ),
                                    dropdown(
                                        "distribution-metric",
                                        options=[
                                            {"label": label, "value": key}
                                            for key, label in DISTRIBUTION_LABELS.items()
                                        ],
                                        value=DEFAULT_METRIC,
                                        clearable=False,
                                        searchable=False,
                                    ),
                                ],
                                className="distribution-control",
                            ),
                            graph("distribution-figure", height=330),
                            html.Div(
                                id="distribution-summary", className="distribution-summary"
                            ),
                            html.P(
                                "Eixo logarítmico; os valores extremos são preservados. "
                                "Linhas pontilhadas: mediana por tipo (mínimo de 5 "
                                "observações). As barras contam transações em faixas "
                                "de largura crescente.",
                                className="card-footnote",
                            ),
                            html.Div(
                                [
                                    html.P("LOCALIZAÇÃO GENERALIZADA", className="eyebrow"),
                                    html.P(
                                        "Os pontos são centroides de face de quadra, "
                                        "não localizações exatas dos imóveis. Ao clicar, "
                                        "o filtro usa o bairro informado no registro, "
                                        "sem inferir seus limites a partir das coordenadas."
                                    ),
                                ],
                                className="geography-note",
                            ),
                        ],
                        class_name="distribution-card",
                    ),
                ],
                className="spatial-grid",
            ),
            html.Div(
                [
                    card(
                        "Evolução mensal do valor real",
                        "Mediana e intervalo interquartil (P25–P75), corrigidos pelo IPCA. "
                        "Mínimo de 30 transações por mês e tipo.",
                        [
                            graph("trend-figure"),
                            html.P(
                                "A faixa representa a dispersão entre transações, não um "
                                "intervalo de confiança. Com recorte geográfico, a linha "
                                "pontilhada mantém a referência municipal do mesmo tipo "
                                "e período.",
                                className="card-footnote",
                            ),
                        ],
                    ),
                    card(
                        "Comparação entre bairros",
                        html.Span(COMPARISON_SUBTITLE, id="comparison-subtitle"),
                        [
                            dcc.Store(id="comparison-data"),
                            html.Div(
                                html.Div(id="comparison-plot"),
                                className="comparison-scroll",
                            ),
                            html.P(id="comparison-note", className="card-footnote"),
                        ],
                    ),
                ],
                className="analysis-grid",
            ),
            card(
                "Trajetórias trimestrais por bairro",
                "Medianas reais por trimestre, com referência municipal. Mínimo de 15 "
                "transações por bairro e trimestre; 30 para a referência de BH.",
                [
                    graph("neighbourhood-figure", height=370),
                    html.P(id="neighbourhood-caption", className="card-footnote"),
                ],
            ),
        ],
        id="overview-panel",
        className="view-panel",
    )


def diagnostics_panel():
    return html.Div(
        [
            html.Div(
                [
                    html.P("DIAGNÓSTICOS DOS REGISTROS", className="eyebrow"),
                    html.P(
                        "Os filtros compartilhados aplicam-se a esta seção. "
                        "Cada análise declara sua janela temporal e sua amostra.",
                        className="section-description",
                    ),
                ],
                className="section-intro",
            ),
            html.P(id="diagnostic-scope", className="scope-banner", role="status"),
            html.Div(
                [
                    card(
                        "Valor declarado frente à base de cálculo",
                        "Parcela trimestral de transações com valor declarado inferior "
                        "à base de cálculo do ITBI. Base positiva; mínimo de 100 por "
                        "trimestre e tipo.",
                        [
                            graph("tax-figure"),
                            html.P(
                                "A divergência entre valor declarado e base "
                                "tributária é descritiva; "
                                "não demonstra subdeclaração ou evasão.",
                                className="card-footnote",
                            ),
                        ],
                    ),
                    card(
                        "Concentração em valores redondos",
                        "Recorte ∩ 2023–2025 · R$ 50 mil a R$ 1 milhão · faixas "
                        "centradas a "
                        "cada R$ 5 mil.",
                        [
                            graph("heaping-figure"),
                            html.P(id="heaping-caption", className="card-footnote"),
                        ],
                    ),
                    card(
                        "Valor real por idade da construção",
                        "Apartamentos · recorte ∩ 2023–2025 · mediana e P25–P75, "
                        "após excluir "
                        "valores acima do P99 do recorte.",
                        [
                            graph("age-figure"),
                            html.P(
                                "Até 2 anos inclui imóveis na planta. Mínimo de "
                                "15 por faixa após o "
                                "corte. São diferenças observadas, sem controle "
                                "por localização ou "
                                "área.",
                                className="card-footnote",
                            ),
                        ],
                    ),
                    card(
                        "Valor real por distância à Praça Sete",
                        "Apartamentos · valores reais · faixas de 1 km, até 14 km"
                        " · mínimo de "
                        "50 por faixa e período.",
                        [
                            graph("distance-figure"),
                            html.P(
                                "Distância em linha reta a partir dos centroides "
                                "de face, não tempo de "
                                "deslocamento. Os períodos da legenda são "
                                "intersectados com o filtro de"
                                " anos.",
                                className="card-footnote",
                            ),
                        ],
                    ),
                ],
                className="diagnostics-grid",
            ),
        ],
        id="diagnostics-panel",
        className="view-panel is-hidden",
    )


def hedonic_note(final_contributions: dict[str, float]) -> str:
    """Explain the estimand and include groups without direct labels."""
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
        if abs(value) < COMPOSITION_LABEL_THRESHOLD:
            note += f" {group}: contribuição desprezível ({composition_number(value)}) no"
            note += " último trimestre."
    if any(value > 0 for value in final_contributions.values()):
        note += (
            " Faixas acima do índice indicam características cuja mudança de composição "
            "elevou a média bruta."
        )
    return note


def models_panel(models):
    if models is None:
        content = html.P(
            "Os índices ainda não estão disponíveis nesta instalação. Consulte a "
            "preparação descrita no README.",
            className="scope-banner",
        )
    else:
        metadata = models["metadata"]
        hedonic = metadata["hedonic"]
        clusters = metadata["clusters"]
        final = models["hedonic"].iloc[-1]
        content = [
            html.Div(
                [
                    html.P("POPULAÇÕES FIXAS · 2016–2025", className="eyebrow"),
                    html.H2(
                        "Índice hedônico e agrupamento de trajetórias",
                        className="section-title",
                    ),
                    html.P(
                        "Estimativas sobre a amostra fixa descrita em cada análise. Os "
                        "filtros do panorama não alteram estes resultados.",
                        className="section-description",
                    ),
                ],
                className="section-intro",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(number(hedonic["n"])),
                            html.Span("observações no modelo hedônico"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong(number(hedonic["neighbourhoods"])),
                            html.Span("bairros com ao menos 100 registros"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong(number(hedonic["r_squared"], 3)),
                            html.Span("R² · log do valor declarado real por m²"),
                        ]
                    ),
                ],
                className="model-metrics",
            ),
            card(
                "Preço ajustado, média bruta e o que separa as duas",
                "Apartamentos e casas · escala log, 1º tri. 2016 = 100 · faixas: "
                "contribuição de cada característica observada para a diferença entre "
                "a média bruta e o índice (log × 100).",
                [
                    graph("hedonic-figure", height=420),
                    html.P(
                        hedonic_note({group: final[group] for group in COMPOSITION_TERMS}),
                        className="card-footnote",
                    ),
                ],
            ),
            card(
                "Agrupamento de trajetórias por similaridade",
                f"Apartamentos · K-médias, quatro grupos · "
                f"{number(clusters['n_neighbourhoods'])} bairros com ao menos 30 registros "
                "em cada um dos dez anos · 2016 = 100.",
                [
                    graph("clusters-figure", height=410),
                    html.P(
                        "Linhas finas: bairros; linhas fortes: centros dos grupos. "
                        "O número de grupos é uma escolha analítica, não um ótimo estimado. "
                        f"Silhueta: {number(clusters['silhouettes']['4'], 2)}; "
                        "há sobreposição entre trajetórias. Os grupos descrevem "
                        "a forma da evolução, não o nível de preços "
                        "ou regiões administrativas.",
                        className="card-footnote",
                    ),
                    html.Details(
                        [
                            html.Summary("Composição de cada grupo"),
                            html.Div(id="cluster-members", className="members-list"),
                        ],
                        className="members-details",
                    ),
                ],
                extra=html.Div(
                    [
                        html.Label(
                            "Grupo de trajetórias", htmlFor="cluster-group", className="sr-only"
                        ),
                        dropdown(
                            "cluster-group",
                            options=[
                                {"label": "Todos os grupos", "value": "all"},
                                *[
                                    {
                                        "label": html.Span(
                                            [
                                                html.Span(
                                                    className="cluster-option-swatch",
                                                    style={"backgroundColor": colour},
                                                    **{"aria-hidden": "true"},
                                                ),
                                                f"Grupo {group}",
                                            ],
                                            className="cluster-option",
                                        ),
                                        "value": str(group),
                                    }
                                    for group, colour in CLUSTER_COLORS.items()
                                ],
                            ],
                            value="all",
                            clearable=False,
                            searchable=False,
                        ),
                    ],
                    className="cluster-field",
                ),
            ),
        ]
    return html.Div(content, id="models-panel", className="view-panel is-hidden")


def methodology():
    source = f"https://huggingface.co/datasets/{REPO_ID}/blob/{REVISION}"
    return html.Details(
        [
            html.Summary("Dados, critérios e limites de interpretação"),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("O que é observado"),
                            html.P(
                                "Valores declarados à autoridade tributária na "
                                "data de pagamento do "
                                "ITBI. A fonte de BH não distingue a natureza da "
                                "transferência; os "
                                "registros não podem ser tratados como vendas de "
                                "mercado verificadas."
                            ),
                            html.P(
                                "Apartamentos e casas sem sinalização em "
                                "value_flag e com valor nominal"
                                " entre R$ 100 e R$ 200.000/m², inclusive. As "
                                "contagens do painel são "
                                "de registros elegíveis, não de todo o ITBI. "
                                "Medianas do resumo e "
                                "distribuições exigem ao menos cinco observações."
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3("Tempo, moeda e dispersão"),
                            html.P(
                                "Janela de exploração: 2016–2025, como nas séries do notebook. "
                                "Valores reais vêm da própria fonte, corrigidos pelo IPCA "
                                f"para {IPCA_BASE}; não são recalculados no painel. "
                                "Valores nominais de vários anos não descontam a inflação."
                            ),
                            html.P(
                                "Quartis usam interpolação linear do pandas. "
                                "Períodos sem amostra "
                                "suficiente permanecem como lacunas; P25–P75 não "
                                "é um intervalo de "
                                "confiança. O diagnóstico exige também área "
                                "construída positiva."
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3("Geografia e proveniência"),
                            html.P(
                                "O mapa mostra até 8.000 registros com área positiva "
                                "e centroide de face, após restringir o valor nominal/m² "
                                "a P2–P98 do recorte. Centroides de CEP e bairro não "
                                "entram no mapa. Não há deslocamento artificial dos pontos. "
                                "Os resumos e as séries usam todos os registros elegíveis, "
                                "independentemente da amostra desenhada."
                            ),
                            html.P(
                                [
                                    "Fonte: Prefeitura de Belo Horizonte, dados "
                                    "abertos. Tratamento: "
                                    "pracadata/brazil-itbi. Licença dos dados de "
                                    "BH: CC-BY. Trabalho "
                                    "derivado e não oficial. ",
                                    html.A(
                                        "Dicionário e limitações",
                                        href=f"{source}/DATA_DICTIONARY.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                    " · ",
                                    html.A(
                                        "Versão da fonte",
                                        href=f"{source}/README.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                ]
                            ),
                        ]
                    ),
                ],
                className="methodology-grid",
            ),
        ],
        id="metodologia",
        className="methodology",
    )


def build_layout(neighbourhoods: list[str], models: dict | None, raw_rows: int):
    return html.Div(
        [
            dcc.Store(id="url-navigation"),
            dcc.Store(id="url-ready", data=False),
            dcc.Store(
                id="url-config",
                data={"options": QUERY_OPTIONS, "defaults": default_controls()},
            ),
            html.A("Ir para os gráficos", href="#conteudo", className="skip-link"),
            html.Header(
                [
                    html.Div(
                        [
                            html.Span("BELO HORIZONTE / MG", className="eyebrow"),
                            html.A(
                                "Sobre os dados", href="#metodologia", className="about-link"
                            ),
                        ],
                        className="masthead-top",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H1("Painel do Mercado Residencial de Belo Horizonte"),
                                    html.P(
                                        "Panorama analítico do mercado residencial a partir "
                                        "dos registros do ITBI.",
                                        className="subtitle",
                                    ),
                                ],
                                className="masthead-title",
                            ),
                            html.Div(
                                [
                                    html.P(
                                        "Base analítica dos registros", className="meta-label"
                                    ),
                                    html.Dl(
                                        [
                                            html.Dt("Período"),
                                            html.Dd("2016–2025"),
                                            html.Dt("Registros na fonte"),
                                            html.Dd(number(raw_rows)),
                                            html.Dt("Valores reais"),
                                            html.Dd(f"IPCA, {IPCA_BASE}"),
                                        ],
                                        className="masthead-facts",
                                    ),
                                ],
                                className="masthead-meta",
                            ),
                        ],
                        className="masthead-main",
                    ),
                ],
                className="masthead",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Tipo de imóvel",
                                        htmlFor="property-type",
                                        id="property-type-label",
                                    ),
                                    dropdown(
                                        "property-type",
                                        options=[
                                            {"label": "Apartamentos", "value": "apartment"},
                                            {"label": "Casas", "value": "house"},
                                            {"label": "Apartamentos e casas", "value": "all"},
                                        ],
                                        value="all",
                                        clearable=False,
                                        searchable=False,
                                    ),
                                ],
                                className="filter-field type-field",
                                role="group",
                                **{"aria-labelledby": "property-type-label"},
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label("Período", id="years-label"),
                                            html.Span(
                                                "2016–2025",
                                                id="years-value",
                                                className="period-value",
                                            ),
                                        ],
                                        className="period-heading",
                                    ),
                                    dcc.RangeSlider(
                                        id="year-range",
                                        min=YEARS[0],
                                        max=YEARS[-1],
                                        step=1,
                                        value=[YEARS[0], YEARS[-1]],
                                        allowCross=False,
                                        marks={
                                            y: str(y)
                                            for y in YEARS
                                            if y in (2016, 2019, 2022, 2025)
                                        },
                                        tooltip={
                                            "placement": "bottom",
                                            "always_visible": False,
                                        },
                                        updatemode="mouseup",
                                        allow_direct_input=False,
                                    ),
                                ],
                                className="filter-field years-field",
                                role="group",
                                **{"aria-labelledby": "years-label"},
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Bairros",
                                        htmlFor="neighbourhoods",
                                        id="neighbourhoods-label",
                                    ),
                                    dropdown(
                                        "neighbourhoods",
                                        options=[
                                            {"label": name.title(), "value": name}
                                            for name in neighbourhoods
                                        ],
                                        value=[],
                                        multi=True,
                                        placeholder="Toda a cidade",
                                        clearable=True,
                                    ),
                                ],
                                className="filter-field neighbourhood-field",
                                role="group",
                                **{"aria-labelledby": "neighbourhoods-label"},
                            ),
                            html.Button(
                                "Restaurar filtros",
                                id="reset-filters",
                                className="button button-quiet reset-button",
                            ),
                        ],
                        id="filter-controls",
                        className="filters",
                    ),
                    html.P(
                        "Filtros aplicados ao panorama e aos diagnósticos.",
                        id="filter-note",
                        className="filter-note",
                        role="status",
                    ),
                ],
                className="filter-area",
            ),
            html.Div(
                [
                    html.Button(
                        label,
                        id=f"tab-{name}",
                        role="tab",
                        className="view-tab view-tab-selected"
                        if name == "overview"
                        else "view-tab",
                        tabIndex=0 if name == "overview" else -1,
                        **{
                            "aria-selected": "true" if name == "overview" else "false",
                            "aria-controls": f"{name}-panel",
                        },
                    )
                    for name, label in [
                        ("overview", "Panorama"),
                        ("diagnostics", "Diagnósticos"),
                        ("models", "Índices e trajetórias"),
                    ]
                ],
                className="view-tabs view-tabs-parent",
                role="tablist",
                **{"aria-label": "Seções do painel"},
            ),
            dcc.Store(id="view-tabs", data="overview"),
            html.Main(
                [
                    dcc.Loading(
                        overview_panel(),
                        type="circle",
                        color=TEAL,
                        delay_show=250,
                        delay_hide=80,
                    ),
                    dcc.Loading(
                        diagnostics_panel(),
                        type="circle",
                        color=TEAL,
                        delay_show=250,
                        delay_hide=80,
                    ),
                    models_panel(models),
                ],
                id="conteudo",
            ),
            methodology(),
            html.Footer(
                [
                    html.Span(
                        "Mercado Residencial de Belo Horizonte", className="footer-brand"
                    ),
                    html.P(
                        "Fonte: Prefeitura de Belo Horizonte, dados abertos. Tratamento: "
                        "pracadata/brazil-itbi (Hugging Face). Trabalho derivado e não oficial."
                    ),
                    html.A(
                        "Consultar a fonte",
                        href=f"https://huggingface.co/datasets/{REPO_ID}",
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                ],
                className="footer",
            ),
            dcc.Store(id="view-resize"),
        ],
        className="app-shell",
    )
