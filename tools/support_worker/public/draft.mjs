import {normalizeReport,redact,MAX_BYTES,InputError} from './protocol.mjs';

// Drafts use the privacy allowlist, but incomplete text and unchecked consent
// must not destroy local context needed when the user resumes editing.
export function normalizeDraft(value) {
  const result=normalizeReport({...value,description:'Draft awaiting review.',include_technical:true});
  result.description=redact(value.description,3000);
  result.title=redact(value.title,90);
  result.expected=redact(value.expected,1500);
  result.include_technical=value.include_technical!==false;
  if(new TextEncoder().encode(JSON.stringify(result)).length>MAX_BYTES)throw new InputError('Report is too large. Remove some log text.');
  return result;
}
