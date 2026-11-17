/* Only browser navigation restores controls. Filter edits replace the current
   history entry without emitting navigation, avoiding a URL/control feedback loop. */
window.dash_clientside = Object.assign({}, window.dash_clientside, {
  sharing: {
    observeNavigation: function() {
      let revision = 0;
      window.addEventListener("popstate", () => {
        // A revision also restores a visited URL equal to the original URL,
        // after filter edits have replaced that entry's query in the meantime.
        window.dash_clientside.set_props("url-navigation", {
          data: {search: window.location.search, revision: ++revision}
        });
      });
      return {search: window.location.search, revision};
    },

    updateUrl: function(type, years, names, metric, style, ready, config) {
      // Initial layout defaults must never overwrite an incoming shared query.
      if (!ready) return;
      const query = new URLSearchParams();
      const defaults = config.defaults;
      [["tipo", type, defaults[0]], ["medida", metric, defaults[3]],
        ["mapa", style, defaults[4]]].forEach(([key, value, fallback]) => {
        if (value !== fallback) {
          const entry = Object.entries(config.options[key]).find(([, v]) => v === value);
          if (entry) query.set(key, entry[0]);
        }
      });
      if (years[0] !== defaults[1][0]) query.set("inicio", years[0]);
      if (years[1] !== defaults[1][1]) query.set("fim", years[1]);
      Array.from(new Set(names || [])).sort().forEach(name => query.append("bairros", name));
      const url = new URL(window.location.href);
      url.search = query.toString();
      if (url.href !== window.location.href) {
        window.history.replaceState(window.history.state, "", url.href);
      }
    }
  }
});
