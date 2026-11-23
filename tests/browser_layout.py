"""Check chart widths in a real browser against a prepared Gunicorn server.

Run this script with a Python environment that has Playwright installed.
Pass --chromium for a system Chrome or Chromium executable.
"""

import argparse
import re
from itertools import combinations, pairwise
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Browser, Page, expect, sync_playwright

PATTERN_PLOTS = tuple(f"pattern-figure-{name}" for name in ("falling", "stable", "rising"))

# Observe every animation frame so a resize that eventually settles still fails
# if a chart expands the page during the transition.
_MONITOR_WIDTH = """
(() => {
    window.widthExcursions = {};
    function measure() {
        const root = document.documentElement;
        if (root && root.scrollWidth > root.clientWidth) {
            const selected = document.querySelector('[role="tab"][aria-selected="true"]');
            const key = (selected?.id || "initial") + "@" + root.clientWidth;
            window.widthExcursions[key] = Math.max(
                window.widthExcursions[key] || 0, root.scrollWidth
            );
        }
        requestAnimationFrame(measure);
    }
    requestAnimationFrame(measure);
})();
"""


def wait_for_plot(page: Page, identifier: str, *, min_traces: int = 1) -> None:
    """Wait for a real figure and a plot sized to its container."""
    page.wait_for_function(
        """([id, traces]) => {
            const plot = document.querySelector('#' + id + ' .js-plotly-plot');
            return plot?.clientWidth > 0 && plot._fullData?.length >= traces &&
                Math.abs(plot._fullLayout.width - plot.clientWidth) < 2;
        }""",
        arg=(identifier, min_traces),
        timeout=45_000,
    )


def assert_no_plot_annotations(page: Page, *identifiers: str) -> None:
    """Ensure active Plotly charts have not acquired end-of-line annotations."""
    counts = page.evaluate(
        """(ids) => Object.fromEntries(ids.map(id => {
            const plot = document.querySelector('#' + id + ' .js-plotly-plot');
            return [id, (plot?.layout?.annotations || []).length];
        }))""",
        list(identifiers),
    )
    assert all(count == 0 for count in counts.values()), counts
    assert_plot_legend_layout(page, *identifiers)


def assert_plot_legend_layout(page: Page, *identifiers: str) -> None:
    """Check that legends fit inside their cards and outside the plotting area."""
    violations = page.evaluate(
        """(ids) => ids.flatMap(id => {
            const host = document.getElementById(id);
            const plot = host?.querySelector('.js-plotly-plot');
            const card = host?.closest('.chart-card');
            const legend = host?.querySelector('.infolayer .legend');
            const size = plot?._fullLayout?._size;
            const footnote = card?.querySelector('.card-footnote');
            if (!card || !plot || !legend || !size) {
                return [`${id}: missing legend or plot layout`];
            }
            const cardBox = card.getBoundingClientRect();
            const plotBox = plot.getBoundingClientRect();
            const legBox = legend.getBoundingClientRect();
            const plotBottom = plotBox.top + size.t + size.h;
            const issues = [];
            if (legBox.left < cardBox.left - 1 || legBox.right > cardBox.right + 1) {
                issues.push(`${id}: legend horizontal overflow`);
            }
            if (legBox.top < plotBottom - 1) {
                issues.push(`${id}: legend overlaps plotting area`);
            }
            if (size.h < 140) {
                issues.push(`${id}: insufficient plot height (${size.h}px)`);
            }
            if (footnote) {
                const footBox = footnote.getBoundingClientRect();
                if (legBox.bottom > footBox.top + 1) {
                    issues.push(`${id}: legend overlaps footnote`);
                }
            }
            return issues;
        })""",
        list(identifiers),
    )
    assert not violations, violations


def click_legend_item(page: Page, identifier: str, label: str, *, double: bool = False) -> None:
    """Click or double-click a native Plotly legend entry by its exact label."""
    item = (
        page.locator(f"#{identifier} .legend .traces")
        .filter(has=page.locator(".legendtext", has_text=re.compile(rf"^{re.escape(label)}$")))
        .locator(".legendtoggle")
    )
    if double:
        item.dblclick()
    else:
        item.click()
    # Wait past Plotly's 300ms doubleClickDelay so single clicks fire and do not merge.
    page.wait_for_timeout(450)


