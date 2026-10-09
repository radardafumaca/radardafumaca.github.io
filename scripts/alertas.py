"""Alertas no Telegram: piora do ar em Manaus, foco novo perto da cidade e resumo da manhã.

Usa TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (ambiente ou .env). Sem eles, roda em modo
de teste: mostra as mensagens e não envia nada.

O estado (o que já foi avisado) fica em <site>/data/alertas.json, publicado com o site;
a Action baixa o da rodada anterior antes de rodar. Na primeira execução, só grava o
estado, sem enviar nada, para o canal não receber uma enxurrada de mensagens.

    python3 scripts/alertas.py _site https://usuario.github.io/radar-fumaca/
"""
import json
import math
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ESTADO_ANTERIOR = DATA / "alertas.prev.json"
MANAUS = (-3.119, -60.0217)
MANAUS_TZ = timezone(timedelta(hours=-4))
OMS_PM25 = 15
RAIO_FOCO_KM = 50
HORA_RESUMO = 7  # 7h de Manaus

# faixas de PM2.5 da EPA, como no site; o alerta começa em "muito ruim"
FAIXAS = [(9, "bom"), (35.5, "moderado"), (55.5, "ruim para grupos sensíveis"), (125.5, "ruim"),
          (225.5, "muito ruim"), (math.inf, "perigoso")]
NIVEL_ALERTA = 4
# para descer de nível, precisa ficar 20% abaixo do limite: evita alternar a cada rodada
HISTERESE = 0.8
SETORES = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]


def env_key(name):
    import os
    key = os.environ.get(name, "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            k, _, value = line.partition("=")
            if k.strip() == name:
                key = value.strip().strip('"').strip("'")
    return key or None


def distance_km(lat1, lon1, lat2, lon2):
    rad = math.pi / 180
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) / 2 * rad)
    y = (lat2 - lat1) * rad
    return 6371 * math.hypot(x, y)


def direcao(lat1, lon1, lat2, lon2):
    x = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    graus = (math.degrees(math.atan2(x, lat2 - lat1)) + 360) % 360
    return SETORES[int(((graus + 22.5) % 360) // 45)]


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def nivel_com_histerese(pm25, nivel_anterior):
    nivel = next(i for i, (lim, _) in enumerate(FAIXAS) if pm25 < lim)
    if nivel_anterior is not None and nivel < nivel_anterior:
        # só desce se ficou bem abaixo do limite do nível anterior
        limite_inferior = FAIXAS[nivel_anterior - 1][0]
        if pm25 >= limite_inferior * HISTERESE:
            return nivel_anterior
    return nivel


def hora(minutos_utc):
    return datetime.fromtimestamp(minutos_utc * 60, MANAUS_TZ).strftime("%H:%M")


class Telegram:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, chat_id

    def _post(self, metodo, corpo, tipo):
        req = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{metodo}", data=corpo,
                                     headers={"Content-Type": tipo})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response).get("ok", False)
        except urllib.error.HTTPError as error:
            # a mensagem do Telegram ajuda a corrigir (ex.: bot sem permissão no canal); o token nunca é impresso
            print(f"Telegram recusou ({error.code}): {error.read().decode('utf-8', 'replace')[:200]}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            print(f"Telegram indisponível: {getattr(error, 'reason', error)}")
        return False

    def mensagem(self, html):
        corpo = json.dumps({"chat_id": self.chat_id, "text": html, "parse_mode": "HTML",
                            "disable_web_page_preview": True}).encode("utf-8")
        return self._post("sendMessage", corpo, "application/json")

    def foto(self, caminho, legenda_html):
        fronteira = uuid.uuid4().hex
        partes = []
        for nome, valor in (("chat_id", self.chat_id), ("caption", legenda_html), ("parse_mode", "HTML")):
            partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode("utf-8"))
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="photo"; filename="radar.jpg"\r\n'
                      f"Content-Type: image/jpeg\r\n\r\n".encode("utf-8") + Path(caminho).read_bytes() + b"\r\n")
        partes.append(f"--{fronteira}--\r\n".encode("utf-8"))
        return self._post("sendPhoto", b"".join(partes), f"multipart/form-data; boundary={fronteira}")


class Teste:
    def mensagem(self, html):
        print("---- mensagem ----\n" + html)
        return True

    def foto(self, caminho, legenda_html):
        print(f"---- foto ({caminho}) ----\n" + legenda_html)
        return True


