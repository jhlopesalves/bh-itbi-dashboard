"""Regression snapshots captured through the public Dash HTTP endpoints.

Regenerate the ignored local snapshots and the committed checksum manifest only
when explicitly permitted by setting ``UPDATE_SNAPSHOTS=1``:

    UPDATE_SNAPSHOTS=1 uv run pytest tests/test_view_snapshots.py::test_view_snapshots

Real-data snapshots can be captured or verified in an uncommitted directory by
setting ``BH_ITBI_REAL_SNAPSHOTS_DIR=/path/to/dir`` and running
``test_real_data_view_snapshots`` (with ``UPDATE_SNAPSHOTS=1`` only for capture).

Clean checkouts compare checksums by output. Matching local snapshots also
provide value-level diffs for the changed outputs.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from dash import Dash
from snapshot_io import snapshot_digest, snapshot_json
from test_app import post_callback

from bh_itbi.app import create_app
from bh_itbi.filters import Filters, filter_transactions, positive_area
from bh_itbi.overview import map_points
from bh_itbi.text.shared import CITY_NAME, TYPE_LABELS
from bh_itbi.theme import (
    AXIS,
    EXTRA_NEIGHBOURHOOD_COLOUR,
    GRID,
    INK,
    MUTED,
    REFERENCE,
    SLATE,
    SURFACE,
    TRANSPARENT,
    TYPE_STYLES,
    composition_tint,
    neighbourhood_styles,
    rgba,
)

SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"
SYNTHETIC_MANIFEST = Path(__file__).with_name("view_snapshot_digests.json")
NINE_NEIGHBOURHOODS = [
    "ANCHIETA",
    "BURITIS",
    "CASTELO",
    "CENTRO",
    "FUNCIONARIOS",
    "LOURDES",
    "SANTO AGOSTINHO",
    "SAVASSI",
    "SION",
]
VIEW_MATRIX: dict[str, tuple[str, list[int], list[str], str, str]] = {
    "defaults": ("all", [2016, 2025], [], "price_per_m2_brl_real", "carto-voyager"),
    "apartment_2023_2025": ("apartment", [2023, 2025], [], "price_per_m2_brl", "white-bg"),
    "house_2016_2018": ("house", [2016, 2018], [], "value_declared_brl", "carto-voyager"),
    "apartment_2024_savassi_centro": (
        "apartment",
        [2024, 2024],
        ["SAVASSI", "CENTRO"],
        "price_per_m2_brl_real",
        "white-bg",
    ),
    "nine_neighbourhoods": (
        "all",
        [2016, 2025],
        NINE_NEIGHBOURHOODS,
        "price_per_m2_brl_real",
        "carto-voyager",
    ),
    "unknown_neighbourhood": (
        "all",
        [2016, 2025],
        ["UNKNOWN"],
        "price_per_m2_brl_real",
        "carto-voyager",
    ),
}


def canonicalise(value: Any) -> Any:
    """Round floats to 10 significant digits and sort dictionary keys recursively."""
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return 0.0 if value == 0.0 else float(f"{value:.10g}")
    if isinstance(value, dict):
        if {"dtype", "bdata"} <= value.keys() <= {"dtype", "bdata", "shape"}:
            # Plotly encodes NumPy arrays as base64. Compare their numbers at the
            # same precision as plain JSON floats, retaining the dtype and shape.
            array = np.frombuffer(base64.b64decode(value["bdata"]), dtype=value["dtype"])
            return {
                **{key: item for key, item in value.items() if key != "bdata"},
                "values": canonicalise(array.tolist()),
            }
        return {
            str(key): canonicalise(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [canonicalise(item) for item in value]
    raise TypeError(f"Unsupported snapshot value type: {type(value)!r}")


def normalise_index_html(html_text: str) -> str:
    """Compare the complete rendered document apart from runtime and asset tokens."""
    html_text = re.sub(r"(/assets/[^\"?]+)\?m=[0-9.]+", r"\1", html_text)
    html_text = re.sub(r"(/_dash-component-suites/[^\"?]+\.v[\d_]+)m\d+", r"\1", html_text)
    html_text = re.sub(
        r'"(end_id|python_version)":"[^"]*"',
        r'"\1":"{runtime}"',
        html_text,
    )
    # The shared script is a required internal addition. A separate assertion
    # checks its load order once the shared JavaScript is introduced.
    return html_text.replace('<script src="/assets/01-chart-helpers.js"></script>\n', "")


def capture_diagnostics(app: Dash, controls: list[Any]) -> dict[str, Any]:
    """Snapshot the diagnostics response, checking the optional padding transport."""
    response = post_callback(app, "tax-figure.figure", controls)
    distance = response["distance-figure"]["figure"]["layout"]
    if "meta" in distance:
        # The browser's padding input is the sole extra distance figure property
        # required by the brief. Assert its exact value before comparing the UI.
        assert distance.pop("meta") == {"pad_fraction": 0.05}
    return response


def capture_models(app: Dash, tab: str) -> dict[str, Any]:
    """Compare the interpolated ribbon dates at browser date precision."""
    response = post_callback(app, "hedonic-figure.figure", [tab])
    for trace in response["hedonic-figure"]["figure"]["data"]:
        coordinates = trace.get("x")
        if isinstance(coordinates, list):
            # Floating-point interpolation can move a crossing by nanoseconds
            # between BLAS implementations. The chart uses millisecond dates.
            trace["x"] = [
                pd.Timestamp(value).round("ms").isoformat(timespec="milliseconds")
                if isinstance(value, str) and "." in value
                else value
                for value in coordinates
            ]
    return response


def _diff_dict(expected: dict[str, Any], actual: dict[str, Any], path: str) -> list[str]:
    expected_keys = set(expected)
    actual_keys = set(actual)
    diffs = [
        f"{path}.{key}: missing key (expected {expected[key]!r})"
        for key in sorted(expected_keys - actual_keys)
    ]
    diffs.extend(
        f"{path}.{key}: unexpected key (got {actual[key]!r})"
        for key in sorted(actual_keys - expected_keys)
    )
    for key in sorted(expected_keys & actual_keys):
        diffs.extend(diff_values(expected[key], actual[key], f"{path}.{key}"))
        if len(diffs) >= 25:
            break
    return diffs[:25]


def diff_values(expected: Any, actual: Any, path: str = "$") -> list[str]:
    """Produce human-readable key-path diffs between two canonical JSON structures."""
    if type(expected) is not type(actual):
        exp_type = type(expected).__name__
        act_type = type(actual).__name__
        return [f"{path}: expected type {exp_type} ({expected!r}), got {act_type} ({actual!r})"]
    if isinstance(expected, dict):
        return _diff_dict(expected, actual, path)
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [f"{path}: expected list of length {len(expected)}, got {len(actual)}"]
        diffs: list[str] = []
        for idx, (exp_item, act_item) in enumerate(zip(expected, actual, strict=True)):
            diffs.extend(diff_values(exp_item, act_item, f"{path}[{idx}]"))
            if len(diffs) >= 25:
                break
        return diffs[:25]
    if expected != actual:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def capture_suite(app: Dash) -> dict[str, Any]:
    """Capture HTTP routes and all server callbacks across the required view matrix."""
    client = app.server.test_client()
    index_response = client.get("/")
    layout_response = client.get("/_dash-layout")
    health_response = client.get("/healthz")
    assert index_response.status_code == 200
    assert layout_response.status_code == 200
    assert health_response.status_code == 200

    snapshots: dict[str, Any] = {
        "document_and_layout": canonicalise(
            {
                "index_html": normalise_index_html(index_response.data.decode("utf-8")),
                "layout": layout_response.get_json(),
                "healthz": health_response.get_json(),
            }
        )
    }

    for name, controls in VIEW_MATRIX.items():
        property_type, years, neighbourhoods, *_ = controls
        snapshots[f"overview__{name}"] = canonicalise(
            {
                "overview": post_callback(app, "geo-map.figure", list(controls)),
                "period": post_callback(app, "years-value.children", [years]),
            }
        )
        snapshots[f"diagnostics__{name}"] = canonicalise(
            {
                "diagnostics": capture_diagnostics(
                    app,
                    [property_type, years, neighbourhoods, "diagnostics"],
                )
            }
        )

    tabs = ("overview", "diagnostics", "models")
    snapshots["tabs_models_and_selection"] = canonicalise(
        {
            "select_view": {
                tab: post_callback(
                    app,
                    "view-tabs.data",
                    [1, 1, 1],
                    changed=f"tab-{tab}.n_clicks",
                )
                for tab in tabs
            },
            "switch_view": {
                tab: post_callback(app, "overview-panel.className", [tab]) for tab in tabs
            },
            "models": {"models": capture_models(app, "models")},
            "restore_selection": {
                "query": post_callback(
                    app,
                    "property-type.value",
                    [
                        {
                            "search": (
                                "?tipo=apartamento&inicio=2023&fim=2025"
                                "&bairros=SAVASSI&medida=nominal_m2&mapa=sem_fundo"
                            ),
                            "revision": 1,
                        },
                        0,
                        None,
                    ],
                    changed="url-navigation.data",
                    states=["all", [2016, 2025], []],
                ),
                "map_click": post_callback(
                    app,
                    "property-type.value",
                    [None, 0, {"points": [{"customdata": ["SAVASSI", "Savassi"]}]}],
                    changed="geo-map.clickData",
                    states=["all", [2016, 2025], []],
                ),
                "reset": post_callback(
                    app,
                    "property-type.value",
                    [None, 1, None],
                    changed="reset-filters.n_clicks",
                    states=["apartment", [2023, 2025], ["SAVASSI"]],
                ),
            },
        }
    )
    return snapshots


def verify_or_write_snapshots(
    snapshots: dict[str, Any], directory: Path, *, update: bool
) -> None:
    """Write golden files when updating; otherwise assert byte-accurate canonical equality."""
    if update:
        directory.mkdir(parents=True, exist_ok=True)
        for name, payload in snapshots.items():
            target = directory / f"{name}.json"
            target.write_text(
                snapshot_json(payload),
                encoding="utf-8",
            )
        return

    failures: list[str] = []
    for name, actual in snapshots.items():
        target = directory / f"{name}.json"
        if not target.exists():
            failures.append(f"Missing snapshot file: {target}")
            continue
        expected = json.loads(target.read_text(encoding="utf-8"))
        if diffs := diff_values(expected, actual, path=name):
            failures.extend(diffs)
    if failures:
        formatted = "\n  ".join(failures)
        pytest.fail(f"Snapshot mismatch:\n  {formatted}")


def _callback_outputs(prefix: str, response: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Identify each output by its exact Dash component ID and property."""
    for component, properties in response.items():
        for prop, value in properties.items():
            yield f"{prefix}/{component}.{prop}", value


