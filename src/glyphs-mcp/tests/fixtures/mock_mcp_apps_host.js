"use strict";

const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync(process.argv[2], "utf8");
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) throw new Error("Feedback UI script was not found");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

class Element {
  constructor() {
    this.dataset = {};
    this.listeners = {};
    this.buttons = [];
    this.attributes = {};
    this._innerHTML = "";
    this.textContent = "";
  }
  set innerHTML(value) {
    this._innerHTML = value;
    this.buttons = Array.from(value.matchAll(/<button([^>]*)data-action="(\d+)"([^>]*)>/g)).map((match) => {
      const button = new Element();
      button.dataset.action = match[2];
      button.disabled = /disabled/.test(match[1] + match[3]);
      return button;
    });
  }
  get innerHTML() { return this._innerHTML; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) { return selector === "[data-action]" ? this.buttons : []; }
  remove() {}
}

function createHost({ respondInitialize = true } = {}) {
  const app = new Element();
  const announcer = new Element();
  const rootStyle = { setProperty(name, value) { this[name] = value; } };
  const document = {
    documentElement: { style: rootStyle },
    getElementById(id) { return id === "app" ? app : id === "announcer" ? announcer : null; },
    addEventListener() {},
  };
  const listeners = {};
  const calls = [];
  const timers = new Map();
  let timerId = 0;
  const parent = {
    postMessage(message) {
      calls.push(message);
      if (message.method === "ui/initialize" && respondInitialize) {
        queueMicrotask(() => dispatch({ jsonrpc: "2.0", id: message.id, result: { hostContext: { theme: "dark" } } }));
      }
      if (message.method === "tools/call") {
        queueMicrotask(() => dispatch({
          jsonrpc: "2.0",
          id: message.id,
          result: { structuredContent: card("result", "success", "Completed", "The host tool call completed.") },
        }));
      }
    },
  };
  function dispatch(data) {
    if (listeners.message) listeners.message({ source: parent, data });
  }
  const window = {
    parent,
    location: { reloadCalled: false, reload() { this.reloadCalled = true; } },
    addEventListener(name, callback) { listeners[name] = callback; },
    setTimeout(callback, delay) { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  const context = { window, document, console, Map, Object, Array, String, Number, Promise, queueMicrotask };
  vm.runInNewContext(scriptMatch[1], context, { filename: "feedback_ui_v1.html" });
  return { app, announcer, calls, dispatch, document, timers, window };
}

function card(kind, status, title, summary, extra = {}) {
  return Object.assign({
    schemaVersion: "1.0", kind, status, title, summary,
    target: {}, items: [], warnings: [], actions: [], progress: {}, result: {},
  }, extra);
}

function tick() { return new Promise((resolve) => setImmediate(resolve)); }

(async () => {
  const host = createHost();
  await tick();
  assert(host.calls.some((message) => message.method === "ui/initialize"), "ui/initialize was not sent");
  assert(host.calls.some((message) => message.method === "ui/notifications/initialized"), "initialized notification was not sent");
  assert(host.document.documentElement.style.colorScheme === "dark", "initial host theme was not applied");

  host.dispatch({ method: "ui/notifications/tool-input", params: { arguments: { font_index: 0 } } });
  assert(host.app.innerHTML.includes("Preparing Glyphs feedback"), "tool input did not render preparing progress");

  host.dispatch({ method: "ui/notifications/host-context-changed", params: { hostContext: { theme: "light", cssVariables: { "--color-accent": "#006c3d" } } } });
  assert(host.document.documentElement.style.colorScheme === "light", "theme change was not applied");
  assert(host.document.documentElement.style["--color-accent"] === "#006c3d", "host CSS variable was not applied");

  const preview = card("dry_run", "ready", "Spacing dry run", "One change ready.", {
    items: [{ label: "A", value: "ready" }],
    actions: [
      { label: "Apply in Glyphs", tool: "apply_feedback_plan", arguments: { plan_id: "opaque", confirm: true }, requiresConfirmation: true, destructive: true },
      { label: "Dry Run Again", tool: "preview_spacing_feedback", arguments: {} },
    ],
  });
  host.dispatch({ method: "ui/notifications/tool-result", params: { structuredContent: preview } });
  assert(host.app.buttons.length === 2, "preview did not limit itself to two actions");
  host.app.buttons[0].listeners.click();
  assert(host.app.innerHTML.includes("Review before applying"), "apply did not enter confirmation state");
  assert(host.app.buttons.length === 2, "confirmation did not retain Apply and Cancel");
  host.app.buttons[1].listeners.click();
  assert(host.app.attributes["aria-busy"] === "true", "tool call did not enter working state");
  assert(host.app.buttons.every((button) => button.disabled), "actions were not disabled while the call was running");
  await tick();
  assert(host.calls.some((message) => message.method === "tools/call"), "tools/call was not sent");
  assert(host.app.innerHTML.includes("Completed"), "tool result was not rendered");

  const retry = card("error", "error", "Read failed", "Try again.", {
    error: { code: "validation_failed", message: "Try again.", recoverable: true, nextAction: "Refresh." },
    actions: [{ label: "Retry", tool: "show_glyphs_status", arguments: {} }],
  });
  host.dispatch({ method: "ui/notifications/tool-result", params: { structuredContent: retry } });
  host.app.buttons[0].listeners.click();
  await tick();
  assert(host.calls.filter((message) => message.method === "tools/call").length === 2, "retry did not invoke tools/call");

  for (const code of ["no_font_open", "target_not_found", "validation_failed", "plan_expired", "stale_plan", "apply_failed", "partial_failure", "open_in_glyphs_failed"]) {
    host.dispatch({ method: "ui/notifications/tool-result", params: { structuredContent: card("error", "error", "Error", "Safe feedback.", { error: { code, message: "Safe feedback.", recoverable: true, nextAction: "Refresh." } }) } });
    assert(host.app.innerHTML.includes(code), `error card ${code} was not rendered`);
  }

  const unavailable = createHost({ respondInitialize: false });
  const timeout = Array.from(unavailable.timers.values()).find((timer) => timer.delay === 5000);
  assert(timeout, "five-second bridge timeout was not registered");
  timeout.callback();
  assert(unavailable.app.innerHTML.includes("bridge_unavailable"), "bridge timeout error was not rendered");
  assert(unavailable.app.buttons.length === 1, "bridge timeout did not expose one retry action");
  unavailable.app.buttons[0].listeners.click();
  assert(unavailable.window.location.reloadCalled, "bridge retry did not reload the panel");
})();
