/* Native buttons retain keyboard activation; arrow keys provide tab navigation. */
document.addEventListener("keydown", (event) => {
  if (!event.target.matches(".view-tab")) return;
  const tabs = Array.from(event.target.parentElement.querySelectorAll(".view-tab"));
  const index = tabs.indexOf(event.target);
  let next;
  if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
  else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else return;
  event.preventDefault();
  tabs[next].focus();
  tabs[next].click();
});

/* Dash 4's slider exposes no label props for its two generated handles. */
const localiseHandles = () => {
  const handles = document.querySelectorAll("#year-range [role=slider]");
  handles.forEach((handle, index) => {
    const label = index === 0 ? "Ano inicial" : "Ano final";
    if (handle.getAttribute("aria-label") !== label) handle.setAttribute("aria-label", label);
  });
  document.querySelectorAll("#geo-map canvas[role=region]").forEach((canvas) => {
    if (canvas.getAttribute("aria-label") !== "Mapa de valores declarados") {
      canvas.setAttribute("aria-label", "Mapa de valores declarados");
    }
  });
};
const observer = new MutationObserver(localiseHandles);
observer.observe(document.documentElement, {childList: true, subtree: true});
localiseHandles();
