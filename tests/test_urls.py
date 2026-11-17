"""Shared selections round-trip through the real clientside URL encoder."""

import json
import shutil
import subprocess
from graphlib import TopologicalSorter
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_app import post_callback

from bh_itbi.app import create_app
from bh_itbi.data import prepare_transactions
from bh_itbi.urls import QUERY_OPTIONS, decode_query, default_controls

NAMES = {"SAVASSI", "LOURDES", "SÃO JOÃO & D'ÁVILA, A+B/#?"}


@pytest.mark.parametrize("search", [None, "", "?", "?unknown=anything"])
def test_default_selection(search):
    assert decode_query(search, NAMES) == default_controls()
    assert default_controls()[0] == "all"


@pytest.mark.parametrize("names", [["SAVASSI"], ["SAVASSI", "LOURDES"], sorted(NAMES)])
def test_neighbourhoods_and_special_characters(names):
    query = urlencode({"bairros": names}, doseq=True)
    assert decode_query("?" + query, NAMES)[2] == sorted(names)
    if len(names) == 3:
        assert "%C3%83" in query and "%26" in query and "%2B" in query


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("?inicio=2020", ("all", [2020, 2025], [], *default_controls()[3:])),
        ("?fim=2021", ("all", [2016, 2021], [], *default_controls()[3:])),
        ("?inicio=2025&fim=2020", default_controls()),
        ("?inicio=1900&fim=2030", default_controls()),
        ("?inicio=no&fim=2020.5", default_controls()),
        ("?tipo=casa&tipo=ambos", default_controls()),
        ("?inicio=&fim=&tipo=&medida=&mapa=", default_controls()),
        ("?tipo=office&medida=invalid&mapa=invalid", default_controls()),
        ("?bairros=unknown&bairros=%FF", default_controls()),
        (
            "?bairros=savassi&bairros=SAVASSI&bairros=unknown",
            ("all", [2016, 2025], ["SAVASSI"], *default_controls()[3:]),
        ),
        ("?" + "x=1&" * 1001, default_controls()),
    ],
)
def test_invalid_and_incomplete_queries(search, expected):
    assert decode_query(search, NAMES) == expected


@pytest.mark.parametrize("kind", ["apartamento", "casa", "ambos"])
def test_presentation_selections_and_property_types(kind):
    result = decode_query(
        f"?tipo={kind}&medida=nominal&mapa=sem_fundo&inicio=2020&fim=2024", NAMES
    )
    assert result == (
        QUERY_OPTIONS["tipo"][kind],
        [2020, 2024],
        [],
        "value_declared_brl",
        "white-bg",
    )


@pytest.fixture
def app(source_factory):
    return create_app(frame=prepare_transactions(source_factory()))


def restore(app, query, *, trigger="url-navigation.data", controls=None, click=None):
    return post_callback(
        app,
        "property-type.value",
        [{"search": query, "revision": 1}, 1, click],
        changed=trigger,
        states=(controls or default_controls())[:3],
    )


def test_shared_link_initialises_controls_and_connected_figures(app):
    query = "?tipo=ambos&inicio=2016&fim=2016&bairros=SAVASSI&medida=nominal&mapa=sem_fundo"
    response = restore(app, query)
    controls = [
        response[name]["value"]
        for name in (
            "property-type",
            "year-range",
            "neighbourhoods",
            "distribution-metric",
            "map-style",
        )
    ]
    assert response["url-ready"]["data"] is True
    assert controls == ["all", [2016, 2016], ["SAVASSI"], "value_declared_brl", "white-bg"]
    result = post_callback(app, "geo-map.figure", controls)
    assert result["kpi-count"]["children"] == "20"
    assert "Savassi" in result["scope-label"]["children"]
    assert result["geo-map"]["figure"]["layout"]["map"]["style"] == "white-bg"
    axis_title = result["distribution-figure"]["figure"]["layout"]["xaxis"]["title"]["text"]
    assert axis_title == "R$ · escala logarítmica"
    diagnostic = post_callback(app, "tax-figure.figure", [*controls[:3], "diagnostics"])
    assert "Savassi" in diagnostic["diagnostic-scope"]["children"]


def test_navigation_overrides_a_stale_map_click_and_reset_restores_all_controls(app):
    click = {"points": [{"customdata": ["SAVASSI", "Savassi"]}]}
    response = restore(app, "?bairros=LOURDES", click=click)
    assert response["neighbourhoods"]["value"] == ["LOURDES"]
    response = restore(app, "?bairros=LOURDES", trigger="geo-map.clickData", click=click)
    assert response == {"neighbourhoods": {"value": ["SAVASSI"]}}
    response = restore(app, "?tipo=casa", trigger="reset-filters.n_clicks", click=click)
    assert [
        response[name]["value"]
        for name in (
            "property-type",
            "year-range",
            "neighbourhoods",
            "distribution-metric",
            "map-style",
        )
    ] == list(default_controls())


def test_navigation_keeps_multiple_neighbourhoods_and_defaults(app):
    selected = restore(app, "?bairros=SAVASSI&bairros=LOURDES")
    assert selected["neighbourhoods"]["value"] == ["LOURDES", "SAVASSI"]
    response = restore(app, "", controls=["house", [2020, 2021], ["LOURDES"]])
    assert response["property-type"]["value"] == "all"
    assert response["year-range"]["value"] == [2016, 2025]
    assert response["neighbourhoods"]["value"] == []


def test_callback_graph_has_no_cycles_or_duplicate_outputs(app):
    graph = {}
    outputs = set()
    for callback in app.callback_map.values():
        dependencies = {f"{item['id']}.{item['property']}" for item in callback["inputs"]}
        output = callback["output"]
        for item in output if isinstance(output, list) else [output]:
            key = str(item)
            assert key not in outputs
            outputs.add(key)
            graph[key] = dependencies
    assert list(TopologicalSorter(graph).static_order())


def test_clientside_encoding_and_history():
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node is required only to exercise the browser JavaScript without a browser"
        )
    result = subprocess.run(
        [node, str(Path(__file__).with_name("sharing.cjs"))],
        input=json.dumps({"options": QUERY_OPTIONS, "defaults": default_controls()}),
        capture_output=True,
        text=True,
        check=True,
    )
    for case in json.loads(result.stdout):
        assert decode_query(case["query"], NAMES) == tuple(case["controls"])
