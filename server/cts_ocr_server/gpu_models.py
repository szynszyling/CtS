"""Language codes exposed by the CtS client and their shared recognizers."""

GROUPS = {
    "base": ("eng", "jpn", "jpn_vert", "chi_sim", "chi_tra"),
    "latin": ("pol", "deu", "fra", "spa", "ita", "por", "ces", "tur"),
    "cyrillic": ("ukr", "rus", "bul", "srp"),
    "korean": ("kor",),
    "el": ("ell",),
}
LANGUAGES = {language: group for group, codes in GROUPS.items() for language in codes}


def recognizer_groups(languages, available=GROUPS):
    # Each recognizer includes ASCII. An English request alongside another
    # language can reuse its recognizer instead of running a second one.
    groups = tuple(dict.fromkeys(LANGUAGES[code] for code in languages if code != "eng"))
    if groups:
        return groups
    return (next(group for group in GROUPS if group in available),)
