# FH6 RTTI GitHub Fallback Sync

Trusted calibrators publish the canonical FH6 locator registry to the isolated
Cloudflare relay. This tool validates that public registry with KFPS's runtime
parser and mirrors it into the repository-root `RTTI.dat` fallback.

The sync deliberately:

- rejects malformed, oversized, non-HTTPS, empty, or stale relay data;
- preserves checked-in profiles that are not present in the relay, up to the
  registry's 64-profile limit;
- writes atomically;
- produces no file change when the normalized profile content is unchanged;
- uses no Cloudflare administrator secret or calibrator credential.

GitHub runs it every five minutes and on manual dispatch through
`.github/workflows/sync-fh6-rtti.yml`. A normal local verification is read-only:

```powershell
python tools\fh6_rtti_sync\sync_registry.py --dry-run
```

The Cloudflare relay remains the application's primary runtime source. The
checked-in file is synchronized so raw GitHub, release bundles, and offline
fallbacks do not remain permanently stale.
