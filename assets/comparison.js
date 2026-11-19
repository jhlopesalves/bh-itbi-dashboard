/* Each neighbourhood is painted as one SVG group so foreground fills occlude
   the lines and fills of the rows behind them. */
(() => {
  const {bindTooltip, formatNumber, line, measureText, setFont, svg, text, wrap} = window.bhCharts;
  // These browser presentation cut-offs mirror config.py and are checked in test_theme.py.
  const comparisonMinimum = 15;
  const ridgeMinimum = 50;
  const ridgeLimit = 8;
  const ticks = [1000, 1500, 2000, 3000, 4000, 6000, 8000, 12000, 16000, 24000, 32000];
  const labelStep = 13;
  const swatchSize = 8;
  const swatchGap = 4;

  function rowLabels(group, position, row, baseline) {
    const {left, right, showMedian} = position;
    const firstLine = baseline - 4 - labelStep * (row.nameLines.length - 1);
    svg(group, "rect", {
      x: left - 9 - row.firstLineWidth - swatchGap - swatchSize,
      y: firstLine - swatchSize,
      width: swatchSize, height: swatchSize,
      fill: row.colour, class: "comparison-swatch", "aria-hidden": "true",
    });
    row.nameLines.forEach((value, i) => {
      const y = baseline - 4 - labelStep * (row.nameLines.length - 1 - i);
      text(group, left - 9, y, value, "comparison-row-name", "end");
    });
    row.countLines.forEach((value, i) => {
      text(group, left - 9, baseline + 9 + labelStep * i, value, "comparison-muted", "end");
    });
    if (showMedian) {
      text(group, right + 9, baseline - 4, formatNumber(row.quantiles[2]), "comparison-median-value");
      text(group, right + 9, baseline + 9, "mediana", "comparison-muted");
    }
  }

  function drawReference(svgNode, cityMedian, position, end) {
    if (cityMedian === null) return;
    const {x, left, right, width} = position;
    const value = x(cityMedian);
    const inside = value >= left && value <= right;
    const label = "mediana da cidade  " + formatNumber(cityMedian);
    const display = value < left ? "← " + label : value > right ? label + " →" : label;
    const swatchWidth = 14;
    const half = (measureText(display) + swatchWidth + swatchGap) / 2 + 5;
    const centre = Math.max(half, Math.min(width - half, Math.max(left, Math.min(right, value))));
    const reference = svg(svgNode, "g", {class: "comparison-city"});
    if (inside) line(reference, value, 23, value, end, "comparison-city-line");
    const start = centre - half + 5;
    text(reference, start + swatchWidth + swatchGap, 14, display, "comparison-city-label");
    line(reference, start, 10, start + swatchWidth, 10, "comparison-city-line", {"aria-hidden": "true"});
  }

  function drawRidge(group, row, x, baseline, scale, index) {
    const {prices, density, quantiles: [, p25, median, p75]} = row;
    const curve = prices.map((price, i) => `${x(price)} ${baseline - scale * density[i]}`).join("L");
    const left = x(prices[0]);
    const right = x(prices.at(-1));
    const area = `M${left} ${baseline}L${curve}L${right} ${baseline}Z`;
    const clipId = `comparison-ridge-${index}`;
    const defs = svg(group, "defs");
    const clip = svg(defs, "clipPath", {id: clipId});
    svg(clip, "path", {d: area});
    svg(group, "path", {d: area, fill: row.outer_fill, class: "comparison-ridge-fill"});
    const clipPath = `url(#${clipId})`;
    svg(group, "rect", {
      x: x(p25), y: 0, width: x(p75) - x(p25), height: baseline,
      fill: row.iqr_fill, class: "comparison-iqr-fill", "clip-path": clipPath,
    });
    const after = prices.findIndex(price => price >= median);
    if (after >= 0 && median >= prices[0]) {
      const before = Math.max(0, after - 1);
      const medianX = x(median);
      const fraction = after === before ? 0 : (medianX - x(prices[before])) / (x(prices[after]) - x(prices[before]));
      const height = density[before] + fraction * (density[after] - density[before]);
      line(group, medianX, baseline - scale * height, medianX, baseline, "comparison-ridge-median", {
        "clip-path": clipPath, "pointer-events": "none",
      });
    }
    svg(group, "path", {d: `M${curve}`, stroke: row.colour, class: "comparison-ridge-outline"});
    line(group, left, baseline, right, baseline, "comparison-baseline", {stroke: row.colour});
  }

  function drawInterval(group, row, x, baseline) {
    const [p10, p25, median, p75, p90] = row.quantiles.map(x);
    line(group, p10, baseline, p90, baseline, "comparison-interval-hit");
    line(group, p10, baseline, p90, baseline, "comparison-interval-range", {stroke: row.outer_fill});
    line(group, p25, baseline, p75, baseline, "comparison-interval-iqr", {stroke: row.iqr_fill});
    svg(group, "circle", {
      cx: median, cy: baseline, r: 4.5, fill: row.colour, class: "comparison-interval-median",
    });
  }

  function addTooltip(group, row, tooltip, host) {
    const currencyLine = (label, value) => `${label}: R$ ${formatNumber(value)}/m²`;
    const fields = [
      row.name, `Transações: ${formatNumber(row.n)}`,
      ...["P10", "P25", "Mediana", "P75", "P90"].map(
        (label, i) => currencyLine(label, row.quantiles[i])
      ),
    ];
    bindTooltip(group, fields, tooltip, host, {useOffsetHeight: true});
  }

  function draw(host, data) {
    const width = host.clientWidth;
    if (!width) return;
    host.replaceChildren();
    host.parentElement.classList.toggle("comparison-scroll-active", data.rows.length > ridgeLimit);
    if (!data.rows.length) {
      const empty = document.createElement("p");
      empty.className = "comparison-empty";
      empty.textContent = `São necessárias ${comparisonMinimum} transações por bairro. Amplie o recorte.`;
      host.append(empty);
      return;
    }

    const font = getComputedStyle(host).fontFamily;
    setFont(`12px ${font}`);
    const limit = Math.min(width * 0.36, 145);
    const swatchSpace = swatchSize + swatchGap;
    const rows = data.rows.map(row => {
      const nameLines = wrap(row.name, limit - swatchSpace);
      return {
        ...row, nameLines,
        firstLineWidth: measureText(nameLines[0]),
        countLines: wrap(`n = ${formatNumber(row.n)}${row.n < ridgeMinimum ? ` (n < ${ridgeMinimum}: resumo)` : ""}`, limit),
      };
    });
    const labelWidth = Math.max(...rows.flatMap(row =>
      [row.firstLineWidth + swatchSpace, ...[...row.nameLines, ...row.countLines].map(measureText)]
    ));
    setFont(`11px ${font}`);
    const showMedian = width >= 420;
    const left = Math.ceil(labelWidth) + 11;
    const right = width - (showMedian ? 59 : 9);
    const lo = Math.log(Math.min(...rows.map(row => row.prices[0] ?? row.quantiles[0])));
    const hi = Math.log(Math.max(...rows.map(row => row.prices.at(-1) ?? row.quantiles[4])));
    const padding = 0.03 * (hi - lo || 1);
    const x = value => left + (right - left) * (Math.log(value) - lo + padding) / (hi - lo + 2 * padding);
    const position = {x, width, left, right, showMedian};

    const maxNameLines = Math.max(...rows.map(row => row.nameLines.length));
    const maxCountLines = Math.max(...rows.map(row => row.countLines.length));
    const ridges = rows.filter(row => row.density.length);
    const spacing = Math.max(
      ridges.length ? Math.max(39, Math.min(115, 285 / (rows.length + 0.8))) : 29,
      labelStep * (maxNameLines + maxCountLines) + 4,
    );
    const maxPeak = ridges.length ? Math.max(...ridges.map(row => Math.max(...row.density))) : 0;
    const scale = maxPeak ? 1.55 * spacing / maxPeak : 0;
    const firstBaseline = 26 + Math.max(scale * maxPeak, labelStep * (maxNameLines - 1) + 17);
    const end = firstBaseline + spacing * (rows.length - 1) + labelStep * rows.at(-1).countLines.length + 4;
    const plot = svg(host, "svg", {
      class: "comparison-svg", width, height: end + 24, role: "group",
      "aria-label": "Distribuição do preço por m² por bairro",
    });
    let tickEnd = -Infinity;
    for (const value of ticks) {
      const px = x(value);
      if (px < left || px > right) continue;
      line(plot, px, 23, px, end, "comparison-grid-line");
      const label = formatNumber(value);
      const half = measureText(label) / 2;
      if (px - half < tickEnd + 4) continue;
      text(plot, px, end + 17, label, "comparison-muted", "middle");
      tickEnd = px + half;
    }
    drawReference(plot, data.city_median, position, end);

    const tooltip = document.createElement("div");
    tooltip.className = "comparison-tooltip";
    tooltip.hidden = true;
    tooltip.setAttribute("aria-hidden", "true");
    rows.forEach((row, index) => {
      const baseline = firstBaseline + index * spacing;
      const group = svg(plot, "g", {
        class: "comparison-row", "data-neighbourhood": row.name, tabindex: 0, role: "img",
      });
      if (row.density.length) drawRidge(group, row, x, baseline, scale, index);
      else drawInterval(group, row, x, baseline);
      rowLabels(group, position, row, baseline);
      addTooltip(group, row, tooltip, host);
    });
    const axis = document.createElement("p");
    axis.className = "comparison-axis";
    axis.textContent = data.axis_title;
    host.append(axis, tooltip);
  }

  let host, data, viewportWidth;
  const resize = new ResizeObserver(() => {
    if (data && host.clientWidth !== viewportWidth) updatePlot();
  });

  function updatePlot() {
    viewportWidth = host.clientWidth;
    draw(host, data);
  }

  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.comparison = {
    update(payload) {
      if (!payload) return;
      const target = document.getElementById("comparison-plot");
      if (host !== target) {
        resize.disconnect();
        host = target;
        resize.observe(host);
      }
      data = payload;
      updatePlot();
    },
  };
})();
