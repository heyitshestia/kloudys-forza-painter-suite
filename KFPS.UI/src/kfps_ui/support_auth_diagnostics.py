"""Fixed-field sign-in events only; never serialize renderer error text or URLs."""

STAGES = frozenset({"init", "start", "browser", "poll", "session", "cancel", "terminal"})
RESULTS = frozenset({"ready", "requested", "pending", "accepted", "failed", "manual", "reopen",
                     "network", "timeout", "rate-limited", "service-unavailable", "request-rejected",
                     "server-error", "invalid-response", "session-missing", "authenticated",
                     "expired", "denied", "cancelled"})


def record_signin_events(events, cursor, logger):
    if not isinstance(events, list) or len(events) > 64:
        return cursor
    for event in events:
        if not isinstance(event, dict):
            continue
        fields = [event.get(name) for name in ("sequence", "attempt", "http_status", "elapsed_ms")]
        if any(type(value) is not int for value in fields):
            continue
        sequence, attempt, status, elapsed = fields
        stage, result = event.get("stage"), event.get("result")
        if (not cursor < sequence <= 2147483647 or not 0 <= attempt <= 1000000
                or not (status == 0 or 100 <= status <= 599) or not 0 <= elapsed <= 600000
                or not isinstance(stage, str) or stage not in STAGES
                or not isinstance(result, str) or result not in RESULTS):
            continue
        if sequence > cursor + 1:
            logger.info("sign-in diagnostics-skipped=%s", sequence - cursor - 1)
        logger.info("sign-in attempt=%s stage=%s result=%s http_status=%s elapsed_ms=%s",
                    attempt, stage, result, status, elapsed)
        cursor = sequence
    return cursor
