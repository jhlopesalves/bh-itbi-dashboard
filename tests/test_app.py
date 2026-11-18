"""Real Dash HTTP callbacks, with a deliberately injected offline test dataset."""

import pytest

from bh_itbi.app import create_app
from bh_itbi.data import prepare_transactions


@pytest.fixture
def app(source_factory):
    return create_app(frame=prepare_transactions(source_factory()))


def post_callback(app, key_part, values, changed=None, states=None):
    key = next(k for k in app.callback_map if key_part in k)
    callback = app.callback_map[key]
    output = callback["output"]
    outputs = (
        [{"id": o.component_id, "property": o.component_property} for o in output]
        if isinstance(output, list)
        else {"id": output.component_id, "property": output.component_property}
    )
    inputs = [
        {**item, "value": value} for item, value in zip(callback["inputs"], values, strict=True)
    ]
    state = [
        {**item, "value": value}
        for item, value in zip(callback["state"], states or [], strict=True)
    ]
    response = app.server.test_client().post(
        "/_dash-update-component",
        json={
            "output": key,
            "outputs": outputs,
            "inputs": inputs,
            "state": state,
            "changedPropIds": [changed or f"{inputs[0]['id']}.{inputs[0]['property']}"],
        },
    )
    assert response.status_code == 200, response.data.decode()
    return response.get_json()["response"]


def test_application_routes_and_portuguese_document(app):
    client = app.server.test_client()
    page = client.get("/")
    assert page.status_code == 200 and b'lang="pt-BR"' in page.data
    assert client.get("/_dash-layout").status_code == 200
    assert client.get("/_dash-dependencies").status_code == 200


def test_connected_callback_and_empty_neighbourhood_selection(app):
    defaults = ["apartment", [2016, 2016], [], "price_per_m2_brl_real", "white-bg"]
    response = post_callback(app, "geo-map.figure", defaults)
    assert response["kpi-count"]["children"] == "40"
    assert response["geo-map"]["figure"]["data"][0]["type"] == "scattermap"
    selection = defaults.copy()
    selection[2] = ["SAVASSI"]
    response = post_callback(app, "geo-map.figure", selection)
    assert response["kpi-count"]["children"] == "20"
    assert "Savassi" in response["scope-label"]["children"]
    selection[2] = ["UNKNOWN"]
    response = post_callback(app, "geo-map.figure", selection)
    assert response["kpi-count"]["children"] == "0"
    assert response["kpi-nominal"]["children"] == "—"
    assert "annotations" in response["distribution-figure"]["figure"]["layout"]


def test_map_click_selects_source_neighbourhood_and_reset_returns_to_city(app):
    click = {"points": [{"customdata": ["SAVASSI", "Savassi"]}]}
    values = [None, 0, click]
    states = ["apartment", [2016, 2016], []]
    selected = post_callback(
        app, "property-type.value", values, changed="geo-map.clickData", states=states
    )
    assert selected["neighbourhoods"]["value"] == ["SAVASSI"]
    cleared = post_callback(
        app,
        "property-type.value",
        [None, 1, click],
        changed="reset-filters.n_clicks",
        states=["apartment", [2016, 2016], ["SAVASSI"]],
    )
    assert cleared["neighbourhoods"]["value"] == []
    assert cleared["year-range"]["value"] == [2016, 2025]


def test_models_tab_explicitly_disables_exploration_filters(app):
    response = post_callback(app, "overview-panel.className", ["models"])
    assert response["models-panel"]["className"] == "view-panel"
    assert response["property-type"]["disabled"]
    assert "fixas" in response["filter-note"]["children"]


def test_diagnostics_callback_handles_insufficient_samples(app):
    response = post_callback(
        app, "tax-figure.figure", ["apartment", [2016, 2016], [], "diagnostics"]
    )
    assert (
        "São necessárias 100"
        in response["tax-figure"]["figure"]["layout"]["annotations"][0]["text"]
    )
    assert "Sem amostra" in response["heaping-caption"]["children"]
    assert not response["age-data"]["data"]["rows"]
    assert "fora do período" in response["age-subtitle"]["children"]


def test_age_callback_handles_few_neighbourhoods_and_small_bands(source_factory):
    source = source_factory(44)
    source["year"] = 2024
    source["transaction_date"] = source["transaction_date"].str.replace("2016", "2024")
    source["building_age_band"] = ["26_plus"] * 15 + ["new"] * 15 + ["3_10"] * 14
    app = create_app(frame=prepare_transactions(source))
    response = post_callback(
        app, "age-data.data", ["apartment", [2024, 2024], [], "diagnostics"]
    )
    chart = response["age-data"]["data"]
    assert not chart["fills"]
    assert len(chart["rows"]) == 2
    assert all(not row["segments"] and row["interval"] is None for row in chart["rows"])
    assert chart["rows"][-1]["reference"]
    assert "Apartamentos, 2024" in response["age-subtitle"]["children"]
    note = response["age-note"]["children"]
    assert "Ajuste indisponível: a seleção tem menos de 20 bairros." in note
    assert "3 a 10 anos (n = 14)" in note
