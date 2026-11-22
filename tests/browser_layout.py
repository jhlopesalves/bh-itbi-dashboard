"""Check chart widths in a real browser against a prepared Gunicorn server.

Run this script with a Python environment that has Playwright installed.
Pass --chromium for a system Chrome or Chromium executable.
"""

import argparse
import re
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Browser, Page, expect, sync_playwright

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


def check_models_legends(page: Page) -> None:
    """Verify cluster groups and hedonic composition legend interactions."""
    page.locator("#tab-models").click()
    wait_for_plot(page, "hedonic-figure", min_traces=10)
    wait_for_plot(page, "clusters-figure", min_traces=8)
    assert_no_plot_annotations(page, "hedonic-figure", "clusters-figure")

    group1_label = (
        page.locator("#clusters-figure .legend .legendtext").first.text_content() or ""
    )
    click_legend_item(page, "clusters-figure", group1_label)
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#clusters-figure .js-plotly-plot');
            const g1 = plot.data.filter(t => t.legendgroup === '1');
            const rest = plot.data.filter(t => t.legendgroup !== '1');
            return g1.length > 1 && g1.every(t => t.visible === 'legendonly') &&
                rest.every(t => t.visible !== 'legendonly');
        }"""
    )
    click_legend_item(page, "clusters-figure", group1_label)
    page.wait_for_function(
        """() => document.querySelector('#clusters-figure .js-plotly-plot')
            .data.every(t => t.visible === true || t.visible === undefined)"""
    )

    page.locator("#cluster-group .dash-dropdown-trigger").click()
    page.get_by_role("option", name="Grupo 1").click()
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#clusters-figure .js-plotly-plot');
            return plot.data.length > 1 && plot.data.every(t => t.legendgroup === '1');
        }"""
    )
    expect(page.locator("#clusters-figure .legend .traces")).to_have_count(1)
    click_legend_item(page, "clusters-figure", group1_label)
    page.wait_for_function(
        """() => document.querySelector('#clusters-figure .js-plotly-plot')
            .data.every(t => t.visible === 'legendonly')"""
    )
    click_legend_item(page, "clusters-figure", group1_label)
    page.wait_for_function(
        """() => document.querySelector('#clusters-figure .js-plotly-plot')
            .data.every(t => t.visible === true)"""
    )
    page.locator("#cluster-group .dash-dropdown-trigger").click()
    page.get_by_role("option", name="Todos os grupos").click()
    page.wait_for_function(
        """() => {
            const plot = document.querySelector('#clusters-figure .js-plotly-plot');
            const groups = new Set(plot.data.map(t => t.legendgroup));
            return groups.size === 4 &&
                plot.data.every(t => t.visible !== 'legendonly' && t.visible !== false);
        }"""
    )

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


def check_diagnostics_legends(page: Page) -> None:
    """Verify tax-base, round-number histogram and distance-axis rescaling."""
    page.locator("#tab-diagnostics").click()
    wait_for_plot(page, "tax-figure", min_traces=2)
    wait_for_plot(page, "heaping-figure", min_traces=2)
    wait_for_plot(page, "distance-figure", min_traces=3)
    assert_no_plot_annotations(page, "tax-figure", "heaping-figure", "distance-figure")

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
    assert page.evaluate("history.length") == history_size


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
        diagnostics = page.locator("#tab-diagnostics")
        models = page.locator("#tab-models")
        expect(overview).to_have_attribute("aria-selected", "true")
        expect(page.get_by_role("tab")).to_have_count(3)
        wait_for_plot(page, "distribution-figure", min_traces=2)
        # Both models render while their tab is inactive. Wait for this so
        # the check includes the first paint of an already-initialised chart.
        page.wait_for_function(
            """() => [...document.querySelectorAll('#models-panel .js-plotly-plot')]
                .filter(plot => plot._fullData?.length > 1).length === 2""",
            timeout=45_000,
        )
        if mobile:
            models.tap()
        else:
            overview.focus()
            overview.press("End")
            expect(models).to_be_focused()
        expect(models).to_have_attribute("aria-selected", "true")
        wait_for_plot(page, "hedonic-figure", min_traces=2)
        wait_for_plot(page, "clusters-figure", min_traces=2)
        page.set_viewport_size({"width": 320 if width > 320 else 390, "height": 900})
        wait_for_plot(page, "hedonic-figure", min_traces=2)
        wait_for_plot(page, "clusters-figure", min_traces=2)
        assert_no_plot_annotations(page, "hedonic-figure", "clusters-figure")
        page.set_viewport_size(viewport)
        wait_for_plot(page, "hedonic-figure", min_traces=2)

        models.focus()
        models.press("ArrowLeft")
        expect(diagnostics).to_be_focused()
        expect(diagnostics).to_have_attribute("aria-selected", "true")
        expect(page.locator("#age-plot svg")).to_be_visible(timeout=45_000)
        wait_for_plot(page, "distance-figure")
        assert_no_plot_annotations(page, "tax-figure", "heaping-figure", "distance-figure")
        diagnostics.press("Home")
        expect(overview).to_be_focused()
        expect(overview).to_have_attribute("aria-selected", "true")
        wait_for_plot(page, "geo-map")
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
