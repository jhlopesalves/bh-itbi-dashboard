/* The plot uses log coordinates with pixel-sized marks and measured labels. */
(() => {
  const measure = document.createElement("canvas").getContext("2d");
  const tickFormat = new Intl.NumberFormat("pt-BR", {maximumFractionDigits: 6});
  const labelSize = 12;
  const gap = 9;

  function svg(parent, tag, attrs, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }

  function line(parent, x1, y1, x2, y2, cls) {
    return svg(parent, "line", {x1, y1, x2, y2, class: cls});
  }

  function text(parent, x, y, value, cls, anchor = "start") {
    return svg(parent, "text", {x, y, class: cls, "text-anchor": anchor}, value);
  }

  function wrap(label, available) {
    const lines = [];
    let row = "";
    for (const word of label.split(" ")) {
      const next = row ? row + " " + word : word;
      if (row && measure.measureText(next).width > available) {
        lines.push(row);
        row = word;
      } else {
        row = next;
      }
    }
    return [...lines, row];
  }

  function visibleEdges(row) {
    return row.segments.filter(part => !part.hidden && part.start !== part.end)
      .flatMap(part => [part.start, part.end]);
  }

  function chartScale(data, width, left, font) {
    const extent = [0];
    const setbacks = [[0, measure.measureText("referência").width + gap]];
    let topInterval = true;
    let leftGutter = 0;
    let rightGutter = 0;
    for (const row of data.rows) {
      extent.push(row.observed, ...row.segments.flatMap(part => [part.start, part.end]));
      if (!row.reference && (width >= 460 || !row.interval)) {
        const room = measure.measureText(row.observed_label).width + gap;
        if (visibleEdges(row).some(value => value > row.observed)) {
          leftGutter = Math.max(leftGutter, room);
        } else {
          rightGutter = Math.max(rightGutter, room);
        }
      }
      if (row.interval) {
        extent.push(...row.interval);
        measure.font = `700 ${labelSize}px ${font}`;
        setbacks.push([0, measure.measureText(row.adjusted_label).width]);
        measure.font = `${labelSize}px ${font}`;
        if (topInterval) setbacks.push([row.interval[1], 38]);
        topInterval = false;
      }
    }
    const low = Math.min(...extent);
    const high = Math.max(...extent);
    const x0 = left + gap + leftGutter;
    const right = width - gap;
    const room = right - x0;
    let scale = (room - rightGutter) / (high - low || 0.10);
    for (const [at, padding] of setbacks) {
      if (at > low) scale = Math.min(scale, (room - padding) / (at - low));
    }
    const x = value => x0 + (value - low) * scale;
    return {x, low: low - gap / scale, high: low + room / scale};
  }

  function percentTicks({x, low, high}, width, left) {
    const [start, end] = [low, high].map(value => Math.expm1(value) * 100);
    const rawStep = (end - start) / Math.max(2, (width - left) / 48);
    const base = 10 ** Math.floor(Math.log10(rawStep));
    const step = base * [1, 2, 2.5, 5, 10].find(n => n * base >= rawStep);
    const ticks = [];
    for (let i = Math.ceil(start / step); i <= Math.floor(end / step); i++) {
      const percent = i * step;
      const pos = x(Math.log1p(percent / 100));
      const sign = i < 0 ? "−" : i > 0 ? "+" : "";
      const label = sign + tickFormat.format(Math.abs(percent)) + "%";
      const half = measure.measureText(label).width / 2;
      if (pos - half >= left - gap && pos + half <= width) ticks.push({i, pos, label, half});
    }
    // A distant percentage interval compresses in log coordinates. Give zero
    // priority, then keep only ticks whose labels fit next to their neighbours.
    const result = ticks.filter(tick => tick.i === 0);
    for (const tick of ticks) {
      if (result.every(other => Math.abs(tick.pos - other.pos) >= tick.half + other.half + 7)) {
        result.push(tick);
      }
    }
    return result;
  }

  function drawBar(group, row, fills, x, y, topInterval) {
    for (const [i, part] of row.segments.entries()) {
      if (part.hidden || part.start === part.end) continue;
      const start = x(part.start);
      const end = x(part.end);
      const height = part.subtracts ? 5 : 10;
      const rect = svg(group, "rect", {
        x: Math.min(start, end), y: y - height / 2, width: Math.abs(end - start), height,
        fill: fills[part.group], class: part.subtracts ? "age-subtraction" : "age-segment",
        "data-group": part.group, "data-end": end,
      });
      // At narrow scales a full outline can obscure the whole fill. The outline
      // stays outside the rectangle so even the shortest segment keeps its hue.
      if (part.subtracts) rect.setAttribute("paint-order", "stroke");
      else if (i) line(group, start, y - 5, start, y + 5, "age-separator");
    }
    if (!row.interval) return;
    text(group, x(0), y - 11, row.adjusted_label, "age-adjusted");
    const [lower, upper] = row.interval.map(x);
    const centre = y + 13;
    line(group, lower, centre, upper, centre, "age-ci");
    for (const bound of [lower, upper]) line(group, bound, centre - 2.5, bound, centre + 2.5, "age-ci");
    if (topInterval) text(group, upper + 5, centre + 5.5, "IC 95%", "age-ci-label");
  }

  function labelObserved(group, row, x, y, left, width) {
    const marker = x(row.observed);
    const label = row.observed_label;
    const size = measure.measureText(label).width;
    // If a subtraction folds back into the bar, the right-hand label may
    // intersect the preceding segments. The left-hand label clears the stack.
    const edges = visibleEdges(row).map(x);
    const zero = x(0);
    let right = marker + gap;
    let before = Math.min(marker - gap, ...edges.map(value => value - 5));
    if (right < zero + 4 && right + size > zero - 4) right = zero + 4;
    if (before > zero - 4 && before - size < zero + 4) before = zero - 4;
    if (right + size <= width && right >= Math.max(...edges) + 4) {
      text(group, right, y + 4, label, "age-observed");
    } else if (before - size >= left) {
      text(group, before, y + 4, label, "age-observed", "end");
    }
  }

  function bindTooltip(group, fields, tooltip, host) {
    group.setAttribute("aria-label", fields.join(". "));
    function show(clientX, clientY) {
      const parent = host.getBoundingClientRect();
      tooltip.hidden = false;
      const maxX = parent.width - tooltip.offsetWidth;
      tooltip.style.left = `${Math.max(0, Math.min(clientX - parent.left + 10, maxX))}px`;
      const y = clientY - parent.top;
      const below = y + 12;
      tooltip.style.top = `${below + tooltip.offsetHeight <= parent.height
        ? below : Math.max(0, y - tooltip.offsetHeight - 10)}px`;
    }
    function fill() {
      tooltip.replaceChildren(...fields.map((field, i) => {
        const node = document.createElement(i ? "div" : "strong");
        node.textContent = field;
        return node;
      }));
    }
    const enter = event => { fill(); show(event.clientX, event.clientY); };
    const hide = () => { tooltip.hidden = true; };
    group.addEventListener("pointerenter", enter);
    group.addEventListener("pointermove", event => show(event.clientX, event.clientY));
    group.addEventListener("pointerleave", hide);
    group.addEventListener("click", enter);
    group.addEventListener("focus", () => {
      const box = group.getBoundingClientRect();
      fill();
      show(box.left + box.width / 2, box.top + box.height / 2);
    });
    group.addEventListener("blur", hide);
  }

  function appendLegend(host, fills) {
    if (!Object.keys(fills).length) return;
    const list = document.createElement("ul");
    list.className = "age-legend";
    list.setAttribute("aria-label", "Composição");
    for (const [label, fill] of Object.entries(fills)) {
      const item = document.createElement("li");
      const swatch = document.createElement("span");
      swatch.style.backgroundColor = fill;
      item.append(swatch, label);
      list.append(item);
    }
    host.append(list);
  }

  function draw(host, data) {
    const width = host.clientWidth;
    if (!width) return;
    host.replaceChildren();
    if (!data.rows.length) {
      const empty = document.createElement("p");
      empty.className = "comparison-empty";
      empty.textContent = data.empty;
      host.append(empty);
      return;
    }
    const font = getComputedStyle(host).fontFamily;
    measure.font = `${labelSize}px ${font}`;
    const widest = Math.max(...data.rows.map(row => measure.measureText(row.label).width));
    const labelWidth = Math.min(widest + 2, width * 0.29);
    const left = labelWidth + gap;
    const scale = chartScale(data, width, left, font);
    const {x} = scale;
    const rowHeight = 62;
    const first = 29;
    const bottom = first + rowHeight * (data.rows.length - 1) + 25;
    const chart = svg(host, "svg", {
      width, height: bottom + 19, class: "age-svg", role: "group",
      "aria-label": "Diferenças de valor real por faixa de idade da construção",
    });
    for (const {i, pos, label} of percentTicks(scale, width, left)) {
      if (i) line(chart, pos, 8, pos, bottom, "age-grid");
      text(chart, pos, bottom + 15, label, "age-tick", "middle");
    }
    line(chart, x(0), 8, x(0), bottom, "age-zero");
    const tooltip = document.createElement("div");
    tooltip.className = "comparison-tooltip";
    tooltip.setAttribute("aria-hidden", "true");
    tooltip.hidden = true;
    const fills = {...data.fills, Ajustado: data.teal};
    let topInterval = true;
    for (const [i, row] of data.rows.entries()) {
      const y = first + i * rowHeight;
      const group = svg(chart, "g", {class: "age-row", tabindex: 0, role: "img"});
      svg(group, "rect", {x: 0, y: y - 22, width, height: 43, fill: "transparent"});
      const lines = wrap(row.label, labelWidth);
      lines.forEach((value, index) => {
        text(group, labelWidth, y + 4 + 14 * (index - (lines.length - 1) / 2),
          value, "age-band-label", "end");
      });
      drawBar(group, row, fills, x, y, topInterval);
      if (row.interval) topInterval = false;
      svg(group, "circle", {
        cx: x(row.observed), cy: y, r: row.reference ? 3.5 : 5,
        class: row.reference ? "age-reference" : "age-marker",
      });
      labelObserved(group, row, x, y, left, width);
      bindTooltip(group, row.tooltip, tooltip, host);
    }
    appendLegend(host, data.fills);
    host.append(tooltip);
  }

  let host, data, renderedWidth;
  const resize = new ResizeObserver(() => {
    if (host.clientWidth !== renderedWidth) update();
  });
  function update() {
    renderedWidth = host.clientWidth;
    draw(host, data);
  }
  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.ageChart = {
    update(payload) {
      if (!payload) return;
      const target = document.getElementById("age-plot");
      if (host !== target) {
        resize.disconnect();
        host = target;
        resize.observe(host);
      }
      data = payload;
      update();
    },
  };
})();
