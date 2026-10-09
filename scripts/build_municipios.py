"""Gera os arquivos fixos dos municípios dentro do raio de Manaus.

- data/municipios.json: limites (malhas do IBGE), usado pelo script de focos.
- data/cidades.json: nome e coordenadas da sede, usado pelo mapa para os nomes.

Só precisa rodar de novo se o raio mudar. Fontes: malhas e localidades do IBGE;
coordenadas das sedes de github.com/kelvins/municipios-brasileiros (licença MIT).
    python3 scripts/build_municipios.py
"""
import csv
import gzip
import io
import json
import urllib.request
from pathlib import Path

from update_data import MANAUS, RADIUS_KM, distance_km

UFS = {"13": "Amazonas", "15": "Pará", "14": "Roraima"}
MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
         "?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=intermediaria")
NOMES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
SEDES = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "municipios.json"
CIDADES = DATA / "cidades.json"


def get_json(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        body = response.read()
    # O IBGE às vezes responde em gzip mesmo sem o cliente pedir.
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return json.loads(body)


def rings_of(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def simplify(ring):
    # 3 casas decimais (~100 m) bastam para saber em que município um foco caiu.
    out = []
    for lon, lat in ring:
        point = [round(lon, 3), round(lat, 3)]
        if not out or out[-1] != point:
            out.append(point)
    return out


def main():
    municipios = {}
    for uf, estado in UFS.items():
        nomes = {str(m["id"]): m["nome"] for m in get_json(NOMES.format(uf=uf))}
        for feature in get_json(MALHA.format(uf=uf))["features"]:
            polygons = rings_of(feature["geometry"])
            near = any(
                distance_km(*MANAUS, lat, lon) <= RADIUS_KM + 30
                for polygon in polygons for lon, lat in polygon[0]
            )
            if not near:
                continue
            code = feature["properties"]["codarea"]
            municipios[code] = {
                "nome": nomes[code],
                "estado": estado,
                "poligonos": [[simplify(ring) for ring in polygon] for polygon in polygons],
            }
    OUT.write_text(json.dumps(municipios, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(municipios)} municípios -> {OUT} ({OUT.stat().st_size // 1024} KB)")

    with urllib.request.urlopen(SEDES, timeout=120) as response:
        sedes = {row["codigo_ibge"]: row for row in csv.DictReader(io.StringIO(response.read().decode("utf-8")))}
    cidades = []
    for code, m in municipios.items():
        sede = sedes.get(code)
        if not sede:
            print(f"sem coordenadas da sede: {m['nome']} ({code})")
            continue
        cidades.append({
            "codigo_ibge": code,
            "nome": m["nome"],
            "lon": round(float(sede["longitude"]), 4),
            "lat": round(float(sede["latitude"]), 4),
        })
    cidades.sort(key=lambda c: c["nome"])
    CIDADES.write_text(json.dumps(cidades, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(cidades)} sedes -> {CIDADES} ({CIDADES.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
