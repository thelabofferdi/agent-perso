"""Recherche Internet (Tavily) et météo (WeatherAPI)."""

import httpx

from app.config import ToolError, get_settings

TIMEOUT = httpx.Timeout(20.0)


async def _get_json(client: httpx.AsyncClient, method: str, url: str, **kw) -> dict:
    try:
        resp = await client.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise ToolError(f"Service injoignable : {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise ToolError(f"Erreur {resp.status_code} du service : {resp.text[:200]}")
    return resp.json()


async def web_search(query: str, max_results: int = 5, news: bool = False) -> str:
    """Recherche sur Internet via Tavily. Renvoie un résumé et les sources avec leurs liens."""
    s = get_settings()
    if s.missing("tavily_api_key"):
        raise ToolError("TAVILY_API_KEY n'est pas configurée.")
    payload = {
        "query": query,
        "max_results": max(1, min(max_results, 10)),
        "topic": "news" if news else "general",
        "include_answer": True,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        data = await _get_json(
            client, "POST", "https://api.tavily.com/search", json=payload,
            headers={"Authorization": f"Bearer {s.tavily_api_key}"},
        )
    lines = []
    if data.get("answer"):
        lines.append(f"Résumé : {data['answer']}\n")
    for i, r in enumerate(data.get("results", []), 1):
        lines.append(f"{i}. {r.get('title')}\n   {r.get('url')}\n   {(r.get('content') or '')[:400]}")
    return "\n".join(lines) or "Aucun résultat."


async def _weather_call(endpoint: str, city: str) -> dict:
    s = get_settings()
    if s.missing("weather_api_key"):
        raise ToolError("OPENWEATHER_API_KEY n'est pas configurée.")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await _get_json(
            client, "GET", f"https://api.openweathermap.org/data/2.5/{endpoint}",
            params={"q": city, "appid": s.weather_api_key, "units": "metric", "lang": "fr"},
        )


async def get_current_weather(city: str) -> str:
    """Météo actuelle d'une ville (température, ressenti, conditions, vent, humidité)."""
    d = await _weather_call("weather", city)
    m, w = d["main"], d["weather"][0]
    return (
        f"{d['name']} ({d['sys'].get('country', '?')}) : {w['description']}, "
        f"{m['temp']:.0f}°C (ressenti {m['feels_like']:.0f}°C), vent {d['wind']['speed'] * 3.6:.0f} km/h, "
        f"humidité {m['humidity']}%."
    )


async def get_weather_forecast(city: str, days: int = 3) -> str:
    """Prévisions météo d'une ville sur 1 à 5 jours."""
    d = await _weather_call("forecast", city)
    by_day: dict[str, list[dict]] = {}
    for e in d["list"]:
        by_day.setdefault(e["dt_txt"][:10], []).append(e)
    out = [f"Prévisions pour {d['city']['name']} ({d['city'].get('country', '?')}) :"]
    for date, es in list(by_day.items())[: max(1, min(days, 5))]:
        mid = es[len(es) // 2]["weather"][0]["description"]
        out.append(
            f"- {date} : {mid}, {min(e['main']['temp_min'] for e in es):.0f}–"
            f"{max(e['main']['temp_max'] for e in es):.0f}°C, "
            f"pluie {max(e.get('pop', 0) for e in es) * 100:.0f}%"
        )
    return "\n".join(out)
