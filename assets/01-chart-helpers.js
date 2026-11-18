/* Shared SVG DOM constructors, canvas text measurement, wrapping and tooltips. */
(() => {
  const measure = document.createElement("canvas").getContext("2d");
  const formatters = new Map();

  function formatNumber(value, maximumFractionDigits = 0, roundingMode = "halfEven") {
    const key = `${maximumFractionDigits}:${roundingMode}`;
    if (!formatters.has(key)) {
      formatters.set(
        key,
        new Intl.NumberFormat("pt-BR", {maximumFractionDigits, roundingMode}),
      );
    }
    return formatters.get(key).format(value);
  }

  function setFont(font) {
    measure.font = font;
  }

  function measureText(value) {
    return measure.measureText(value).width;
  }

  function svg(parent, tag, attrs = {}, textContent) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (textContent !== undefined) node.textContent = textContent;
    parent.append(node);
    return node;
  }

  function line(parent, x1, y1, x2, y2, className, attrs = {}) {
    return svg(parent, "line", {x1, y1, x2, y2, class: className, ...attrs});
  }

  function text(parent, x, y, value, className, anchor = "start") {
    return svg(parent, "text", {x, y, class: className, "text-anchor": anchor}, value);
  }

  function wrap(label, limit) {
    const lines = [""];
    for (const word of label.split(" ")) {
      const last = lines.at(-1);
      if (last && measure.measureText(`${last} ${word}`).width > limit) lines.push("");
      for (const character of (lines.at(-1) ? " " : "") + word) {
        if (measure.measureText(lines.at(-1) + character).width > limit) lines.push("");
        lines[lines.length - 1] += character;
      }
    }
    return lines;
  }

  function bindTooltip(group, fields, tooltip, host, {useOffsetHeight = false} = {}) {
    group.setAttribute("aria-label", fields.join(". "));
    function position(clientX, clientY) {
      const box = host.getBoundingClientRect();
      tooltip.hidden = false;
      const x = clientX - box.left;
      const maxX = box.width - tooltip.offsetWidth;
      tooltip.style.left = `${Math.max(0, Math.min(x + 10, maxX))}px`;
      const y = clientY - box.top;
      const below = y + 12;
      // The comparison plot uses its integer layout height. The age plot
      // positions within the rendered rectangle, which may be fractional.
      const height = useOffsetHeight ? host.offsetHeight : box.height;
      tooltip.style.top = `${below + tooltip.offsetHeight <= height
        ? below : Math.max(0, y - tooltip.offsetHeight - 10)}px`;
    }
    function show(clientX, clientY) {
      tooltip.replaceChildren(...fields.map((field, i) => {
        const node = document.createElement(i ? "div" : "strong");
        node.textContent = field;
        return node;
      }));
      position(clientX, clientY);
    }
    const enter = event => show(event.clientX, event.clientY);
    const hide = () => { tooltip.hidden = true; };
    group.addEventListener("pointerenter", enter);
    group.addEventListener("pointermove", event => position(event.clientX, event.clientY));
    group.addEventListener("pointerleave", hide);
    group.addEventListener("click", enter);
    group.addEventListener("focus", () => {
      const box = group.getBoundingClientRect();
      show(box.left + box.width / 2, box.top + box.height / 2);
    });
    group.addEventListener("blur", hide);
  }

  window.bhCharts = {
    bindTooltip,
    formatNumber,
    line,
    measureText,
    setFont,
    svg,
    text,
    wrap,
  };
})();
