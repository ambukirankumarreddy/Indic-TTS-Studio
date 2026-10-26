"""Design tokens for the studio UI (dark, violet accent)."""

BG = "#0e1016"
SIDEBAR = "#131620"
CARD = "#191d29"
CARD_2 = "#212636"
INPUT = "#11141c"
BORDER = "#2a3044"
HOVER = "#262c3e"

ACCENT = "#7c5cff"
ACCENT_HOVER = "#6847f0"
ACCENT_SOFT = "#2b2550"
TEAL = "#22d3ee"

TEXT = "#e8eaf2"
MUTED = "#8a92a8"
DIM = "#5b6378"

SUCCESS = "#34d399"
WARN = "#fbbf24"
DANGER = "#f87171"
INFO = "#60a5fa"

FONT = "Segoe UI"
FONT_INDIC = "Nirmala UI"   # ships with Windows, covers all Indic scripts


def font(size=13, weight="normal", family=FONT):
    import customtkinter as ctk
    return ctk.CTkFont(family=family, size=size, weight=weight)


def license_colors(license_text: str):
    """(bg, fg) for a license badge."""
    t = (license_text or "").lower()
    if "-nc" in t or "non-commercial" in t or "iit madras" in t or "indictts" in t:
        return "#3a2c10", WARN
    if "microsoft" in t:
        return "#132a45", INFO
    if "apache" in t or "cc by 4.0" in t or "mit" in t:
        return "#0f3326", SUCCESS
    return CARD_2, MUTED


KIND_COLORS = {
    "Studio": ACCENT, "Dialogue": TEAL, "Audiobook": SUCCESS,
    "Subtitles": WARN, "Batch": INFO, "Preview": MUTED,
}