def check_map_colourbar(page: Page) -> None:
    """Check the endpoint labels, round ticks and their rendered spacing."""
    labels = page.locator("#geo-map .cbaxis text")
    expect(labels).to_have_text(
        ["≤ 850", *(f"{i}.000" for i in range(1, 10)), "≥ 9.325"], timeout=45_000
    )
    boxes = labels.evaluate_all("""nodes => nodes.map(node => {
        const box = node.getBoundingClientRect();
        return {top: box.top, bottom: box.bottom};
    })""")
    assert all(upper["bottom"] <= lower["top"] for lower, upper in pairwise(boxes)), boxes


def check_overview_legends(page: Page, url: str) -> None:
    """Verify trend, histogram and neighbourhood legend interactions in a real browser."""
    wait_for_plot(page, "trend-figure", min_traces=4)
    wait_for_plot(page, "distribution-figure", min_traces=2)
    wait_for_plot(page, "neighbourhood-figure", min_traces=6)
    assert_no_plot_annotations(
        page, "trend-figure", "distribution-figure", "neighbourhood-figure"
    )
    for chart in ("trend-figure", "distribution-figure", "neighbourhood-figure"):
        expect(page.locator(f"#{chart} .infolayer .legend")).to_have_count(1)

    for group, label in (("apartment", "Apartamentos"), ("house", "Casas")):
        click_legend_item(page, "trend-figure", label)
        page.wait_for_function(
            """([id, grp]) => {
                const plot = document.querySelector('#' + id + ' .js-plotly-plot');
                const target = plot.data.filter(t => t.legendgroup === grp);
                const others = plot.data.filter(t => t.legendgroup !== grp);
                return target.length > 1 &&
                    target.every(t => t.visible === 'legendonly') &&
                    others.every(t => t.visible !== 'legendonly' && t.visible !== false);
            }""",
            arg=("trend-figure", group),
        )
        click_legend_item(page, "trend-figure", label)
        page.wait_for_function(
            """(id) => document.querySelector('#' + id + ' .js-plotly-plot')
                .data.every(t => t.visible === true || t.visible === undefined)""",
            arg="trend-figure",
        )

    click_legend_item(page, "distribution-figure", "Apartamentos")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#distribution-figure .js-plotly-plot');
            const trace = plot.data.find(t => t.legendgroup === 'apartment');
            const shape = plot.layout.shapes.find(s => s.legendgroup === 'apartment');
            const house = plot.data.find(t => t.legendgroup === 'house');
            return trace?.visible === 'legendonly' && shape?.visible === 'legendonly' &&
                house?.visible !== 'legendonly';
        }"""
    )
    click_legend_item(page, "distribution-figure", "Apartamentos")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#distribution-figure .js-plotly-plot');
            const trace = plot.data.find(t => t.legendgroup === 'apartment');
            const shape = plot.layout.shapes.find(s => s.legendgroup === 'apartment');
            return trace?.visible === true && shape?.visible === true;
        }"""
    )

    click_legend_item(page, "neighbourhood-figure", "Savassi", double=True)
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#neighbourhood-figure .js-plotly-plot');
            return plot.data.every(t =>
                t.name === 'Savassi' ? t.visible !== 'legendonly' : t.visible === 'legendonly'
            );
        }"""
    )
    click_legend_item(page, "neighbourhood-figure", "Savassi", double=True)
    page.wait_for_function(
        """() => document.querySelector('#neighbourhood-figure .js-plotly-plot')
            .data.every(t => t.visible !== 'legendonly' && t.visible !== false)"""
    )

    page.goto(url + "/?bairros=SAVASSI", wait_until="domcontentloaded")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#trend-figure .js-plotly-plot');
            return plot?.data?.some(t => t.name === 'BH · Apartamentos');
        }"""
    )
    assert_no_plot_annotations(page, "trend-figure", "neighbourhood-figure")
    click_legend_item(page, "trend-figure", "Apartamentos")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#trend-figure .js-plotly-plot');
            const apt = plot.data.filter(t => t.legendgroup === 'apartment');
            const ref = plot.data.find(t => t.name === 'BH · Apartamentos');
            return apt.every(t => t.visible === 'legendonly') && ref?.visible !== 'legendonly';
        }"""
    )
    click_legend_item(page, "trend-figure", "BH · Apartamentos")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#trend-figure .js-plotly-plot');
            const ref = plot.data.find(t => t.name === 'BH · Apartamentos');
            return ref?.visible === 'legendonly';
        }"""
    )
    click_legend_item(page, "trend-figure", "Apartamentos")
    click_legend_item(page, "trend-figure", "BH · Apartamentos")
    page.locator("#reset-filters").click()
    expect(page).to_have_url(re.compile(re.escape(url) + r"/$"))


