"""Product lookup from the same Sanity dataset the storefront uses.

We only need name + price to build an order, keyed by the product's slug — the
same `slug` that the "Order on WhatsApp" deep link embeds as `#slug`.
"""
from __future__ import annotations

import httpx

from .config import settings

# GROQ: fetch the fields we need for one product by its slug.
_QUERY = (
    '*[_type == "product" && slug.current == $slug][0]'
    "{'slug': slug.current, name, price, compareAtPrice, category}"
)


async def get_product(slug: str) -> dict | None:
    """Return {slug, name, price, ...} or None if not found / Sanity unavailable."""
    if not settings.sanity_project_id:
        return None

    url = (
        f"https://{settings.sanity_project_id}.api.sanity.io"
        f"/v{settings.sanity_api_version}/data/query/{settings.sanity_dataset}"
    )
    headers = {}
    if settings.sanity_api_read_token:
        headers["Authorization"] = f"Bearer {settings.sanity_api_read_token}"
    params = {"query": _QUERY, "$slug": f'"{slug}"'}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        result = resp.json().get("result")

    if not result or result.get("price") is None:
        return None
    return result
