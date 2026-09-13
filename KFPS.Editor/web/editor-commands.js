(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorCommands = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ generation, event = () => {}, overflow = () => {}, limit = 128 }) {
    const queue = [];
    let running = false, sequence = 0, disposed = false, committingId = 0;
    const emit = (task, state) => { try { event({ id:task.id, name:task.name, state }); } catch (_) {} };
    async function drain() {
      if (running) return;
      running = true;
      try {
        while (queue.length) {
          const task = queue.shift();
          if (disposed || task.generation !== generation()) { emit(task,"cancelled"); task.resolve(false); continue; }
          let committed = false;
          const context = {
            id: task.id,
            generation: task.generation,
            current: () => !disposed && task.generation === generation(),
            commit(apply) {
              if (committed) throw Error("Operation already committed");
              if (!context.current()) return false;
              committed = true;
              committingId = task.id;
              try {
                const result = apply();
                emit(task,"committed");
                return result;
              } finally { committingId = 0; }
            },
          };
          emit(task,"pending");
          try {
            const value = await task.operation(context);
            if (!committed) emit(task, context.current() ? "finished" : "cancelled");
            task.resolve(value);
          }
          catch (error) { emit(task,"failed"); task.reject(error); }
        }
      } finally { running = false; }
    }
    return {
      enqueue(operation, name = "edit") {
        if (disposed) return Promise.resolve(false);
        if (queue.length >= limit) { overflow(); return Promise.resolve(false); }
        return new Promise((resolve,reject) => {
          queue.push({operation,name,resolve,reject,id:++sequence,generation:generation()});
          void drain();
        });
      },
      get busy() { return running; },
      get committingId() { return committingId; },
      get pending() { return queue.length; },
      dispose() {
        disposed = true;
        for (const task of queue.splice(0)) { emit(task,"cancelled"); task.resolve(false); }
      },
    };
  }
  return {create};
});
