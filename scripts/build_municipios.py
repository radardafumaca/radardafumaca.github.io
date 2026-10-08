"""Gera data/municipios.json com os limites dos municípios dentro do raio de Manaus.

Só precisa rodar de novo se o raio mudar. Fonte: malhas e localidades do IBGE.
    python3 scripts/build_municipios.py
"""
import gzip
import json
import urllib.request
from pathlib import Path

from update_data import MANAUS, RADIUS_KM, distance_km

UFS = {"13": "Amazonas", "15": "Pará", "14": "Roraima"}
MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
         "?formato=application/vnd.geo%2Bjson&intrarregiao=municipio&qualidade=intermediaria")
NOMES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
OUT = Path(__file__).resolve().parent.parent / "data" / "municipios.json"


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


if __name__ == "__main__":
    main()
