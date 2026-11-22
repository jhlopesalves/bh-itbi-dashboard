/* Rescale the distance chart's y-axis to fit the currently visible period series. */
(() => {
  function visibleTraces(traces) {
    return traces.filter(trace => trace.visible !== false && trace.visible !== "legendonly");
  }

  function fitVisiblePeriods(graph) {
    // Keep this y-axis range calculation synchronised with distance_figure
    // in bh_itbi/figures/diagnostics.py; step and padding come from the figure.
    const padFraction = graph.layout.meta?.pad_fraction;
    const step = graph.layout.yaxis?.dtick;
    if (!Number.isFinite(padFraction) || !Number.isFinite(step) || step <= 0) return;
    const values = visibleTraces(graph.data || []).flatMap(
      trace => (trace.y || []).filter(Number.isFinite)
    );
    if (!values.length) return;
    const low = Math.min(...values);
    const high = Math.max(...values);
    const pad = padFraction * (high - low);
    const floor = step * Math.floor((low - pad) / step);
    const ceiling = step * Math.ceil((high + pad) / step);
    const range = floor === ceiling ? [floor - step, ceiling + step] : [floor, ceiling];
    const current = graph.layout.yaxis?.range;
    if (current?.[0] === range[0] && current?.[1] === range[1]) return;
    Plotly.relayout(graph, {"yaxis.range": range});
  }

  const mount = new MutationObserver(connect);
  function connect() {
    const graph = document.querySelector("#distance-figure .js-plotly-plot");
    if (!graph?.on || !window.Plotly) return;
    mount.disconnect();
    graph.on("plotly_restyle", () => fitVisiblePeriods(graph));
  }
  mount.observe(document.documentElement, {childList: true, subtree: true});
  connect();
})();
