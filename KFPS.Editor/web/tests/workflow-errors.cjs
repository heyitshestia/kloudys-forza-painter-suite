"use strict";

function validatePageErrors(records, scripts, contracts) {
  const remaining = records.map(record => ({ ...record }));
  const expected = [], missing = [];
  for (const script of scripts) {
    for (const message of contracts.cases[script]?.expectedPageErrors || []) {
      const entry = { script, message };
      expected.push(entry);
      const index = remaining.findIndex(record => record.script === script && record.message === message);
      if (index < 0) missing.push(entry);
      else remaining.splice(index, 1);
    }
  }
  return { passed: !remaining.length && !missing.length, expected, missing, unexpected: remaining };
}

module.exports = { validatePageErrors };
