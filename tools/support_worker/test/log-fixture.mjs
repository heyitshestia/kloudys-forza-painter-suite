import {gzipSync} from 'node:zlib';
import {describePrivateLogs,APP_LOG_SCHEMA} from '../public/private-logs.mjs';
import {redact} from '../public/protocol.mjs';

export const logBundle = {schema:APP_LOG_SCHEMA,created_at:'2026-09-13T12:00:00Z',files:[{
  name:'app-status-0000.log',modified_utc:'2026-09-13T12:00:00Z',source_bytes:26,omitted_lines:0,
  text:'Synthetic session started\n',
}],warnings:[]};
export const logBlob = new Blob([gzipSync(JSON.stringify(logBundle))],{type:'application/gzip'});
export const logMetadata = (await describePrivateLogs(logBlob,{redact})).metadata;
