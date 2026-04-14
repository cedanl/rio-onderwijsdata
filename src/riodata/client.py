import httpx

BASE_URL = "https://lod.onderwijsregistratie.nl/api/rio/v2"
PAGE_SIZE = 100  # API maximum


def _extract(response: dict) -> tuple[list, str | None]:
    """Haal items en 'next'-link uit een HATEOAS-response."""
    embedded = response.get("_embedded", {})
    items = next(iter(embedded.values()), []) if embedded else []
    next_href = response.get("_links", {}).get("next", {}).get("href")
    return items, next_href


def get(resource: str, id: str, **params) -> dict:
    """Haal één resource op via ID."""
    r = httpx.get(f"{BASE_URL}/{resource}/{id}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch(resource: str, **params) -> list:
    """Haal alle items op van een list-resource (automatisch pagineren via HATEOAS).

    Geef page= mee om slechts één pagina op te halen.
    pageSize= overschrijft de standaard (100, API-maximum).
    Alle andere kwargs worden als query-parameters meegegeven.
    """
    page_size = params.pop("pageSize", PAGE_SIZE)
    single_page = "page" in params
    page = params.pop("page", 0)

    url = f"{BASE_URL}/{resource}"
    query = {"page": page, "pageSize": page_size, **params}

    results = []
    while url:
        # Geef params alleen mee als ze niet leeg zijn —
        # httpx overschrijft anders de query-string in de URL
        kwargs = {"params": query} if query else {}
        r = httpx.get(url, timeout=30, **kwargs)
        r.raise_for_status()
        data = r.json()

        if "_embedded" not in data:
            if results:
                # Lege laatste HATEOAS-pagina — stop paginering
                break
            # Endpoint dat nooit HATEOAS gebruikt (plain array of object)
            return data if isinstance(data, list) else [data]

        items, next_href = _extract(data)
        results.extend(items)

        if single_page or not next_href:
            break
        # Volg de HATEOAS 'next'-link (bevat al alle params)
        url, query = next_href, None

    return results


def related(resource: str, id: str, sub: str, **params) -> list:
    """Haal sub-resources op die gelinkt zijn aan een resource.

    Voorbeeld: related("aangeboden-opleidingen", uuid, "aangeboden-opleiding-cohorten")
    """
    r = httpx.get(f"{BASE_URL}/{resource}/{id}/{sub}", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "_embedded" in data:
        items, _ = _extract(data)
        return items
    return data if isinstance(data, list) else [data]
