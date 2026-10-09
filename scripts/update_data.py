"""Baixa os focos de calor da NASA FIRMS e gera data/focos.json com a região de Manaus.

Com FIRMS_MAP_KEY (no ambiente ou no .env), usa a API e busca 5 dias; sem ela,
usa os arquivos abertos de 48 h. Do INPE vêm só os dias sem chuva e o risco de
fogo de cada município.

Usa só a biblioteca padrão. Rode na raiz do projeto:
    python3 scripts/update_data.py
"""
import csv
import io
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

MANAUS = (-3.119, -60.0217)
RADIUS_KM = 300
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "focos.json"
VENTO = DATA / "vento.json"

# Vento numa grade de 10 x 10 pontos sobre a região, junto ao solo (10 m) e a ~1,5 km
# (850 hPa), onde a fumaça costuma viajar. 100 pontos por rodada, a cada 30 min,
# fica abaixo do limite gratuito da Open-Meteo (10 mil consultas por dia).
WIND_URL = "https://api.open-meteo.com/v1/forecast"
WIND_GRID = 10

# Com chave (FIRMS_MAP_KEY), a API da FIRMS devolve só a região e até 5 dias.
FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{area}/{days}"
FIRMS_API_DAYS = 5
FIRMS_API_SOURCES = [
    ("VIIRS_SNPP_NRT", "VIIRS"),
    ("VIIRS_NOAA20_NRT", "VIIRS"),
    ("VIIRS_NOAA21_NRT", "VIIRS"),
    ("MODIS_NRT", "MODIS"),
]

# Sem chave, os arquivos abertos da FIRMS trazem as últimas 48 h da América do Sul.
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
FIRMS_SOURCES = [
    ("suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_48h.csv", "VIIRS"),
    ("noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_48h.csv", "VIIRS"),
    ("noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_48h.csv", "VIIRS"),
    ("modis-c6.1/csv/MODIS_C6_1_South_America_48h.csv", "MODIS"),
]
SATELITES = {
    "N": "Suomi NPP",
    "N20": "NOAA-20",
    "1": "NOAA-20",
    "N21": "NOAA-21",
    "2": "NOAA-21",
    "T": "Terra",
    "Terra": "Terra",
    "A": "Aqua",
    "Aqua": "Aqua",
}
INPE_DAILY = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/"
    "focos_diario_br_{date}.csv"
)


def firms_key():
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "FIRMS_MAP_KEY":
                key = value.strip().strip('"').strip("'")
    return key or None


def region_bbox():
    # Retângulo que contém o círculo do raio, no formato oeste,sul,leste,norte.
    dlat = RADIUS_KM / 111.2
    dlon = RADIUS_KM / (111.2 * math.cos(math.radians(MANAUS[0])))
    return f"{MANAUS[1] - dlon:.3f},{MANAUS[0] - dlat:.3f},{MANAUS[1] + dlon:.3f},{MANAUS[0] + dlat:.3f}"


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


