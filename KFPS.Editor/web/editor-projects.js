(function installProjects(root) {
  "use strict";
  function create({ persistence, generation, requestId = () => root.crypto.randomUUID() }) {
    let association = null;
    let associatedGeneration = -1;
    let associatedName = "";
    const valid = receipt => receipt && typeof receipt.target_id === "string"
      && receipt.target_id.length > 0 && receipt.target_id.length <= 1024
      && /^[a-f0-9]{64}$/.test(receipt.fingerprint)
      && Number.isSafeInteger(receipt.bytes) && receipt.bytes >= 0;
    const unknown = () => Object.assign(new Error("The save could not be confirmed. Check saved projects before saving another copy."), { code: "save_unknown" });
    async function write(operation, name, payload, expected) {
        const id = requestId();
        let result;
        try {
          result = await persistence.request(operation, {
            name, payload, request_id: id, expected_fingerprint: expected?.fingerprint || null, target_id: expected?.target_id,
            overwrite: Boolean(expected),
          });
          if (!valid(result?.receipt) || result.receipt.request_id !== id || result.receipt.write_stage !== "committed") throw unknown();
        } catch (error) {
          if (["project_exists", "project_conflict", "project_too_large", "export_too_large", "save_request_used"].includes(error.code)) throw error;
          // A worker/network timeout says nothing about whether replacement ran.
          // Reconcile the receipt, never replay the write or download a second copy.
          try {
            result = await persistence.request("fetchJSON", { url: `/api/fabric-editor/project-receipt?request_id=${id}&kind=${operation === "saveExport" ? "export" : "project"}` });
          } catch (_error) { throw unknown(); }
          if (result?.status !== "committed" || !valid(result.receipt) || result.receipt.request_id !== id) throw unknown();
        }
        return { ...result, id: result.id || result.receipt.target_id, title: result.title || name, receipt: Object.freeze({ ...result.receipt }) };
    }
    return {
      get association() { return associatedGeneration === generation() ? association : null; },
      expected(name) { return associatedGeneration === generation() && associatedName === name ? association : null; },
      associate(receipt, name = "") {
        association = valid(receipt) ? Object.freeze({ ...receipt }) : null;
        associatedGeneration = generation();
        associatedName = name;
      },
      async verify(receipt) {
        if (!valid(receipt)) return false;
        try {
          const result = await persistence.request("fetchJSON", {
            url: `/api/fabric-editor/project-receipt?id=${encodeURIComponent(receipt.target_id)}&fingerprint=${receipt.fingerprint}`,
          });
          return result.current === true;
        } catch (_error) { return false; }
      },
      save: (name, payload, expected) => write("saveProject", name, payload, expected),
      export: (name, payload) => write("saveExport", name, payload, null),
    };
  }
  const api = { create };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.KfpsEditorProjects = api;
})(typeof globalThis === "object" ? globalThis : this);
