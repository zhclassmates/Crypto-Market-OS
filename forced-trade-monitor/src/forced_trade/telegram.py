"""Alert sink. Not on the research path."""


def format_alert(symbol: str, state: str, bar_open_ts: int) -> str:
    return f"{symbol} {state} bar={bar_open_ts}"
