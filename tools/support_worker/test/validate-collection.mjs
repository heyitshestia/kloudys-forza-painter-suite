// Offline qualification of a package produced by the actual Python collector.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {readPackage} from '../public/private-logs.mjs';
import {redact,normalizeReport,publicSummary} from '../public/protocol.mjs';
import {submissionBody,readSubmission} from '../src/submission.mjs';

const value=await readPackage(new Blob([readFileSync(process.argv[2])]),{redact});
const report=normalizeReport({...value.report,description:'Offline diagnostic collection qualification'});
const response=await readSubmission(new Request('https://support.example',{method:'POST',body:submissionBody(report,[],value.logs)}));
assert.deepEqual(Buffer.from(await response.privateLogs.arrayBuffer()),Buffer.from(await value.logs.arrayBuffer()));
assert.equal(response.report.private_logs.files,value.bundle.files.length);
const publicText=publicSummary(report,{name:'Synthetic tester'});
for(const word of ['Pending event','Synthetic event','desktop.log','collection-index','PRIVATE'])assert(!publicText.includes(word));
assert(!JSON.stringify(value.bundle).includes('PRIVATE'));
const excluded=normalizeReport({...report,include_technical:false});
assert(!excluded.private_logs);
await assert.rejects(readSubmission(new Request('https://support.example',{method:'POST',body:submissionBody(excluded,[],value.logs)})));
console.log(JSON.stringify({files:value.bundle.files.length,privateBytesPreserved:true,publicEvidenceExcluded:true}));
