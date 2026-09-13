import {InputError,MAX_BYTES,normalizeReport,readJsonLimited,readBytesLimited,redact} from '../public/protocol.mjs';
import {MAX_SCREENSHOTS_BYTES,describeScreenshot,screenshotName} from '../public/screenshots.mjs';
import {MAX_LOG_BYTES,describePrivateLogs,logFilename} from '../public/private-logs.mjs';

export async function readSubmission(request) {
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('multipart/form-data;')) {
    const report = normalizeReport(await readJsonLimited(request));
    if (report.screenshots?.length) throw new InputError('Reattach the original screenshots before retrying this report.');
    if (report.private_logs) throw new InputError('Reattach the saved KFPS report bundle to include the complete private logs.');
    return {report,files:[],privateLogs:null};
  }
  const bytes = await readBytesLimited(request,MAX_SCREENSHOTS_BYTES+MAX_LOG_BYTES+MAX_BYTES+16384);
  let form;
  try { form = await new Response(bytes,{headers:{'Content-Type':request.headers.get('content-type')}}).formData(); }
  catch { throw new InputError('Invalid screenshot upload.'); }
  const raw = form.get('report');
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > MAX_BYTES) throw new InputError('Invalid report data.');
  let input;
  try { input = JSON.parse(raw); } catch { throw new InputError('Invalid JSON report.'); }
  const report = normalizeReport(input), files = [], metadata = report.screenshots || [];
  const keys = [...form.keys()];
  if (keys.length !== metadata.length+1+Number(!!report.private_logs) || new Set(keys).size !== keys.length
      || keys.some(key=>key!=='report'&&!(report.private_logs&&key==='private_logs')&&!metadata.some((_,i)=>key===`screenshot[${i}]`))) throw new InputError('Unexpected or missing attachment files.');
  for (let i=0;i<metadata.length;i++) {
    const file = form.get(`screenshot[${i}]`);
    let actual;
    try { actual = await describeScreenshot(file); } catch(error) { throw new InputError(error.message); }
    if (Object.keys(actual).some(key=>actual[key]!==metadata[i][key])) throw new InputError('Screenshot changed. Reattach the original screenshots to retry.');
    files.push(file);
  }
  const privateLogs=report.private_logs?form.get('private_logs'):null;
  if(report.private_logs) {
    try {
      const {metadata}=await describePrivateLogs(privateLogs,{redact});
      if(JSON.stringify(metadata)!==JSON.stringify(report.private_logs))throw Error('Private logs changed. Reattach the original report bundle to retry.');
    } catch(error) {throw new InputError(error.message);}
  }
  return {report,files,privateLogs};
}

export function submissionBody(report,files,privateLogs=null) {
  const form = new FormData(); form.set('report',JSON.stringify(report));
  files.forEach((file,i)=>form.set(`screenshot[${i}]`,file,screenshotName(i,report.screenshots[i].type)));
  if(privateLogs)form.set('private_logs',privateLogs,logFilename(report.id,report.private_logs?.schema));
  return form;
}