def download(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


# ---------- municípios ----------

def inside_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class Municipios:
    def __init__(self, path):
        self.items = []
        for code, m in json.loads(path.read_text(encoding="utf-8")).items():
            points = [p for polygon in m["poligonos"] for p in polygon[0]]
            lons = [p[0] for p in points]
            lats = [p[1] for p in points]
            self.items.append({
                "code": code,
                "nome": m["nome"],
                "estado": m["estado"],
                "poligonos": m["poligonos"],
                "bbox": (min(lons), min(lats), max(lons), max(lats)),
                "centro": (sum(lats) / len(lats), sum(lons) / len(lons)),
            })

    def locate(self, lat, lon):
        for m in self.items:
            x0, y0, x1, y1 = m["bbox"]
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            for polygon in m["poligonos"]:
                if inside_ring(lon, lat, polygon[0]) and not any(inside_ring(lon, lat, h) for h in polygon[1:]):
                    return m
        # Foco sobre um rio largo ou na borda simplificada: usa o município mais próximo.
        return min(self.items, key=lambda m: distance_km(lat, lon, *m["centro"]))


# ---------- fontes ----------

def firms_texts(key):
    if key:
        area = region_bbox()
        for source, sensor in FIRMS_API_SOURCES:
            url = FIRMS_API.format(key=key, source=source, area=area, days=FIRMS_API_DAYS)
            text = download(url)
            # A API responde 200 com uma mensagem de erro em texto quando a chave é inválida.
            if text and not text.startswith("latitude"):
                raise RuntimeError(f"FIRMS recusou {source}: {text.strip()[:200]}")
            yield source, sensor, text
    else:
        for path, sensor in FIRMS_SOURCES:
            yield path, sensor, download(FIRMS + path)


def firms_focos(cutoff, key):
    focos = []
    for name, sensor, text in firms_texts(key):
        if not text:
            print(f"FIRMS sem dados: {name}")
            continue
        for row in csv.DictReader(io.StringIO(text)):
            lat, lon = float(row["latitude"]), float(row["longitude"])
            dist = distance_km(*MANAUS, lat, lon)
            if dist > RADIUS_KM:
                continue
            # Descarta detecções de baixa confiança (VIIRS "l", MODIS abaixo de 30%).
            conf = row["confidence"].strip()
            if (sensor == "VIIRS" and conf == "l") or (sensor == "MODIS" and (number(conf) or 0) < 30):
                continue
            when = datetime.strptime(row["acq_date"] + row["acq_time"].zfill(4), "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
            if when < cutoff:
                continue
            satelite = SATELITES.get(row["satellite"].strip(), row["satellite"].strip())
            focos.append({
                "lat": lat,
                "lon": lon,
                "dist": dist,
                "when": when,
                "frp": number(row["frp"]),
                "fonte": f"{satelite} ({sensor})",
            })
    return focos


def inpe_condicoes(now):
    """Dias sem chuva (máximo) e risco de fogo (média) por código IBGE, a partir dos focos do INPE."""
    dias = defaultdict(list)
    risco = defaultdict(list)
    for offset in range(2):
        text = download(INPE_DAILY.format(date=(now - timedelta(days=offset)).strftime("%Y%m%d")))
        if not text:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            if distance_km(*MANAUS, float(row["lat"]), float(row["lon"])) > RADIUS_KM:
                continue
            code = row["municipio_id"].strip()
            d, r = number(row["numero_dias_sem_chuva"]), number(row["risco_fogo"])
            if d is not None:
                dias[code].append(d)
            if r is not None:
                risco[code].append(r)
    return {
        code: {
            "dias_sem_chuva": max(dias[code]) if dias[code] else None,
            "risco_fogo": round(sum(risco[code]) / len(risco[code]), 2) if risco[code] else None,
        }
        for code in set(dias) | set(risco)
    }


def vento():
    dlat = (RADIUS_KM + 40) / 111.2
    dlon = (RADIUS_KM + 40) / (111.2 * math.cos(math.radians(MANAUS[0])))
    lat0, lon0 = MANAUS[0] - dlat, MANAUS[1] - dlon
    step_lat, step_lon = 2 * dlat / (WIND_GRID - 1), 2 * dlon / (WIND_GRID - 1)
    pontos = [(lat0 + j * step_lat, lon0 + i * step_lon) for j in range(WIND_GRID) for i in range(WIND_GRID)]
    query = urllib.parse.urlencode({
        "latitude": ",".join(f"{lat:.3f}" for lat, _ in pontos),
        "longitude": ",".join(f"{lon:.3f}" for _, lon in pontos),
        "current": "wind_speed_10m,wind_direction_10m,wind_speed_850hPa,wind_direction_850hPa",
        "timezone": "UTC",
    })
    with urllib.request.urlopen(f"{WIND_URL}?{query}", timeout=120) as response:
        respostas = json.load(response)

    def uv(speed_kmh, direction):
        # direção meteorológica: de onde o vento vem; u para leste, v para norte, em m/s
        speed = speed_kmh / 3.6
        rad = math.radians(direction)
        return [round(-speed * math.sin(rad), 2), round(-speed * math.cos(rad), 2)]

    superficie, altitude = [], []
    for r in respostas:
        c = r["current"]
        superficie.append(uv(c["wind_speed_10m"], c["wind_direction_10m"]))
        altitude.append(uv(c["wind_speed_850hPa"], c["wind_direction_850hPa"]))
    payload = {
        "atualizado_em": respostas[0]["current"]["time"] + "Z",
        # pontos em linhas de sul para norte, cada linha de oeste para leste
        "grade": {"lon0": round(lon0, 4), "lat0": round(lat0, 4), "dlon": round(step_lon, 4),
                  "dlat": round(step_lat, 4), "nx": WIND_GRID, "ny": WIND_GRID},
        "superficie": superficie,
        "altitude": altitude,
    }
    VENTO.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"vento em {len(respostas)} pontos -> {VENTO}")


def main():
    now = datetime.now(timezone.utc)
    key = firms_key()
    window_hours = FIRMS_API_DAYS * 24 if key else 48
    cutoff = now - timedelta(hours=window_hours)
    municipios = Municipios(DATA / "municipios.json")

    focos = firms_focos(cutoff, key)
    try:
        condicoes = inpe_condicoes(now)
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"INPE indisponível, seguindo sem dias sem chuva e risco: {error}")
        condicoes = {}

    stats = {}
    for f in focos:
        m = municipios.locate(f["lat"], f["lon"])
        f["code"] = m["code"]
        s = stats.setdefault(m["code"], {"m": m, "focos": 0, "dist_min": f["dist"]})
        s["focos"] += 1
        s["dist_min"] = min(s["dist_min"], f["dist"])

    lista = []
    for code, s in stats.items():
        extra = condicoes.get(code, {})
        lista.append({
            "codigo_ibge": code,
            "nome": s["m"]["nome"],
            "estado": s["m"]["estado"],
            "focos": s["focos"],
            "dist_min_km": round(s["dist_min"]),
            "dias_sem_chuva": extra.get("dias_sem_chuva"),
            "risco_fogo": extra.get("risco_fogo"),
        })
    lista.sort(key=lambda m: -m["focos"])
    indice = {m["codigo_ibge"]: i for i, m in enumerate(lista)}

    fontes = sorted({f["fonte"] for f in focos})
    fonte_idx = {nome: i for i, nome in enumerate(fontes)}
    focos.sort(key=lambda f: f["when"])
    payload = {
        "atualizado_em": now.isoformat(timespec="minutes"),
        "fonte": "NASA FIRMS (API)" if key else "NASA FIRMS (arquivos abertos)",
        "centro": MANAUS,
        "raio_km": RADIUS_KM,
        "janela_horas": window_hours,
        "satelites": fontes,
        "municipios": lista,
        # [lat, lon, minutos desde 1970 (UTC), índice do município, FRP em MW, índice do satélite]
        "focos": [
            [round(f["lat"], 4), round(f["lon"], 4), int(f["when"].timestamp() // 60),
             indice[f["code"]], f["frp"], fonte_idx[f["fonte"]]]
            for f in focos
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        vento()
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
        # sem vento a página continua funcionando; só a camada de correntes fica indisponível
        print(f"Open-Meteo indisponível, seguindo sem a grade de vento: {error}")

    origem = "API com chave" if key else "arquivos abertos"
    print(f"{len(focos)} focos ({window_hours} h, {origem}) em {len(lista)} municípios -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
