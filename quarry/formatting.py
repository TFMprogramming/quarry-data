"""German number formatting for headlines shown in the app."""


def money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}".replace(".", ",") + " Mrd. $"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".replace(".", ",") + " Mio. $"
    return f"{round(value):,}".replace(",", ".") + " $"


def percent(fraction: float) -> str:
    sign = "+" if fraction >= 0 else "−"
    return f"{sign}{abs(fraction) * 100:.0f} %"
