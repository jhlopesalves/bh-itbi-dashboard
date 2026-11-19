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

        resized = {"width": 320 if width > 320 else 390, "height": 900}
        page.set_viewport_size(resized)
        wait_for_plot(page, "hedonic-figure", min_traces=2)
        wait_for_plot(page, "clusters-figure", min_traces=2)
        page.set_viewport_size(viewport)
        wait_for_plot(page, "hedonic-figure", min_traces=2)

        models.focus()
        models.press("ArrowLeft")
        expect(diagnostics).to_be_focused()
        expect(diagnostics).to_have_attribute("aria-selected", "true")
        expect(page.locator("#age-plot svg")).to_be_visible(timeout=45_000)
        wait_for_plot(page, "distance-figure")
        diagnostics.press("Home")
        expect(overview).to_be_focused()
        expect(overview).to_have_attribute("aria-selected", "true")
        wait_for_plot(page, "geo-map")
        assert page.evaluate("window.widthExcursions") == {}, page.evaluate(
            "window.widthExcursions"
        )
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
