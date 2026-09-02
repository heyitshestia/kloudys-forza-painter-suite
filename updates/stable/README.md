# Stable updater channel

`channel.json` and `channel.json.sig` are the only mutable pointers for the KFPS bootstrap updater.

Do not commit a channel until every referenced artifact has been uploaded to its immutable HTTPS URL and independently verified. Never edit either JSON or signature by hand. Generate them with `KFPS-Update-Publisher.exe`, publish a strictly higher sequence, and follow [the bootstrap updater publication procedure](../../docs/BOOTSTRAP_UPDATER.md#publication).

If no channel files are present, bootstrap updaters at or below the embedded recovery floor use the hash-pinned recovery path. Newer installations stop without downgrading.
