(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.KfpsTransformInputs = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ scene, edits, view, parse, round, document, window }) {
    const listeners = new AbortController();
    let drag = null, disposed = false;
    const on = (target, event, callback, capture = false) => target.addEventListener(event, callback, { capture, signal: listeners.signal });
    const present = callback => {
      try { return callback(); } catch (error) { try { view.error(error); } catch (_) {} }
    };
    const valid = state => state.generation === scene.generation() && scene.contains(state.object);
    function finishDrag(cancel) {
      if (!drag) return;
      const current = drag;
      drag = null;
      try {
        if (valid(current)) {
          if (cancel) scene.restore(current.object, current.shape);
          else edits.commit(current.object);
          present(view.syncMasks);
          present(view.refresh);
          present(view.render);
        }
      } finally {
        if (current.label.hasPointerCapture(current.pointerId)) current.label.releasePointerCapture(current.pointerId);
      }
    }
    for (const id of ["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput"]) {
      const input = view.element(id);
      let owner = null, original = "", generation = -1;
      on(input, "focus", () => { owner = scene.selected(); original = input.value; generation = scene.generation(); });
      const commit = () => {
        if (!disposed && generation === scene.generation() && owner && scene.selected() === owner && input.value !== original) {
          if (edits.apply()) original = input.value;
        }
      };
      on(input, "blur", () => present(commit));
      on(input, "keydown", event => {
        if (event.isComposing || event.keyCode === 229) return;
        if (event.key === "Enter") { event.preventDefault(); if (!event.repeat) present(commit); }
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); present(view.refresh); original = input.value; }
        if (["ArrowUp", "ArrowDown"].includes(event.key)) {
          event.preventDefault();
          try {
            input.value = round(parse(input.value) + (event.key === "ArrowUp" ? 1 : -1) * Number(input.dataset.step) * (event.shiftKey ? 10 : event.altKey ? 0.1 : 1));
            commit();
          } catch (error) { input.setAttribute("aria-invalid", "true"); present(() => view.invalid(error)); }
        }
      });
    }
    for (const label of document.querySelectorAll("[data-numeric-for]")) {
      on(label, "pointerdown", event => {
        const input = view.element(label.dataset.numericFor), object = scene.selected();
        if (event.button !== 0 || input.disabled || object?.kloudy?.locked || !object) return;
        event.preventDefault();
        present(() => finishDrag(true));
        document.activeElement?.blur();
        edits.flushNudge();
        view.refresh();
        drag = { label, pointerId: event.pointerId, input, object, generation: scene.generation(),
          shape: scene.snapshot(object), x: event.clientX, value: Number(input.value) };
        label.setPointerCapture(event.pointerId);
      });
      on(label, "pointermove", event => {
        if (!drag || drag.label !== label || drag.pointerId !== event.pointerId) return;
        if (!valid(drag) || scene.selected() !== drag.object) { present(() => finishDrag(true)); return; }
        drag.input.value = round(drag.value + (event.clientX - drag.x) * Number(drag.input.dataset.step) * (event.shiftKey ? 10 : event.altKey ? 0.1 : 1));
        present(() => edits.apply({ preview: true }));
      });
      on(label, "pointerup", event => { if (drag?.pointerId === event.pointerId) present(() => finishDrag(false)); });
      on(label, "pointercancel", event => { if (drag?.pointerId === event.pointerId) present(() => finishDrag(true)); });
      on(label, "lostpointercapture", event => { if (drag?.pointerId === event.pointerId) present(() => finishDrag(true)); });
    }
    on(window, "blur", () => present(() => finishDrag(true)));
    on(window, "keydown", event => {
      if (event.isComposing || event.keyCode === 229 || !drag) return;
      if (event.key === "Escape") present(() => finishDrag(true));
      event.preventDefault(); event.stopImmediatePropagation();
    }, true);
    return {
      cancel() { finishDrag(true); },
      dispose() {
        if (disposed) return;
        disposed = true;
        try { finishDrag(true); } finally { listeners.abort(); }
      },
      get active() { return Boolean(drag); },
    };
  }
  return { create };
});
