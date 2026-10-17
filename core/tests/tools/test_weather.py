import httpx
import respx

from friday.tools.weather import make_weather_tool

GEO = "https://geocoding-api.open-meteo.com/v1/search"
FC = "https://api.open-meteo.com/v1/forecast"


def _mock():
    respx.get(GEO).mock(
        return_value=httpx.Response(
            200, json={"results": [{"name": "Lisboa", "latitude": 38.7, "longitude": -9.1}]}
        )
    )
    return respx.get(FC).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2026-10-17", "2026-10-18"],
                    "temperature_2m_max": [22.4, 19.0],
                    "temperature_2m_min": [14.1, 13.2],
                    "precipitation_probability_max": [5, 80],
                    "weather_code": [1, 63],
                }
            },
        )
    )


@respx.mock
async def test_weather_today_and_tomorrow():
    fc = _mock()
    tool = make_weather_tool(default_city="Lisboa")
    today = await tool.handler()
    tomorrow = await tool.handler(city="Lisboa", day="amanhã")
    assert "Lisboa" in today and "22" in today and "14" in today
    assert "chuva" in tomorrow.lower() and "80%" in tomorrow
    assert fc.calls[0].request.url.params["timezone"] == "auto"


@respx.mock
async def test_unknown_city():
    respx.get(GEO).mock(return_value=httpx.Response(200, json={}))
    out = await make_weather_tool(default_city="Lisboa").handler(city="Xyzzy")
    assert out.startswith("ERRO") and "Xyzzy" in out


@respx.mock
async def test_network_error_is_message():
    respx.get(GEO).mock(side_effect=httpx.ConnectError("sem rede"))
    out = await make_weather_tool(default_city="Lisboa").handler()
    assert out.startswith("ERRO")
