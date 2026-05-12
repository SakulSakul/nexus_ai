"""Weather helper — Open-Meteo 무료 API (key 불필요)."""

from __future__ import annotations

import sys
from typing import Optional


# WMO weather code → (emoji, 한국어 설명) 간소화.
_WMO_MAP: dict = {
    0: ("☀️", "맑음"),
    1: ("🌤️", "대체로 맑음"),
    2: ("⛅", "구름 조금"),
    3: ("☁️", "흐림"),
    45: ("🌫️", "안개"),
    48: ("🌫️", "짙은 안개"),
    51: ("🌦️", "이슬비"),
    53: ("🌦️", "이슬비"),
    55: ("🌦️", "이슬비"),
    61: ("🌧️", "비"),
    63: ("🌧️", "비"),
    65: ("🌧️", "강한 비"),
    71: ("🌨️", "눈"),
    73: ("🌨️", "눈"),
    75: ("🌨️", "강한 눈"),
    77: ("🌨️", "싸락눈"),
    80: ("🌦️", "소나기"),
    81: ("🌦️", "소나기"),
    82: ("⛈️", "강한 소나기"),
    95: ("⛈️", "뇌우"),
    96: ("⛈️", "뇌우/우박"),
    99: ("⛈️", "강한 뇌우/우박"),
}


def _cache_decorator():
    """Streamlit 환경에서는 cache_data, 외부에서는 no-op."""
    try:
        import streamlit as st
        return st.cache_data(ttl=1800, show_spinner=False)
    except Exception:
        def _noop(fn):
            return fn
        return _noop


@_cache_decorator()
def get_current_weather(lat: float, lng: float) -> Optional[dict]:
    """Open-Meteo current weather. Returns {emoji, description, temperature} or None.

    30분 cache (Streamlit cache_data ttl=1800). 좌표별 별도 cache.
    """
    try:
        import json
        import urllib.request
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lng}"
            "&current=temperature_2m,weather_code"
            "&timezone=Asia%2FSeoul"
        )
        with urllib.request.urlopen(url, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        current = data.get("current") or {}
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None or code is None:
            return None
        emoji, desc = _WMO_MAP.get(int(code), ("🌡️", "기온"))
        return {
            "emoji": emoji,
            "description": desc,
            "temperature": round(float(temp), 1),
        }
    except Exception as e:
        print(
            f"[weather] get_current_weather({lat},{lng}) failed: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return None


# 회사 사업장 위치 — 본사(서울) + 인천공항점.
CITIES: dict = {
    "서울": (37.5665, 126.9780),
    "인천": (37.4563, 126.7052),
}


def get_all_weather() -> dict:
    """모든 등록된 도시의 현재 날씨 — 각 좌표별 cache."""
    return {
        name: get_current_weather(lat, lng)
        for name, (lat, lng) in CITIES.items()
    }