def main():
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    site_url = sys.argv[2] if len(sys.argv) > 2 else "https://andrecavalcantii.github.io/radar-fumaca/"
    token, chat = env_key("TELEGRAM_BOT_TOKEN"), env_key("TELEGRAM_CHAT_ID")
    canal = Telegram(token, chat) if token and chat else Teste()
    if isinstance(canal, Teste):
        print("sem TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID: modo de teste, nada é enviado")

    agora = datetime.now(timezone.utc)
    agora_min = agora.timestamp() / 60
    anterior = load(ESTADO_ANTERIOR)
    primeira_vez = anterior is None
    estado = anterior or {}
    link = f'\n\n<a href="{escape(site_url)}">Ver no Radar da Fumaça</a>'

    # ---------- ar em Manaus (mediana dos sensores num raio de 25 km) ----------
    sensores = load(DATA / "sensores.json")
    perto = [s for s in (sensores or {}).get("sensores", []) if distance_km(*MANAUS, s["lat"], s["lon"]) <= 25]
    if len(perto) >= 3:
        v = sorted(s["pm25"] for s in perto)
        m = len(v) // 2
        mediana = v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2
        nivel_antes = estado.get("nivel_ar")
        nivel = nivel_com_histerese(mediana, nivel_antes)
        pior = max(perto, key=lambda s: s["pm25"])
        if not primeira_vez and nivel_antes is not None:
            if nivel >= NIVEL_ALERTA and nivel > nivel_antes:
                canal.mensagem(
                    f"⚠️ <b>Ar {FAIXAS[nivel][1]} em Manaus</b>\n"
                    f"PM2.5 de <b>{mediana:.0f} µg/m³</b> (mediana de {len(perto)} sensores), "
                    f"{mediana / OMS_PM25:.0f}× a referência diária da OMS. "
                    f"Pior ponto: {escape(pior['nome'])}, {pior['pm25']:.0f} µg/m³.\n"
                    "Evite atividades ao ar livre; se sair, use máscara PFF2." + link)
            elif nivel_antes >= NIVEL_ALERTA and nivel <= 2:
                canal.mensagem(
                    f"✅ <b>O ar melhorou em Manaus</b>\n"
                    f"PM2.5 de {mediana:.0f} µg/m³ (mediana de {len(perto)} sensores): {FAIXAS[nivel][1]}." + link)
        estado["nivel_ar"] = nivel
        estado["pm25"] = round(mediana, 1)

    # ---------- focos novos a menos de 50 km ----------
    focos = load(DATA / "focos.json")
    avisados = [a for a in estado.get("focos_avisados", []) if a[2] >= agora_min - 24 * 60]
    novos = []
    if focos:
        candidatos = []
        for f in focos["focos"]:
            if f[2] < agora_min - 6 * 60:  # só detecções recentes
                continue
            km = distance_km(*MANAUS, f[0], f[1])
            if km <= RAIO_FOCO_KM:
                candidatos.append((km, f))
        for km, f in sorted(candidatos, key=lambda c: c[0]):
            # mesmo fogo visto por outro satélite, ou já avisado nas últimas 24 h
            if any(distance_km(f[0], f[1], a[0], a[1]) < 5 for a in avisados + [[n[1][0], n[1][1]] for n in novos]):
                continue
            novos.append((km, f))
        if novos and not primeira_vez:
            linhas = [f"• <b>{km:.0f} km</b> a {direcao(*MANAUS, f[0], f[1])} · {escape(focos['municipios'][f[3]]['nome'])} · {hora(f[2])}"
                      for km, f in novos[:5]]
            extra = f"\n… e mais {len(novos) - 5}" if len(novos) > 5 else ""
            titulo = "🔥 <b>Foco ativo perto de Manaus</b>" if len(novos) == 1 else f"🔥 <b>{len(novos)} focos ativos perto de Manaus</b>"
            canal.mensagem(titulo + f" (menos de {RAIO_FOCO_KM} km)\n" + "\n".join(linhas) + extra +
                           "\nDetecção por satélite (NASA FIRMS). Em caso de incêndio, ligue 193." + link)
        avisados += [[round(f[0], 4), round(f[1], 4), f[2]] for _, f in novos]
    estado["focos_avisados"] = avisados

    # ---------- resumo da manhã, às 7h de Manaus ----------
    local = agora.astimezone(MANAUS_TZ)
    hoje = local.strftime("%Y-%m-%d")
    if local.hour == HORA_RESUMO and estado.get("resumo_em") != hoje and not primeira_vez:
        og = site / "og.jpg"
        descricao = ""
        try:
            import re
            html = (site / "index.html").read_text(encoding="utf-8")
            achado = re.search(r'<meta property="og:description" content="([^"]*)"', html)
            descricao = achado.group(1) if achado else ""
        except OSError:
            pass
        legenda = "☀️ <b>Bom dia, Manaus. Como está o ar hoje</b>\n" + descricao + link
        enviado = canal.foto(og, legenda) if og.exists() else canal.mensagem(legenda)
        if enviado:
            estado["resumo_em"] = hoje
    elif primeira_vez and local.hour == HORA_RESUMO:
        estado["resumo_em"] = hoje

    estado["atualizado_em"] = agora.isoformat(timespec="minutes")
    saida = site / "data" / "alertas.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(estado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(("primeira execução: só gravei o estado. " if primeira_vez else "") +
          f"ar nível {estado.get('nivel_ar')} ({estado.get('pm25')} µg/m³), {len(novos)} foco(s) novo(s) a menos de {RAIO_FOCO_KM} km")


if __name__ == "__main__":
    main()
