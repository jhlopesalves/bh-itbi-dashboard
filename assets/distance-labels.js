/* Use the rendered axis height to place period labels in a responsive gutter. */
(() => {
  const minimumWidth = 420;
  const normalMargin = 22;
  const labelMargin = 88;
  const labelHeight = 19;
  const labelSpacing = labelHeight + 4;

  function visiblePeriods(graph) {
    return graph.data.filter(trace => trace.visible !== false && trace.visible !== "legendonly");
  }

  function endLabels(graph, height) {
    const [low, high] = graph._fullLayout.yaxis.range;
    const ends = visiblePeriods(graph).map(trace => ({
      text: trace.meta,
      value: trace.y.findLast(Number.isFinite),
    })).filter(({value}) => value >= low && value <= high);
    ends.sort((a, b) => b.value - a.value);
    let centre = labelHeight / 2 - labelSpacing;
    const positions = ends.map(({value}) => {
      const target = height * (high - value) / (high - low);
      centre = Math.max(target, centre + labelSpacing);
      return centre;
    });
    // Keep the lowest label inside the axes and preserve order if the
    // forward pass runs out of room at the bottom.
    centre = height - labelHeight / 2 + labelSpacing;
    for (let i = positions.length - 1; i >= 0; i--) {
      centre = Math.min(positions[i], centre - labelSpacing);
      positions[i] = centre;
    }
    return ends.map(({text}, i) => ({
      text,
      x: 1,
      xref: "paper",
      xanchor: "left",
      xshift: 8,
      y: 1 - positions[i] / height,
      yref: "paper",
      yanchor: "middle",
      showarrow: false,
      borderpad: 0,
      font: {size: 11, color: graph.layout.font.color},
    }));
  }

  function syncLabels(graph) {
    // Loading and empty-state figures own their own annotations.
    if (!graph.data?.length || !graph.clientWidth) return;
    const height = graph._fullLayout?.yaxis?._length;
    if (!height) return;
    const labels = graph.clientWidth >= minimumWidth ? endLabels(graph, height) : [];
    const margin = labels.length ? labelMargin : normalMargin;
    const current = graph.layout.annotations || [];
    if (graph.layout.margin.r === margin && current.length === labels.length
        && labels.every((label, i) => label.text === current[i].text
          && Math.abs(label.y - current[i].y) < 1e-6)) return;
    Plotly.relayout(graph, {"margin.r": margin, annotations: labels});
  }

  function fitVisiblePeriods(graph) {
    // Legend toggles use the same 5% padding and tick step as the server figure.
    const values = visiblePeriods(graph).flatMap(trace => trace.y.filter(Number.isFinite));
    if (!values.length) return;
    const low = Math.min(...values);
    const high = Math.max(...values);
    const pad = 0.05 * (high - low);
    const step = graph.layout.yaxis.dtick;
    const floor = step * Math.floor((low - pad) / step);
    const ceiling = step * Math.ceil((high + pad) / step);
    const range = floor === ceiling ? [floor - step, ceiling + step] : [floor, ceiling];
    Plotly.relayout(graph, {"yaxis.range": range});
  }

  const mount = new MutationObserver(connect);
  function connect() {
    const graph = document.querySelector("#distance-figure .js-plotly-plot");
    if (!graph?.on || !window.Plotly) return;
    mount.disconnect();
    let frame;
    const refresh = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => syncLabels(graph));
    };
    graph.on("plotly_afterplot", refresh);
    graph.on("plotly_restyle", () => fitVisiblePeriods(graph));
    new ResizeObserver(refresh).observe(graph);
    refresh();
  }
  mount.observe(document.documentElement, {childList: true, subtree: true});
  connect();
})();
