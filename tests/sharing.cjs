/* Run the production functions with browser primitives and no extra packages. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const config = JSON.parse(fs.readFileSync(0, "utf8"));
let location = new URL("https://example.test/painel?bairros=SAVASSI#conteudo");
const events = {};
const updates = [];
let replacements = 0;
const window = {
  get location() { return location; },
  addEventListener: (event, handler) => { events[event] = handler; },
  history: {
    state: {retained: true},
    replaceState: (state, _, href) => {
      assert.deepEqual(state, {retained: true});
      replacements++;
      location = new URL(href);
    },
    pushState: () => assert.fail("Filters must not add history entries")
  },
  dash_clientside: {
    set_props: (id, value) => updates.push({id, ...value})
  }
};
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, "../assets/sharing.js"), "utf8"),
  {window, URL, URLSearchParams, Set}
);
const sharing = window.dash_clientside.sharing;
const serialise = value => JSON.parse(JSON.stringify(value));

const initial = sharing.observeNavigation();
assert.equal(initial.search, "?bairros=SAVASSI");
sharing.updateUrl(...config.defaults, false, config);
assert.equal(location.search, "?bairros=SAVASSI");
assert.equal(replacements, 0);
const cases = [];
const selections = [
  config.defaults,
  ["apartment", [2020, 2025], ["SAVASSI"], config.defaults[3], config.defaults[4]],
  ["house", [2018, 2024], ["LOURDES", "SAVASSI"], "price_per_m2_brl", "white-bg"],
  ["all", [2022, 2022], ["SÃO JOÃO & D'ÁVILA, A+B/#?"], "value_declared_brl", "white-bg"]
];
for (const controls of selections) {
  sharing.updateUrl(...controls, true, config);
  assert.equal(location.pathname, "/painel");
  assert.equal(location.hash, "#conteudo");
  cases.push({query: location.search, controls});
}
assert.ok(location.search.includes("%C3%83") && location.search.includes("%2B"));
const count = replacements;
sharing.updateUrl(...selections.at(-1), true, config);
assert.equal(replacements, count);
// Revisit the same search after edits: both traversals must restore controls.
location = new URL("https://example.test/painel?bairros=SAVASSI");
events.popstate();
sharing.updateUrl(...config.defaults, true, config);
location = new URL("https://example.test/painel?bairros=SAVASSI");
events.popstate();
assert.deepEqual(serialise(updates), [
  {id: "url-navigation", data: {search: "?bairros=SAVASSI", revision: 1}},
  {id: "url-navigation", data: {search: "?bairros=SAVASSI", revision: 2}}
]);
sharing.updateUrl(...config.defaults, true, config);
assert.equal(location.search, "");
process.stdout.write(JSON.stringify(cases));
