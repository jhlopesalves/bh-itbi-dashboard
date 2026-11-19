/* Shared Plotly end labels. Keep the asset URL used by the distance chart. */
(() => {
  const minimumWidth = 420;
  const normalMargin = 22;
  const distanceMargin = 88;
  const labelHeight = 19;
  const labelSpacing = labelHeight + 4;

  function visibleTraces(traces) {
    return traces.filter(trace => trace.visible !== false && trace.visible !== "legendonly");
  }

  function labelEnds(graph, [low, high], height, distance) {
    // Full data decodes Plotly's binary arrays. Distance already sends arrays
    // and keeps its original preformatted label strings.
    const ends = visibleTraces(distance ? graph.data : graph._fullData).flatMap(trace => {
      const meta = trace.meta;
      if (!meta) return [];
      const value = trace.y.findLast(Number.isFinite);
      if (!(value >= low && value <= high)) return [];
      return [{
        value, name: trace.name,
        text: distance ? meta : meta.text,
        colour: meta.colour,
      }];
    }).sort((a, b) => b.value - a.value);
    if (distance || ends.length * labelHeight <= height) return ends;
    // A dense, slate-only selection already identifies each line in its legend.
    return ends.filter(end => end.colour);
  }

  function placeLabels(graph, ends, [low, high], height, distance) {
    const spacing = distance ? labelSpacing
      : Math.min(labelSpacing, (height - labelHeight) / Math.max(1, ends.length - 1));
    let centre = labelHeight / 2 - spacing;
    const positions = ends.map(({value}) => {
      const target = height * (high - value) / (high - low);
      centre = Math.max(target, centre + spacing);
      return centre;
    });
    // Keep the lowest label inside the axes and preserve order if the
    // forward pass runs out of room at the bottom.
    centre = height - labelHeight / 2 + spacing;
    for (let i = positions.length - 1; i >= 0; i--) {
      centre = Math.min(positions[i], centre - spacing);
      positions[i] = centre;
    }
    return ends.map(({text, colour}, i) => ({
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
      font: {size: 11, color: colour || graph.layout.font.color},
    }));
  }

  function rightMargin(graph, ends, distance) {
    if (!ends.length) return normalMargin;
    if (distance) return distanceMargin;
    const {measureText, setFont} = window.bhCharts;
    setFont(`11px ${graph.layout.font.family}`);
    const width = Math.max(...ends.map(({name}) => measureText(name)));
    return Math.max(distanceMargin, Math.ceil(width + 28));
  }

  function syncLabels(graph) {
    // Loading and empty-state figures own their own annotations.
    if (!graph.data?.length || !graph.clientWidth) return;
    const meta = graph.layout.meta;
    const distance = Number.isFinite(meta?.pad_fraction);
    if (!distance && !meta?.end_labels) return;
    const axis = graph._fullLayout?.yaxis;
    const height = axis?._length;
    if (!height) return;
    const ends = graph.clientWidth >= minimumWidth
      ? labelEnds(graph, axis.range, height, distance) : [];
    const labels = placeLabels(graph, ends, axis.range, height, distance);
    const margin = rightMargin(graph, ends, distance);
    const current = graph.layout.annotations || [];
    if (graph.layout.margin.r === margin && current.length === labels.length
        && labels.every((label, i) => label.text === current[i].text
          && label.font.color === current[i].font.color
          && Math.abs(label.y - current[i].y) < 1e-6)) return;
    Plotly.relayout(graph, {"margin.r": margin, annotations: labels});
  }

  function fitVisiblePeriods(graph) {
    // Keep this y-axis range calculation synchronised with distance_figure
    // in bh_itbi/figures/diagnostics.py; step and padding come from the figure.
    const padFraction = graph.layout.meta?.pad_fraction;
    if (!Number.isFinite(padFraction)) return;
    const values = visibleTraces(graph.data).flatMap(trace => trace.y.filter(Number.isFinite));
    if (!values.length) return;
    const low = Math.min(...values);
    const high = Math.max(...values);
    const pad = padFraction * (high - low);
    const step = graph.layout.yaxis.dtick;
    const floor = step * Math.floor((low - pad) / step);
    const ceiling = step * Math.ceil((high + pad) / step);
    const range = floor === ceiling ? [floor - step, ceiling + step] : [floor, ceiling];
    Plotly.relayout(graph, {"yaxis.range": range});
  }

  function observeGraph(graph) {
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

  const pending = new Set(["distance-figure", "neighbourhood-figure", "trend-figure", "tax-figure"]);
  const mount = new MutationObserver(connect);
  function connect() {
    if (!window.Plotly) return;
    for (const id of pending) {
      const graph = document.querySelector(`#${id} .js-plotly-plot`);
      if (!graph?.on) continue;
      observeGraph(graph);
      pending.delete(id);
    }
    if (!pending.size) mount.disconnect();
  }
  mount.observe(document.documentElement, {childList: true, subtree: true});
  connect();
})();
