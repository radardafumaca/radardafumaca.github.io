"""Focos do mês atual comparados com o mesmo período dos anos anteriores.

Para a comparação ser justa entre anos, usa um satélite só, o Suomi NPP (VIIRS),
em órbita desde 2012: somar os satélites mais novos (NOAA-20, NOAA-21) inflaria os
anos recentes. Conta os focos por dia (data UTC da detecção) no raio de 300 km.

O arquivo dos anos passados (FIRMS "SP") é baixado uma vez por mês e guardado em
data/anos.json, publicado com o site; a cada rodada só os últimos dias do ano atual
(FIRMS "NRT") são atualizados.

    python3 scripts/anos.py
"""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

from update_data import DATA, MANAUS, RADIUS_KM, distance_km, download, firms_key, region_bbox

SAIDA = DATA / "anos.json"
ANTERIOR = DATA / "anos.prev.json"
PRIMEIRO_ANO = 2012  # Suomi NPP desde janeiro de 2012
API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{fonte}/{area}/{dias}/{inicio}"


def contar(key, fonte, inicio, dias):
    """Focos por dia (AAAA-MM-DD -> n) numa janela de até 5 dias."""
    texto = download(API.format(key=key, fonte=fonte, area=region_bbox(), dias=dias, inicio=inicio.isoformat()))
    if not texto or not texto.startswith("latitude"):
        raise RuntimeError(f"FIRMS recusou {fonte} {inicio}: {(texto or '').strip()[:120]}")
    por_dia = {}
    for r in csv.DictReader(io.StringIO(texto)):
        if r["confidence"].strip() == "l":
            continue
        if distance_km(*MANAUS, float(r["latitude"]), float(r["longitude"])) > RADIUS_KM:
            continue
        por_dia[r["acq_date"]] = por_dia.get(r["acq_date"], 0) + 1
    return por_dia


def dias_do_mes(ano, mes):
    proximo = date(ano + (mes == 12), mes % 12 + 1, 1)
    return (proximo - date(ano, mes, 1)).days


def contar_mes(key, fonte, ano, mes, ate_dia=None):
    """Lista com os focos de cada dia do mês (até ate_dia), em janelas de 5 dias."""
    total = ate_dia or dias_do_mes(ano, mes)
    contagem = [0] * total
    for inicio in range(1, total + 1, 5):
        dias = min(5, total - inicio + 1)
        for dia_iso, n in contar(key, fonte, date(ano, mes, inicio), dias).items():
            d = date.fromisoformat(dia_iso)
            if d.year == ano and d.month == mes and d.day <= total:
                contagem[d.day - 1] += n
    return contagem


def main():
    key = firms_key()
    if not key:
        print("sem FIRMS_MAP_KEY: comparação com outros anos fica de fora")
        return
    hoje = datetime.now(timezone.utc).date()
    mes_id = f"{hoje.year}-{hoje.month:02d}"
    dados = None
    for fonte in (ANTERIOR, SAIDA):
        try:
            dados = json.loads(fonte.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    if not dados or dados.get("mes") != mes_id:
        dados = {"mes": mes_id, "fonte": "VIIRS Suomi NPP", "raio_km": RADIUS_KM, "anos": {}, "atual": []}

    # anos passados: baixados uma vez por mês (os que faltarem)
    baixados = 0
    for ano in range(PRIMEIRO_ANO, hoje.year):
        if str(ano) in dados["anos"]:
            continue
        try:
            dados["anos"][str(ano)] = contar_mes(key, "VIIRS_SNPP_SP", ano, hoje.month)
            baixados += 1
        except RuntimeError as error:
            print(error)

    # ano atual: refaz os últimos 3 dias (o "hoje" ainda está chegando) e completa o que faltar
    atual = dados.get("atual", [])[: max(0, hoje.day - 3)]
    try:
        inicio = len(atual) + 1
        resto = contar_mes(key, "VIIRS_SNPP_NRT", hoje.year, hoje.month, ate_dia=hoje.day)[inicio - 1:] if inicio <= hoje.day else []
        dados["atual"] = atual + resto
    except RuntimeError as error:
        print(error)

    dados["ano_atual"] = hoje.year
    dados["ate_dia"] = len(dados["atual"])
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    SAIDA.write_text(json.dumps(dados, separators=(",", ":")), encoding="utf-8")
    ate = dados["ate_dia"]
    soma = {a: sum(v[:ate]) for a, v in dados["anos"].items()}
    agora = sum(dados["atual"])
    media = sum(soma.values()) / len(soma) if soma else 0
    print(f"anos: {mes_id}, dias 1–{ate}: {hoje.year} = {agora} focos; média {PRIMEIRO_ANO}–{hoje.year - 1} = {media:.0f}"
          f" ({baixados} ano(s) baixado(s) agora) -> {SAIDA}")


if __name__ == "__main__":
    main()
