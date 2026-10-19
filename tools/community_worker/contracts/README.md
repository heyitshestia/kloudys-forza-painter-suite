# Verified Access Contract

`verified-access-contract.schema.json` is the accepted additive Community v1
wire contract shared by the worker and KFPS Community client. Its bytes are
frozen at SHA-256
`0264de524a9273131ad71222214cb8b36dda680cb8bc808a04d06c847da5d7ee`.
Only title/description changed from
`8c7a35b77a4f1a40bdf283f32466809b14ff674f0fd0a6548be72700c8e31168`;
schema meanings are identical. That predecessor adds the approved legacy-grant definitions to
6e190e1b921d8ff253f860dbd4ca4a0a9caf5af7345c3c75f0266af0297b74e8;
consumer capability fields are unchanged from that revision.
This supersedes b7a1797fac214cba34688715ef2e492ac11d7a88bdb8cb5a786803040989a65b
(age-only) and 8956dc1b5b1fb5bcbfe23074682fe442a6dfcdf2db481e9f7f4e4a2555f2888a
(ten uploads only). Current rule: 14 days AND ten own Handmade vinyls, OR a
permanent existing-key grant. See ACCOUNT-AGE.md and CURRENT-POLICY.md for the
exact fields, timestamp provenance, exception and reason precedence.
The historical URN is retained for reference compatibility; the implementation
was authorized on 2026-10-19, not deployed.

Current public policy authority is [CURRENT-POLICY.md](CURRENT-POLICY.md), with
connection-age evidence in [ACCOUNT-AGE.md](ACCOUNT-AGE.md) and paired historical
proof rules in [LEGACY-GRANT-PROOF.md](LEGACY-GRANT-PROOF.md). Current route/state
semantics and migration/rollback/repair instructions are in [ROLLOUT.md](ROLLOUT.md).
Private preflight/review records are historical evidence, not public dependencies
or a second independently editable contract.

Worker owner maintains this canonical file; Community client owner consumes it.
Any wire change requires explicit coordination before either implementation
changes. Existing payload fields are unchanged; these definitions are additive.
