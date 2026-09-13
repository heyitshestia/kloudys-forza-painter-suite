(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorHistory = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function equal(left, right) {
    return Boolean(left && right && Array.isArray(left.shapes) && Array.isArray(right.shapes)
      && left.shapes.length === right.shapes.length
      && left.shapes.every((shape, index) => shape === right.shapes[index])
      && JSON.stringify(left.editor_guides || null) === JSON.stringify(right.editor_guides || null)
      && JSON.stringify(left.editor_collapsed_groups || []) === JSON.stringify(right.editor_collapsed_groups || []));
  }
  function create({ limit = 80, now = () => performance.now(), timestamp = () => new Date().toISOString() } = {}) {
    let entries = Object.freeze([]), index = -1, floor = -1, lastReason = "", lastAt = 0;
    let sequence = 0;
    const current = () => index >= 0 ? entries[index] : null;
    function reset() {
      entries = Object.freeze([]); index = -1; floor = -1; lastReason = ""; lastAt = 0;
    }
    function installBaseline(snapshot, reason, protectedSource) {
      snapshot.history_reason = String(reason);
      snapshot.history_at = timestamp();
      entries = Object.freeze([snapshot]); index = 0; floor = protectedSource ? 0 : -1;
      lastReason = ""; lastAt = 0; sequence++;
      return snapshot;
    }
    return {
      get entries() { return entries; },
      get index() { return index; },
      get floor() { return floor; },
      get sequence() { return sequence; },
      current, reset, installBaseline,
      commit(snapshot, reason = "change") {
        if (equal(current(), snapshot)) return false;
        snapshot.history_reason = String(reason || "change");
        snapshot.history_at = timestamp();
        const at = now();
        const coalesce = reason === "nudge" && lastReason === reason && at - lastAt < 400
          && index === entries.length - 1 && index > Math.max(0, floor);
        const next = entries.slice(0, index + 1);
        if (coalesce) next[index] = snapshot;
        else {
          next.push(snapshot);
          if (next.length > limit) { next.shift(); if (floor >= 0) floor = Math.max(0, floor - 1); }
          index = next.length - 1;
        }
        entries = Object.freeze(next); lastReason = reason; lastAt = at; sequence++;
        return true;
      },
      replaceCurrent(snapshot) {
        if (index < 0) return false;
        const next = entries.slice(); next[index] = snapshot; entries = Object.freeze(next);
        sequence++;
        return true;
      },
      // Called only after the scene owner has installed the requested snapshot.
      acceptRestore(target, expected) {
        if (!Number.isInteger(target) || target < Math.max(0, floor) || target >= entries.length
          || entries[target] !== expected) return false;
        index = target; lastReason = ""; sequence++;
        return true;
      },
      breakCoalescing() { lastReason = ""; },
      estimate() {
        const unique = new Set(); let references = 0, metadata = 0;
        for (const state of entries) {
          for (const shape of state.shapes || []) unique.add(shape);
          references += (state.shapes?.length || 0) * 8;
          metadata += JSON.stringify({editor_guides:state.editor_guides || null,
            editor_collapsed_groups:state.editor_collapsed_groups || []}).length;
        }
        let bytes = references + metadata;
        for (const shape of unique) bytes += shape.__historySignature?.length || JSON.stringify(shape).length;
        return {bytes, uniqueShapes:unique.size};
      },
    };
  }
  return {create, equal};
});
