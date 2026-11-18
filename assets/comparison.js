/* Each neighbourhood is painted as one SVG group so foreground fills occlude
   the lines and fills of the rows behind them. */
(() => {
  const currency = new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 0, roundingMode: "halfEven"});
  const ticks = [1000, 1500, 2000, 3000, 4000, 6000, 8000, 12000, 16000, 24000, 32000];
  const measure = document.createElement("canvas").getContext("2d");

  function svg(parent, tag, attrs = {}, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }

  function line(parent, x1, y1, x2, y2, className, attrs = {}) {
    return svg(parent, "line", {x1, y1, x2, y2, class: className, ...attrs});
  }

  function wrap(text, limit) {
    const lines = [""];
    for (const word of text.split(" ")) {
      const last = lines.at(-1);
      if (last && measure.measureText(`${last} ${word}`).width > limit) lines.push("");
      for (const character of (lines.at(-1) ? " " : "") + word) {
        if (measure.measureText(lines.at(-1) + character).width > limit) lines.push("");
        lines[lines.length - 1] += character;
      }
    }
    return lines;
  }

  const labelStep = 13;

  function rowLabels(group, position, row, baseline) {
    const {left, right, showMedian} = position;
    row.nameLines.forEach((text, i) => {
      const y = baseline - 4 - labelStep * (row.nameLines.length - 1 - i);
      svg(group, "text", {
        x: left - 9, y, "text-anchor": "end", class: "comparison-row-name",
      }, text);
    });
    row.countLines.forEach((text, i) => svg(group, "text", {
      x: left - 9, y: baseline + 9 + labelStep * i, "text-anchor": "end", class: "comparison-muted",
    }, text));
    if (showMedian) {
      svg(group, "text", {x: right + 9, y: baseline - 4, class: "comparison-median-value"},
        currency.format(row.quantiles[2]));
      svg(group, "text", {x: right + 9, y: baseline + 9, class: "comparison-muted"}, "mediana");
    }
  }

  function drawReference(svgNode, cityMedian, position, end) {
    if (cityMedian === null) return;
    const {x, left, right, width} = position;
    const value = x(cityMedian);
    const inside = value >= left && value <= right;
    const label = "mediana da cidade  " + currency.format(cityMedian);
    const text = value < left ? "← " + label : value > right ? label + " →" : label;
    const half = measure.measureText(text).width / 2 + 5;
    const centre = Math.max(half, Math.min(width - half, Math.max(left, Math.min(right, value))));
    const reference = svg(svgNode, "g", {class: "comparison-city"});
    if (inside) line(reference, value, 23, value, end, "comparison-city-line");
    svg(reference, "text", {
      x: centre, y: 14, "text-anchor": "middle", class: "comparison-city-label",
    }, text);
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
    svg(group, "path", {d: area, class: "comparison-ridge-fill"});
    const clipPath = `url(#${clipId})`;
    svg(group, "rect", {
      x: x(p25), y: 0, width: x(p75) - x(p25), height: baseline,
      class: "comparison-iqr-fill", "clip-path": clipPath,
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
    svg(group, "path", {d: `M${curve}`, class: "comparison-ridge-outline"});
    line(group, left, baseline, right, baseline, "comparison-baseline");
  }

  function drawInterval(group, row, x, baseline) {
    const [p10, p25, median, p75, p90] = row.quantiles.map(x);
    line(group, p10, baseline, p90, baseline, "comparison-interval-hit");
    line(group, p10, baseline, p90, baseline, "comparison-interval-range");
    line(group, p25, baseline, p75, baseline, "comparison-interval-iqr");
    svg(group, "circle", {cx: median, cy: baseline, r: 4.5, class: "comparison-interval-median"});
  }

  function addTooltip(group, row, tooltip, host) {
    const currencyLine = (label, value) => `${label}: R$ ${currency.format(value)}/m²`;
    const fields = [
      row.name, `Transações: ${currency.format(row.n)}`,
      ...["P10", "P25", "Mediana", "P75", "P90"].map(
        (label, i) => currencyLine(label, row.quantiles[i])
      ),
    ];
    group.setAttribute("aria-label", fields.join(". "));

    const show = (clientX, clientY) => {
      const box = host.getBoundingClientRect();
      tooltip.hidden = false;
      tooltip.style.left = `${Math.max(0, Math.min(clientX - box.left + 10, box.width - tooltip.offsetWidth))}px`;
      const y = clientY - box.top;
      const below = y + 12;
      tooltip.style.top = `${below + tooltip.offsetHeight > host.offsetHeight
        ? Math.max(0, y - tooltip.offsetHeight - 10)
        : below}px`;
    };
    const fill = () => {
      tooltip.replaceChildren(...fields.map((field, i) => {
        const node = document.createElement(i ? "div" : "strong");
        node.textContent = field;
        return node;
      }));
    };
    const enter = event => { fill(); show(event.clientX, event.clientY); };
    group.addEventListener("pointerenter", enter);
    group.addEventListener("pointermove", event => show(event.clientX, event.clientY));
    group.addEventListener("pointerleave", () => { tooltip.hidden = true; });
    group.addEventListener("click", enter);
    group.addEventListener("focus", () => {
      const box = group.getBoundingClientRect();
      fill();
      show(box.left + box.width / 2, box.top + box.height / 2);
    });
    group.addEventListener("blur", () => { tooltip.hidden = true; });
  }

  function draw(host, data) {
    const width = host.clientWidth;
    if (!width) return;
    host.replaceChildren();
    host.parentElement.classList.toggle("comparison-scroll-active", data.rows.length > 8);
    if (!data.rows.length) {
      const empty = document.createElement("p");
      empty.className = "comparison-empty";
      empty.textContent = "São necessárias 15 transações por bairro. Amplie o recorte.";
      host.append(empty);
      return;
    }

    const font = getComputedStyle(host).fontFamily;
    measure.font = `12px ${font}`;
    const limit = Math.min(width * 0.36, 145);
    const rows = data.rows.map(row => ({
      ...row,
      nameLines: wrap(row.name, limit),
      countLines: wrap(`n = ${currency.format(row.n)}${row.n < 50 ? " (n < 50: resumo)" : ""}`, limit),
    }));
    const labelWidth = Math.max(...rows.flatMap(row =>
      [...row.nameLines, ...row.countLines].map(label => measure.measureText(label).width)
    ));
    measure.font = `11px ${font}`;
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
      const label = currency.format(value);
      const half = measure.measureText(label).width / 2;
      if (px - half < tickEnd + 4) continue;
      svg(plot, "text", {x: px, y: end + 17, "text-anchor": "middle", class: "comparison-muted"}, label);
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
