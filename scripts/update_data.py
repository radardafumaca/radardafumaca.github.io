"""Baixa os focos de calor do INPE e gera data/focos.json com a região de Manaus.

Usa só a biblioteca padrão. Rode na raiz do projeto:
    python3 scripts/update_data.py
"""
import csv
import io
import json
import math
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

MANAUS = (-3.119, -60.0217)
RADIUS_KM = 300
WINDOW_HOURS = 48
DAILY_URL = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/"
    "focos_diario_br_{date}.csv"
)
OUT = Path(__file__).resolve().parent.parent / "data" / "focos.json"


def distance_km(lat1, lon1, lat2, lon2):
    # Aproximação equiretangular: erro desprezível num raio de 300 km.
    rad = math.pi / 180
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) / 2 * rad)
    y = (lat2 - lat1) * rad
    return 6371 * math.hypot(x, y)


def number(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return None if n <= -999 else n


def nome_proprio(texto):
    minusculas = {"de", "da", "do", "das", "dos", "e"}
    palavras = texto.lower().split()
    return " ".join(p if i and p in minusculas else p.capitalize() for i, p in enumerate(palavras))


def fetch_day(day):
    url = DAILY_URL.format(date=day.strftime("%Y%m%d"))
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=WINDOW_HOURS)

    rows = []
    for offset in range(3):
        text = fetch_day(now - timedelta(days=offset))
        if text:
            rows.extend(csv.DictReader(io.StringIO(text)))

    seen = set()
    focos = []
    municipios = defaultdict(lambda: {"focos": 0, "dist_min": None, "dias_sem_chuva": [], "risco": []})
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        lat, lon = float(row["lat"]), float(row["lon"])
        dist = distance_km(*MANAUS, lat, lon)
        if dist > RADIUS_KM:
            continue
        when = datetime.strptime(row["data_hora_gmt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if when < cutoff:
            continue

        nome = nome_proprio(row["municipio"])
        m = municipios[nome]
        m["focos"] += 1
        m["estado"] = row["estado"]
        m["dist_min"] = dist if m["dist_min"] is None else min(m["dist_min"], dist)
        dias = number(row["numero_dias_sem_chuva"])
        risco = number(row["risco_fogo"])
        if dias is not None:
            m["dias_sem_chuva"].append(dias)
        if risco is not None:
            m["risco"].append(risco)

        frp = number(row["frp"])
        focos.append([round(lat, 4), round(lon, 4), int(when.timestamp() // 60), nome, frp])

    lista = []
    for nome, m in municipios.items():
        lista.append({
            "nome": nome,
            "estado": nome_proprio(m["estado"]),
            "focos_48h": m["focos"],
            "dist_min_km": round(m["dist_min"]),
            "dias_sem_chuva": max(m["dias_sem_chuva"]) if m["dias_sem_chuva"] else None,
            "risco_fogo": round(sum(m["risco"]) / len(m["risco"]), 2) if m["risco"] else None,
        })
    lista.sort(key=lambda m: -m["focos_48h"])

    nomes = [m["nome"] for m in lista]
    indice = {nome: i for i, nome in enumerate(nomes)}
    focos.sort(key=lambda f: f[2])
    payload = {
        "atualizado_em": now.isoformat(timespec="minutes"),
        "centro": MANAUS,
        "raio_km": RADIUS_KM,
        "janela_horas": WINDOW_HOURS,
        "municipios": lista,
        # [lat, lon, minutos desde 1970 (UTC), índice do município, FRP em MW]
        "focos": [[f[0], f[1], f[2], indice[f[3]], f[4]] for f in focos],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(focos)} focos em {len(lista)} municípios -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