def snapshot_outputs(snapshots: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Index canonical values without changing the raw snapshot file format."""
    for name, payload in snapshots.items():
        if name == "document_and_layout":
            yield "index", payload["index_html"]
            yield "layout", payload["layout"]
            yield "healthz", payload["healthz"]
        elif name == "tabs_models_and_selection":
            for action, cases in payload.items():
                for case, response in cases.items():
                    yield from _callback_outputs(f"{action}/{case}", response)
        else:
            view, case = name.split("__", maxsplit=1)
            for response in payload.values():
                yield from _callback_outputs(f"{view}/{case}", response)


def snapshot_failures(
    expected: dict[str, str], actual: dict[str, str], values: dict[str, Any]
) -> list[str]:
    """Report missing, unexpected or changed outputs, with local diffs when available."""
    failures = [f"{key}: missing output" for key in sorted(expected.keys() - actual.keys())]
    failures.extend(
        f"{key}: unexpected output" for key in sorted(actual.keys() - expected.keys())
    )
    changed = sorted(
        key for key in expected.keys() & actual.keys() if expected[key] != actual[key]
    )
    if not changed:
        return failures

    local = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in SNAPSHOTS_DIR.glob("*.json")
    }
    references = dict(snapshot_outputs(local))
    for key in changed:
        if (
            key in references
            and snapshot_digest(snapshot_json(references[key])) == expected[key]
        ):
            failures.extend(diff_values(references[key], values[key], path=key))
        else:
            failures.append(f"{key}: expected SHA-256 {expected[key]}, got {actual[key]}")
    return failures


@pytest.fixture(scope="session")
def snapshot_app(snapshot_frame: pd.DataFrame, snapshot_models: Any) -> Dash:
    return create_app(
        frame=snapshot_frame,
        models=snapshot_models,
        audit_endpoint={
            "quarter": "2025Q4",
            "published": 110.04,
            "robust": 105.44,
            "robust_lower": 102.57,
            "robust_upper": 108.38,
        },
    )


def test_synthetic_dataset_covers_all_required_populations(
    snapshot_frame: pd.DataFrame, snapshot_models: Any
) -> None:
    counts = snapshot_frame["neighbourhood"].value_counts()
    assert snapshot_frame["neighbourhood"].nunique() >= 25
    assert {"SAVASSI", "LOURDES", "BURITIS", "CASTELO", "CENTRO"} <= set(counts.index)
    assert (counts >= 50).sum() >= 4
    assert ((counts >= 15) & (counts < 50)).sum() >= 5
    assert (counts < 15).sum() >= 3
    assert set(snapshot_frame["property_type"].unique()) == {"apartment", "house"}
    assert set(snapshot_frame["building_age_band"].unique()) == {
        "new",
        "3_10",
        "11_25",
        "26_plus",
    }
    assert snapshot_frame["quarter"].nunique() == 40
    assert (snapshot_frame["built_area_m2"] <= 0).any()
    assert (snapshot_frame["built_area_m2"] > 0).any()
    assert (snapshot_frame["value_tax_base_brl"] > snapshot_frame["value_declared_brl"]).any()
    assert (snapshot_frame["value_tax_base_brl"] < snapshot_frame["value_declared_brl"]).any()
    assert snapshot_models is not None
    distances = snapshot_frame.loc[
        snapshot_frame["face_geocoded"] & snapshot_frame["property_type"].eq("apartment")
    ]
    assert distances["distance_km"].min() < 1
    assert distances["distance_km"].max() > 13
    period = pd.cut(distances["year"], [2015, 2018, 2021, 2025])
    cells = distances.groupby([period, np.floor(distances["distance_km"])], observed=True)
    assert cells.size().ge(50).sum() >= 3


@pytest.fixture(scope="session")
def view_snapshots(snapshot_app: Dash) -> dict[str, Any]:
    return capture_suite(snapshot_app)


def _assert_trace_colour(trace: dict[str, Any], output: str) -> None:
    line = trace.get("line", {})
    marker = trace.get("marker", {})
    fill = trace.get("fillcolor")
    description = (output, trace.get("name"), trace["type"])
    assert any(value is not None for value in (line.get("color"), marker.get("color"), fill)), (
        description
    )
    if trace["type"] == "scatter":
        mode = trace["mode"]
        if "lines" in mode and line.get("width") != 0:
            assert line.get("color") is not None, description
        if "markers" in mode:
            assert marker.get("color") is not None or (
                "lines" in mode and line.get("color") is not None
            ), description
        if trace.get("fill", "none") != "none":
            assert fill is not None, description
    else:
        assert marker.get("color") is not None, description


def test_every_plotly_trace_has_an_explicit_colour(view_snapshots: dict[str, Any]) -> None:
    for output, figure in snapshot_outputs(view_snapshots):
        if output.endswith(".figure"):
            assert figure["layout"]["colorway"] == [INK], output
            for trace in figure["data"]:
                _assert_trace_colour(trace, output)


def test_map_keeps_fixed_scales_with_selection_relative_limits(
    view_snapshots: dict[str, Any], snapshot_frame: pd.DataFrame
) -> None:
    def marker(case: str) -> dict[str, Any]:
        return view_snapshots[f"overview__{case}"]["overview"]["geo-map"]["figure"]["data"][0][
            "marker"
        ]

    default = marker("defaults")
    selected = marker("apartment_2023_2025")
    for attribute in ("cmin", "cmax", "sizeref", "colorscale"):
        assert default[attribute] == selected[attribute]
    assert default["colorbar"]["title"]["text"] == "R$/m²<br>real"
    assert default["color"] != selected["color"]

    limits = []
    price = "price_per_m2_brl_real"
    for case in ("defaults", "apartment_2023_2025"):
        kind, years, names, _, _ = VIEW_MATRIX[case]
        frame = filter_transactions(snapshot_frame, Filters.from_controls(kind, years, names))
        candidates = frame.loc[frame["face_geocoded"] & positive_area(frame), price]
        points, stats = map_points(frame)
        assert stats.lower == candidates.quantile(0.02)
        assert stats.upper == candidates.quantile(0.98)
        assert points[price].between(stats.lower, stats.upper).all()
        limits.append((stats.lower, stats.upper))
    assert limits[0][0] != limits[1][0]
    assert limits[0][1] != limits[1][1]


def test_map_colourbar_labels_include_both_open_ends(view_snapshots: dict[str, Any]) -> None:
    figure = view_snapshots["overview__defaults"]["overview"]["geo-map"]["figure"]
    marker = figure["data"][0]["marker"]
    ticks = marker["colorbar"]["tickvals"]
    labels = marker["colorbar"]["ticktext"]
    assert ticks[0] == marker["cmin"]
    assert ticks[-1] == marker["cmax"]
    assert labels[0].startswith("≤ ")
    assert labels[-1].startswith("≥ ")


def test_price_time_axes_follow_the_plotted_values(view_snapshots: dict[str, Any]) -> None:
    outputs = view_snapshots["overview__defaults"]["overview"]
    for chart in ("trend-figure", "neighbourhood-figure"):
        axis = outputs[chart]["figure"]["layout"]["yaxis"]
        assert "rangemode" not in axis
        lower, upper = axis["range"]
        assert 0 < lower < upper
        assert lower % 500 == upper % 500 == 0


@pytest.mark.parametrize("case", VIEW_MATRIX)
def test_neighbourhood_cards_share_colours_and_labels(
    view_snapshots: dict[str, Any], case: str
) -> None:
    outputs = view_snapshots[f"overview__{case}"]["overview"]
    comparison = outputs["comparison-data"]["data"]
    figure = outputs["neighbourhood-figure"]["figure"]
    assert "meta" not in figure["layout"]
    assert figure["layout"]["showlegend"] is True
    trajectories = {
        trace["name"]: trace for trace in figure["data"] if trace["name"] != CITY_NAME
    }
    assert trajectories
    styles = neighbourhood_styles(sorted(VIEW_MATRIX[case][2]))
    assert [trace["name"] for trace in figure["data"]] == [
        *(name.title() for name in styles),
        CITY_NAME,
    ]
    assert {name: trace["line"] for name, trace in trajectories.items()} == {
        name.title(): {"color": style.colour, "dash": style.dash, "width": 2}
        for name, style in styles.items()
    }
    for trace in figure["data"]:
        assert "meta" not in trace
    reference = figure["data"][-1]
    assert reference["name"] == CITY_NAME
    assert reference["line"] == REFERENCE
    assert "legendgroup" not in reference
    for row in comparison["rows"]:
        assert row["name"] and row["colour"] == trajectories[row["name"]]["line"]["color"]


def test_categorical_legends_group_series_and_omit_end_label_metadata(
    view_snapshots: dict[str, Any],
) -> None:
    for output, figure in snapshot_outputs(view_snapshots):
        if not output.endswith(".figure"):
            continue
        layout = figure["layout"]
        assert "end_labels" not in (layout.get("meta") or {}), output
        for trace in figure["data"]:
            assert "meta" not in trace, (output, trace.get("name"))
        if figure["data"] and not output.endswith("geo-map.figure"):
            assert layout["showlegend"] is True, output
            assert layout["legend"]["groupclick"] == "togglegroup", output

    for case, (*_, neighbourhoods, _, _) in VIEW_MATRIX.items():
        monthly = view_snapshots[f"overview__{case}"]["overview"]["trend-figure"]["figure"]
        if not monthly["data"]:
            continue
        visible = [
            trace for trace in monthly["data"] if trace.get("showlegend", True) is not False
        ]
        medians = [trace for trace in visible if trace.get("legendgroup") in TYPE_LABELS]
        references = [trace for trace in visible if "legendgroup" not in trace]
        bands = [trace for trace in monthly["data"] if trace.get("showlegend") is False]
        assert len(medians) == len({trace["legendgroup"] for trace in medians})
        assert {trace["legendgroup"] for trace in bands} <= {
            trace["legendgroup"] for trace in medians
        }
        if bands:
            last_band = max(i for i, t in enumerate(monthly["data"]) if t in bands)
            first_median = min(i for i, t in enumerate(monthly["data"]) if t in medians)
            assert last_band < first_median
        assert bool(references) == bool(neighbourhoods)
        for ref in references:
            assert ref["name"].startswith("BH · ")
            assert ref["line"] == REFERENCE

    payload = view_snapshots["tabs_models_and_selection"]["models"]["models"]
    trajectories = payload["trajectories-figure"]["figure"]
    neighbourhoods, median = trajectories["data"][:-1], trajectories["data"][-1]
    visible = [trace for trace in trajectories["data"] if trace.get("showlegend", True)]
    assert [trace["name"] for trace in visible] == ["Bairros", "Mediana entre os bairros"]
    assert {trace["legendgroup"] for trace in neighbourhoods} == {"neighbourhoods"}
    assert all(trace["line"] == {"color": SLATE, "width": 1} for trace in neighbourhoods)
    assert all(
        trace["mode"] == "lines" and trace["opacity"] == 0.35 for trace in neighbourhoods
    )
    assert median["mode"] == "lines+markers"
    assert median["line"]["color"] == INK
    assert "legendgroup" not in trajectories["layout"]["shapes"][0]


def _plotly_trace_colours(trace: dict[str, Any]) -> Iterator[str]:
    marker = trace.get("marker", {})
    pattern = trace.get("fillpattern", {})
    for value in (
        trace.get("line", {}).get("color"),
        marker.get("color"),
        marker.get("line", {}).get("color"),
        trace.get("fillcolor"),
        pattern.get("fgcolor"),
        pattern.get("bgcolor"),
    ):
        if isinstance(value, list):
            yield from value
        elif value is not None:
            yield value


def test_property_type_series_share_the_original_palette(
    view_snapshots: dict[str, Any],
) -> None:
    charts = {"trend-figure.figure", "distribution-figure.figure", "tax-figure.figure"}
    expected = {"Apartamentos": "#1d6f73", "Casas": "#c0603a"}
    observed = {chart: set() for chart in charts}
    for output, figure in snapshot_outputs(view_snapshots):
        chart = output.rsplit("/", maxsplit=1)[-1]
        if chart not in charts:
            continue
        for trace in figure["data"]:
            name = trace.get("name")
            if name in expected:
                if chart == "distribution-figure.figure":
                    assert trace["type"] == "bar"
                    assert trace["marker"]["color"] == expected[name]
                else:
                    line = trace["line"]
                    assert (line["color"], line["dash"], line["width"]) == (
                        expected[name],
                        "solid",
                        2,
                    )
                observed[chart].add(name)
    assert all(names == expected.keys() for names in observed.values())


@pytest.mark.parametrize("case", VIEW_MATRIX)
def test_panorama_colours_keep_their_assigned_roles(
    view_snapshots: dict[str, Any], case: str
) -> None:
    outputs = view_snapshots[f"overview__{case}"]["overview"]
    rows = outputs["comparison-data"]["data"]["rows"]
    marks = [
        (row[key], ("neighbourhood", row["name"]))
        for row in rows
        for key in ("colour", "outer_fill", "iqr_fill")
    ]
    neighbourhood = outputs["neighbourhood-figure"]["figure"]
    for trace in neighbourhood["data"]:
        role = "reference" if trace["name"] == CITY_NAME else "neighbourhood"
        marks.extend((colour, (role, trace["name"])) for colour in _plotly_trace_colours(trace))

    monthly = outputs["trend-figure"]["figure"]
    for trace in monthly["data"]:
        kind = trace.get("legendgroup")
        role = ("property type", TYPE_LABELS[kind]) if kind else ("reference", trace["name"])
        marks.extend((colour, role) for colour in _plotly_trace_colours(trace))

    histogram = outputs["distribution-figure"]["figure"]
    for trace in histogram["data"]:
        marks.extend(
            (colour, ("property type", trace["name"]))
            for colour in _plotly_trace_colours(trace)
        )
    neutrals = {INK, MUTED, SURFACE, GRID, AXIS, SLATE, TRANSPARENT, REFERENCE["color"]}
    neutrals.add(EXTRA_NEIGHBOURHOOD_COLOUR)
    neutrals.update(
        composition_tint(colour, strength=strength)
        for colour in (SLATE, EXTRA_NEIGHBOURHOOD_COLOUR)
        for strength in (0.34, 0.68)
    )
    property_colours = {
        colour: TYPE_LABELS[kind]
        for kind, style in TYPE_STYLES.items()
        for colour in (style["line"]["color"], rgba(style["line"]["color"], 0.09))
    }
    for shape in histogram["layout"].get("shapes", []):
        colour = shape["line"]["color"]
        marks.append((colour, ("property type", property_colours[colour])))

    unique: dict[str, tuple[str, str]] = {}
    for colour, meaning in marks:
        if colour in neutrals:
            continue
        if meaning[0] == "property type":
            assert property_colours.get(colour) == meaning[1]
        else:
            assert meaning[0] == "neighbourhood"
        assert unique.setdefault(colour, meaning) == meaning


def test_view_snapshots(view_snapshots: dict[str, Any]) -> None:
    update = os.environ.get("UPDATE_SNAPSHOTS") == "1"
    values = dict(snapshot_outputs(view_snapshots))
    actual = {key: snapshot_digest(snapshot_json(value)) for key, value in values.items()}
    if update:
        verify_or_write_snapshots(view_snapshots, SNAPSHOTS_DIR, update=True)
        SYNTHETIC_MANIFEST.write_text(snapshot_json(actual), encoding="utf-8")
        return

    expected = json.loads(SYNTHETIC_MANIFEST.read_text(encoding="utf-8"))
    if failures := snapshot_failures(expected, actual, values):
        pytest.fail("Snapshot mismatch:\n  " + "\n  ".join(failures))


@pytest.mark.skipif(
    not os.environ.get("BH_ITBI_REAL_SNAPSHOTS_DIR"),
    reason="Set BH_ITBI_REAL_SNAPSHOTS_DIR to capture or compare real-data snapshots",
)
def test_real_data_view_snapshots() -> None:
    directory = Path(os.environ["BH_ITBI_REAL_SNAPSHOTS_DIR"])
    update = os.environ.get("UPDATE_SNAPSHOTS") == "1"
    app = create_app(require_prepared=True)
    snapshots = capture_suite(app)
    verify_or_write_snapshots(snapshots, directory, update=update)