def check_sensitivity_note(page: Page) -> None:
    """Verify the committed endpoint and audit link below the hedonic chart."""
    note = page.locator(".chart-card:has(#hedonic-figure) .boxed-note")
    expect(note.get_by_text("SENSIBILIDADE", exact=True)).to_be_visible()
    expect(note).to_contain_text("4º tri. 2025 é 105,4 (IC 95%: 102,6 a 108,4), contra 110,0")
    expect(note.get_by_role("link", name="Consultar a auditoria")).to_have_attribute(
        "href",
        "https://github.com/jhlopesalves/bh-itbi-dashboard/blob/main/docs/robustness/report.md",
    )


def check_models_legends(page: Page) -> None:
    """Verify the hedonic index and composition legend interactions."""
    page.locator("#tab-models").click()
    wait_for_plot(page, "hedonic-figure", min_traces=10)
    assert_no_plot_annotations(page, "hedonic-figure")

    click_legend_item(page, "hedonic-figure", "Índice hedônico · IC 95%")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#hedonic-figure .js-plotly-plot');
            const index = plot.data.filter(t => t.legendgroup === 'hedonic_index');
            return index.length === 3 && index.every(t => t.visible === 'legendonly');
        }"""
    )
    click_legend_item(page, "hedonic-figure", "Índice hedônico · IC 95%")
    page.wait_for_function(
        """() => document.querySelector('#hedonic-figure .js-plotly-plot')
            .data.filter(t => t.legendgroup === 'hedonic_index')
            .every(t => t.visible === true)"""
    )
    page.wait_for_timeout(350)
    click_legend_item(page, "hedonic-figure", "Faixa de idade")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#hedonic-figure .js-plotly-plot');
            const age = plot.data.filter(t => t.legendgroup === 'age_band');
            return age.length >= 3 && age.every(t => t.visible === 'legendonly');
        }"""
    )
    click_legend_item(page, "hedonic-figure", "Faixa de idade")
    page.wait_for_function(
        """() => document.querySelector('#hedonic-figure .js-plotly-plot')
            .data.every(t => t.visible !== 'legendonly' && t.visible !== false)"""
    )
    check_diagnostics_legends(page)


def check_tax_milestone_labels(page: Page) -> None:
    """Measure the rendered labels and check the selected end-year tick bound."""
    wait_for_plot(page, "tax-figure", min_traces=2)
    labels = page.locator("#tax-figure .annotation-text")
    expect(labels).to_have_text(["Tema 1113 (STJ)", "Lei 11.530", "Dec. 18.735"])
    box = page.locator("#tax-figure").bounding_box()
    assert box is not None
    bounds = []
    for label in labels.all():
        rect = label.bounding_box()
        assert rect is not None
        assert box["x"] <= rect["x"] and rect["x"] + rect["width"] <= box["x"] + box["width"]
        bounds.append(rect)
    for first, second in combinations(bounds, 2):
        horizontal = (
            first["x"] < second["x"] + second["width"]
            and second["x"] < first["x"] + first["width"]
        )
        vertical = (
            first["y"] < second["y"] + second["height"]
            and second["y"] < first["y"] + first["height"]
        )
        assert not (horizontal and vertical), (first, second)
    assert "2026" not in page.locator("#tax-figure .xtick").all_text_contents()


