import { configureSurfaceEditing, surfaceAtClient, surfaceCameraEnabled, setSurfaceSelection } from './livery-scene.js';
import { gestureTransform } from './surface-math.mjs';

const MODES = new Set(['orbit', 'move', 'scale', 'rotate', 'skew']);

export function createSurfaceEditor({ canvas, viewport, config, getState, getBounds, hitPlacement, select, begin, preview, commit, cancel, message, pickStack }) {
  configureSurfaceEditing(config);
  let mode = 'orbit', drag = null, queued = 0, pending = null, disposed = false;
  const controller = new AbortController(), signal = controller.signal;
  const refresh = () => {
    if (disposed) return;
    canvas.style.cursor = drag ? 'grabbing' : mode === 'orbit' ? 'grab' : 'crosshair';
    viewport.dataset.surfaceMode = mode;
    const state = getState(), placement = state.project?.placements.find(item => item.id === state.selected);
    setSurfaceSelection(mode !== 'orbit' && placement?.visible ? placement : null, placement ? getBounds?.(placement.id) : null);
  };
  const finish = (abort = false) => {
    if (!drag) return;
    if (queued) { cancelAnimationFrame(queued); queued = 0; }
    if (!abort && pending) move(pending);
    pending = null;
    if (!drag) return;
    const pointerId = drag.pointerId; drag = null;
    if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
    try { if (abort) cancel(); else commit(); }
    finally { surfaceCameraEnabled(true); refresh(); }
  };
  function move(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    // Scale and skew use screen displacement, not changing native surface UVs.
    const hit = mode === 'move' || mode === 'rotate' ? surfaceAtClient(event.clientX, event.clientY) : null;
    if (mode === 'move' && (!hit || hit.section !== drag.section)) {
      message('The pointer left this paintable section. Move back onto the same section to continue.');
      return;
    }
    const current = hit?.section === drag.section ? hit : { ...drag.start, screen: [event.clientX, event.clientY] };
    try {
      preview(drag.placement.id, gestureTransform(drag.placement, mode, drag.start, current,
        { aspectLocked: getState().aspectLocked, snap: event.shiftKey&&!event.ctrlKey }),{bypassSnap:event.ctrlKey});
      refresh();
    } catch (error) { finish(true); message(error.message, true); }
  }
  canvas.addEventListener('pointerdown', event => {
    if (disposed || (mode === 'orbit' && !(event.altKey && pickStack)) || event.button !== 0 || drag) return;
    const state = getState(); if (state.busy || state.dragging) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const hit = surfaceAtClient(event.clientX, event.clientY);
    if (!hit) { message('This surface has no eligible livery mapping.'); return; }
    if(event.altKey&&pickStack){pickStack(hit.section,...hit.point);return;}
    const id = hitPlacement(hit.section, ...hit.point);
    if (!id) { select(null, hit.section); message('No vinyl at this point. Add or place a vinyl on this section.'); return; }
    if(select(id, hit.section,{additive:event.shiftKey})===false)return;
    if(event.shiftKey)return;
    const placement = getState().project.placements.find(item => item.id === id);
    if (!placement || begin(id) === false) return;
    surfaceCameraEnabled(false);
    drag = { pointerId: event.pointerId, placement: structuredClone(placement), start: hit, section: hit.section };
    canvas.setPointerCapture(event.pointerId); canvas.focus({ preventScroll: true }); refresh();
  }, { capture: true, signal });
  canvas.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    event.preventDefault(); event.stopImmediatePropagation(); pending = event;
    if (!queued) queued = requestAnimationFrame(() => { queued = 0; const value = pending; pending = null; if (value) move(value); });
  }, { capture: true, signal });
  canvas.addEventListener('pointerup', event => {
    if (drag?.pointerId !== event.pointerId) return;
    event.preventDefault(); event.stopImmediatePropagation(); finish();
  }, { capture: true, signal });
  canvas.addEventListener('pointercancel', event => { if (drag?.pointerId === event.pointerId) finish(true); }, { signal });
  canvas.addEventListener('lostpointercapture', event => { if (drag?.pointerId === event.pointerId) finish(true); }, { signal });
  window.addEventListener('keydown', event => {
    if (drag && event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); finish(true); }
  }, { capture: true, signal });
  window.addEventListener('blur', () => finish(true), { signal });
  document.addEventListener('visibilitychange', () => { if (document.hidden) finish(true); }, { signal });
  window.addEventListener('pagehide', () => api.dispose(), { signal });
  const api = {
    setMode(next) {
      if (disposed) return;
      if (!MODES.has(next)) throw Error('Unknown editing mode.');
      finish(true); mode = next;
      if (mode !== 'orbit') { surfaceCameraEnabled(false); surfaceCameraEnabled(true); }
      refresh();
    },
    refresh,
    getState: () => ({ mode, dragging: Boolean(drag), disposed }),
    dispose() { if (disposed) return; disposed = true; finish(true); controller.abort(); setSurfaceSelection(null); canvas.style.cursor = ''; delete viewport.dataset.surfaceMode; },
  };
  refresh();
  return api;
}
