"""Pure replay-safe watermark calculations."""


def calculate_low_watermark(
    next_unread_scn: int,
    oldest_open_transaction_scn: int | None = None,
    incomplete_continuation_scn: int | None = None,
    pending_ddl_replay_scn: int | None = None,
) -> int:
    candidates = [next_unread_scn]
    for value in (
        oldest_open_transaction_scn,
        incomplete_continuation_scn,
        pending_ddl_replay_scn,
    ):
        if value is not None:
            candidates.append(value)
    return min(candidates)


def choose_window_end(start_scn: int, target_scn: int, span: int) -> int:
    if start_scn > target_scn:
        return target_scn
    return min(target_scn, start_scn + max(1, span) - 1)


def adapt_span(
    current_span: int,
    record_count: int,
    minimum_span: int,
    maximum_span: int,
    low_volume: int = 1_000,
    high_volume: int = 50_000,
) -> int:
    if record_count >= high_volume:
        return max(minimum_span, current_span // 2)
    if record_count <= low_volume:
        return min(maximum_span, current_span * 2)
    return current_span