def check_diagnostics_legends(page: Page) -> None:
    """Verify tax-base, round-number histogram and distance-axis rescaling."""
    page.locator("#tab-diagnostics").click()
    wait_for_plot(page, "tax-figure", min_traces=2)
    wait_for_plot(page, "heaping-figure", min_traces=2)
    wait_for_plot(page, "distance-figure", min_traces=3)
    assert_no_plot_annotations(page, "heaping-figure", "distance-figure")
    assert_plot_legend_layout(page, "tax-figure")

    click_legend_item(page, "tax-figure", "Apartamentos")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#tax-figure .js-plotly-plot');
            return plot.data[0].visible === 'legendonly' &&
                plot.data[1].visible !== 'legendonly';
        }"""
    )
    click_legend_item(page, "tax-figure", "Apartamentos")

    click_legend_item(page, "heaping-figure", "Demais faixas")
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#heaping-figure .js-plotly-plot');
            return plot.data[0].visible === 'legendonly' &&
                plot.data[1].visible !== 'legendonly';
        }"""
    )
    click_legend_item(page, "heaping-figure", "Demais faixas")

    initial_range = page.evaluate(
        "document.querySelector('#distance-figure .js-plotly-plot').layout.yaxis.range.slice()"
    )
    click_legend_item(page, "distance-figure", "2022–2025")
    page.wait_for_function(
        """() => document.querySelector('#distance-figure .js-plotly-plot')
            .data.find(t => t.name === '2022–2025')?.visible === 'legendonly'"""
    )
    one_hidden = page.evaluate(
        "document.querySelector('#distance-figure .js-plotly-plot').layout.yaxis.range.slice()"
    )
    assert all(isinstance(v, (int, float)) for v in one_hidden), one_hidden
    click_legend_item(page, "distance-figure", "2019–2021")
    page.wait_for_function(
        """() => document.querySelector('#distance-figure .js-plotly-plot')
            .data.find(t => t.name === '2019–2021')?.visible === 'legendonly'"""
    )
    two_hidden = page.evaluate(
        "document.querySelector('#distance-figure .js-plotly-plot').layout.yaxis.range.slice()"
    )
    assert two_hidden[0] > initial_range[0], (initial_range, two_hidden)
    click_legend_item(page, "distance-figure", "2016–2018")
    page.wait_for_function(
        """() => document.querySelector('#distance-figure .js-plotly-plot')
            .data.every(t => t.visible === 'legendonly')"""
    )
    all_hidden = page.evaluate(
        "document.querySelector('#distance-figure .js-plotly-plot').layout.yaxis.range.slice()"
    )
    assert all_hidden == two_hidden
    for period in ("2016–2018", "2019–2021", "2022–2025"):
        click_legend_item(page, "distance-figure", period)
    page.wait_for_function(
        """() => document.querySelector('#distance-figure .js-plotly-plot')
            .data.every(t => t.visible === true)"""
    )
    restored_range = page.evaluate(
        "document.querySelector('#distance-figure .js-plotly-plot').layout.yaxis.range.slice()"
    )
    assert restored_range == initial_range
    page.locator("#tab-overview").click()


def check_selection(page: Page, url: str) -> None:
    """Restore a shared selection, change a control and reset to the defaults."""
    search = "?tipo=casa&inicio=2020&fim=2024&bairros=SAVASSI"
    page.goto(url + "/" + search, wait_until="domcontentloaded")
    expect(page.locator("#property-type")).to_contain_text("Casas")
    expect(page.locator("#neighbourhoods")).to_contain_text("Savassi")
    slider = page.get_by_role("slider", name="Ano inicial")
    expect(slider).to_have_attribute("aria-valuenow", "2020")
    expect(page.get_by_role("slider", name="Ano final")).to_have_attribute(
        "aria-valuenow", "2024"
    )
    expect(page.locator("#kpi-latest-real")).to_be_visible()
    latest_unit = page.locator("#kpi-latest-real-unit")
    expect(latest_unit).to_contain_text("· 2024 ·", timeout=45_000)
    expect(page).to_have_url(url + "/" + search)
    history_size = page.evaluate("history.length")
    slider.focus()
    slider.press("ArrowRight")
    expect(slider).to_have_attribute("aria-valuenow", "2021")
    page.wait_for_function("new URLSearchParams(location.search).get('inicio') === '2021'")
    assert parse_qs(urlsplit(page.url).query)["bairros"] == ["SAVASSI"]
    page.locator("#reset-filters").click()
    expect(page).to_have_url(re.compile(re.escape(url) + r"/$"))
    expect(page.locator("#property-type")).to_contain_text("Apartamentos e casas")
    expect(slider).to_have_attribute("aria-valuenow", "2016")
    expect(latest_unit).to_contain_text("· 2025 ·", timeout=45_000)
    assert page.evaluate("history.length") == history_size


