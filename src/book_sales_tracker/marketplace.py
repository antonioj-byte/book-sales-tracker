from dataclasses import dataclass


@dataclass(frozen=True)
class MarketplaceConfig:
    code: str
    label: str
    keepa_domain_id: int
    google_books_country: str
    google_books_lang: str


MARKETPLACES: dict[str, MarketplaceConfig] = {
    "es": MarketplaceConfig("es", "Amazon.es — España", 9, "ES", "es"),
    "com": MarketplaceConfig("com", "Amazon.com — Estados Unidos", 1, "US", "en"),
    "de": MarketplaceConfig("de", "Amazon.de — Alemania", 3, "DE", "de"),
    "co.uk": MarketplaceConfig("co.uk", "Amazon.co.uk — Reino Unido", 2, "GB", "en"),
    "fr": MarketplaceConfig("fr", "Amazon.fr — Francia", 4, "FR", "fr"),
    "it": MarketplaceConfig("it", "Amazon.it — Italia", 8, "IT", "it"),
}


def get_marketplace(code: str) -> MarketplaceConfig:
    normalized = code.strip().lower()
    if normalized not in MARKETPLACES:
        supported = ", ".join(sorted(MARKETPLACES))
        raise ValueError(f"Marketplace no soportado: {code}. Opciones: {supported}")
    return MARKETPLACES[normalized]


def list_marketplace_options() -> list[tuple[str, str]]:
    return [(cfg.code, cfg.label) for cfg in MARKETPLACES.values()]
