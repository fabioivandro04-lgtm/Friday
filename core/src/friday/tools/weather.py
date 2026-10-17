"""Previsão do tempo via Open-Meteo (grátis, sem chave)."""

from __future__ import annotations

import httpx

from friday.tools.registry import Tool

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

# Códigos WMO resumidos em PT-PT.
_CODES = [
    ((0,), "céu limpo"),
    ((1, 2), "pouco nublado"),
    ((3,), "nublado"),
    ((45, 48), "nevoeiro"),
    ((51, 53, 55, 56, 57), "chuvisco"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "chuva"),
    ((71, 73, 75, 77, 85, 86), "neve"),
    ((95, 96, 99), "trovoada"),
]


def _describe(code: int) -> str:
    return next((text for codes, text in _CODES if code in codes), "tempo variável")


def make_weather_tool(default_city: str) -> Tool:
    async def weather(city: str = "", day: str = "hoje") -> str:
        name = (city or default_city).strip()
        index = 1 if day.strip().lower() in ("amanhã", "amanha", "tomorrow") else 0
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                geo = await client.get(GEO, params={"name": name, "count": 1, "language": "pt"})
                results = geo.json().get("results") or []
                if not results:
                    return f"ERRO: não encontrei a cidade {name}."
                place = results[0]
                fc = await client.get(
                    FORECAST,
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "daily": "temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max,weather_code",
                        "timezone": "auto",
                        "forecast_days": 2,
                    },
                )
                daily = fc.json()["daily"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            return f"ERRO: previsão indisponível ({e})."
        label = "amanhã" if index else "hoje"
        return (
            f"{place['name']}, {label}: {_describe(daily['weather_code'][index])}, "
            f"máxima {round(daily['temperature_2m_max'][index])}°C, "
            f"mínima {round(daily['temperature_2m_min'][index])}°C, "
            f"probabilidade de chuva {daily['precipitation_probability_max'][index]}%."
        )

    return Tool(
        name="weather",
        description=f"Previsão do tempo para hoje ou amanhã (cidade padrão: {default_city}).",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "day": {"type": "string", "enum": ["hoje", "amanhã"]},
            },
        },
        handler=weather,
    )