def check_pattern_panels(page: Page, width: int) -> None:
    """Verify three comparable plots, their member lists and their hover copy."""
    card = page.locator(".patterns-card")
    expect(card.get_by_role("heading", level=3)).to_have_text(
        ["Queda e estabilização", "Estáveis", "Alta recente"]
    )
    expect(card.locator(".pattern-counts")).to_have_text(
        [
            "35 bairros · 29 firmes · 6 de fronteira",
            "51 bairros · 32 firmes · 19 de fronteira",
            "17 bairros · 11 firmes · 6 de fronteira",
        ]
    )
    expect(card.get_by_role("link", name="Consultar a auditoria")).to_be_visible()
    for plot_id in PATTERN_PLOTS:
        wait_for_plot(page, plot_id, min_traces=2)
    plots = card.locator(".js-plotly-plot").evaluate_all("""plots => plots.map(plot => ({
        range: plot._fullLayout.yaxis.range,
        periods: plot._fullLayout.xaxis.tickvals.length,
        legend: plot._fullLayout.showlegend,
    }))""")
    assert len({tuple(plot["range"]) for plot in plots}) == 1
    assert all(plot["periods"] == 5 and not plot["legend"] for plot in plots)
    columns = card.locator(".pattern-grid").evaluate(
        "grid => getComputedStyle(grid).gridTemplateColumns.split(' ').length"
    )
    assert columns == (3 if width > 900 else 1)
    for details in card.locator("details").all():
        summary = details.locator("summary")
        expect(summary).to_have_text("Bairros deste padrão")
        summary.press("Enter")
        expect(details).to_have_attribute("open", "")
        expect(details.get_by_text("Firmes:", exact=False)).to_be_visible()
        expect(details.get_by_text("De fronteira:", exact=False)).to_be_visible()
        summary.press("Enter")
        expect(details.locator("p").first).to_be_hidden()

    stable = card.locator(".pattern-panel").nth(1)
    stable.locator("summary").press("Enter")
    borderline = stable.get_by_text("De fronteira:", exact=False)
    for name in ("Copacabana", "Guarani", "Manacas", "Santa Amelia", "Santa Monica"):
        expect(borderline).to_contain_text(name)
    stable.locator("summary").press("Enter")
    plot = stable.locator(".js-plotly-plot")
    plot.evaluate("""plot => {
        const index = plot.data.findIndex(trace => trace.name === 'Copacabana');
        Plotly.Fx.hover(plot, [{curveNumber: index, pointNumber: 1}]);
    }""")
    hover = stable.locator(".hoverlayer .hovertext")
    expect(hover).to_contain_text("Copacabana")
    expect(hover).to_contain_text("das reamostragens")
    plot.evaluate("""plot => {
        Plotly.Fx.hover(plot, [{curveNumber: plot.data.length - 1, pointNumber: 1}]);
    }""")
    expect(hover).to_contain_text("Centro do padrão")
    expect(hover).to_contain_text("(EP ")
    plot.evaluate("plot => Plotly.Fx.unhover(plot)")


def check_models_viewport(page: Page, width: int) -> None:
    """Activate the models tab and verify its first paint and resize."""
    overview = page.locator("#tab-overview")
    models = page.locator("#tab-models")
    # The four plots render while their tab is inactive. Wait for this so
    # the check includes the first paint of an already-initialised chart.
    page.wait_for_function(
        """() => [...document.querySelectorAll('#models-panel .js-plotly-plot')]
            .filter(plot => plot._fullData?.length > 1).length === 4""",
        timeout=45_000,
    )
    if width < 600:
        models.tap()
    else:
        overview.focus()
        overview.press("End")
        expect(models).to_be_focused()
    expect(models).to_have_attribute("aria-selected", "true")
    check_sensitivity_note(page)
    wait_for_plot(page, "hedonic-figure", min_traces=2)
    for plot_id in PATTERN_PLOTS:
        wait_for_plot(page, plot_id, min_traces=2)
    check_pattern_panels(page, width)
    page.set_viewport_size({"width": 320 if width > 320 else 390, "height": 900})
    wait_for_plot(page, "hedonic-figure", min_traces=2)
    for plot_id in PATTERN_PLOTS:
        wait_for_plot(page, plot_id, min_traces=2)
    assert_no_plot_annotations(page, "hedonic-figure")
    page.set_viewport_size({"width": width, "height": 900})
    wait_for_plot(page, "hedonic-figure", min_traces=2)


