"""The public query vocabulary and validation for shared dashboard selections."""

from urllib.parse import parse_qs

from bh_itbi.config import YEARS

QUERY_OPTIONS = {
    "tipo": {"apartamento": "apartment", "casa": "house", "ambos": "all"},
    "medida": {
        "real_m2": "price_per_m2_brl_real",
        "nominal_m2": "price_per_m2_brl",
        "nominal": "value_declared_brl",
    },
    "mapa": {"ruas": "carto-voyager", "sem_fundo": "white-bg"},
}
DEFAULT_METRIC = "price_per_m2_brl_real"
DEFAULT_MAP_STYLE = "carto-voyager"


def default_controls() -> tuple[str, list[int], list[str], str, str]:
    """Return fresh control values, including the two presentation selections."""
    return "all", [YEARS[0], YEARS[-1]], [], DEFAULT_METRIC, DEFAULT_MAP_STYLE


def decode_query(
    search: str | None, available_neighbourhoods: set[str]
) -> tuple[str, list[int], list[str], str, str]:
    """Decode a query without changing analytical filter validation.

    Missing or invalid scalar fields use their defaults. Reversed periods reset
    both endpoints; valid neighbourhoods survive alongside unknown names.
    Repeated ``bairros`` parameters preserve names containing commas or accents.
    """
    defaults = default_controls()
    try:
        query = parse_qs(
            (search or "").lstrip("?"), keep_blank_values=True, max_num_fields=1000
        )
    except ValueError:
        return defaults

    def scalar(name: str) -> str | None:
        values = query.get(name, [])
        return values[0] if len(values) == 1 else None

    def year(name: str, default: int) -> int:
        raw = scalar(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return value if value in YEARS else default

    start, end = year("inicio", YEARS[0]), year("fim", YEARS[-1])
    years = [start, end] if start <= end else defaults[1]
    names = {name.strip().upper() for name in query.get("bairros", [])}
    return (
        QUERY_OPTIONS["tipo"].get(scalar("tipo") or "", defaults[0]),
        years,
        sorted(names & available_neighbourhoods),
        QUERY_OPTIONS["medida"].get(scalar("medida") or "", defaults[3]),
        QUERY_OPTIONS["mapa"].get(scalar("mapa") or "", defaults[4]),
    )