def check_masthead(page: Page) -> None:
    """Verify the measurement note and source facts at the active width."""
    note = page.locator(".masthead-title .subtitle + .measurement-note")
    expect(note).to_be_visible()
    expect(note).to_have_text(
        "Valores declarados em registros de ITBI; não representam necessariamente "
        "preços de venda verificados."
    )
    assert note.evaluate(
        """element => {
            const range = document.createRange();
            range.selectNodeContents(element);
            const title = element.parentElement.getBoundingClientRect();
            return [...range.getClientRects()].every(
                line => line.left >= title.left && line.right <= title.right + 1
            );
        }"""
    ), "Measurement note overflows the masthead title"
    facts = page.locator(".masthead-facts")
    expect(facts.locator("dt")).to_have_text(
        [
            "Período",
            "Registros na fonte (todos os anos)",
            "Elegíveis no período",
            "Valores reais",
        ]
    )
    expect(facts.locator("dd")).to_have_text(
        ["2016–2025", "516.725", "205.436", "IPCA, setembro de 2026"]
    )
    for fact in facts.locator("dt, dd").all():
        expect(fact).to_be_visible()


def check_diagnostics_viewport(page: Page, width: int) -> None:
    """Activate diagnostics via the tablist and verify chart layout."""
    diagnostics = page.locator("#tab-diagnostics")
    models = page.locator("#tab-models")
    models.focus()
    models.press("ArrowLeft")
    expect(diagnostics).to_be_focused()
    expect(diagnostics).to_have_attribute("aria-selected", "true")
    expect(page.locator("#age-plot svg")).to_be_visible(timeout=45_000)
    wait_for_plot(page, "distance-figure")
    wait_for_plot(page, "tax-figure", min_traces=2)
    assert_no_plot_annotations(page, "heaping-figure", "distance-figure")
    assert_plot_legend_layout(page, "tax-figure")
    if width in (320, 1440):
        check_tax_milestone_labels(page)
    diagnostics.press("Home")


def check_viewport(browser: Browser, url: str, width: int) -> None:
    """Exercise first activation, every tab and a viewport change."""
    mobile = width < 600
    viewport = {"width": width, "height": 900}
    with browser.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile) as context:
        context.add_init_script(_MONITOR_WIDTH)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="domcontentloaded")
        overview = page.locator("#tab-overview")
        expect(overview).to_have_attribute("aria-selected", "true")
        expect(page.get_by_role("tab")).to_have_count(3)
        check_masthead(page)
        wait_for_plot(page, "distribution-figure", min_traces=2)
        check_models_viewport(page, width)
        check_diagnostics_viewport(page, width)
        expect(overview).to_be_focused()
        expect(overview).to_have_attribute("aria-selected", "true")
        wait_for_plot(page, "geo-map")
        check_map_colourbar(page)
        assert_no_plot_annotations(
            page, "distribution-figure", "trend-figure", "neighbourhood-figure"
        )
        if width == 1440:
            check_overview_legends(page, url)
            check_models_legends(page)
        check_selection(page, url)
        assert page.evaluate("window.widthExcursions") == {}, page.evaluate(
            "window.widthExcursions"
        )
        assert errors == [], errors
    print(f"{width}px: tab transitions, resizing, URL restoration and reset passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="URL of the prepared dashboard")
    parser.add_argument("--chromium", help="Path to a Chromium executable")
    parser.add_argument(
        "--width", type=int, action="append", help="Override the viewport matrix"
    )
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.chromium,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        for width in args.width or (320, 390, 768, 1440):
            check_viewport(browser, args.url.rstrip("/"), width)
        browser.close()


if __name__ == "__main__":
    main()
