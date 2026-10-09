"""Gera a prévia do link (WhatsApp, redes) com os números do momento.

Cria <site>/og.jpg (1200 x 630) e preenche as etiquetas og:* de <site>/index.html.
O WhatsApp não roda JavaScript: título, descrição e imagem precisam estar no HTML.

    python3 scripts/build_preview.py _site https://usuario.github.io/radar-fumaca/
"""
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FONTS = ROOT / "assets" / "fonts"
MANAUS = (-3.119, -60.0217)
MANAUS_TZ = timezone(timedelta(hours=-4))  # sem horário de verão
OMS_PM25 = 15
W, H = 1200, 630

# cores do tema escuro do site
GROUND = (21, 25, 24)
SURFACE = (29, 35, 33)
INK = (231, 235, 232)
MUTED = (151, 163, 158)
LINE = (55, 64, 61)
EMBER = (240, 122, 62)
AGE_COLORS = [(255, 90, 67), (255, 146, 43), (255, 208, 138), (138, 130, 112)]
# faixas de PM2.5 da EPA (as mesmas do site)
BANDS = [(9, (64, 192, 87), "bom"), (35.5, (252, 196, 25), "moderado"), (55.5, (255, 146, 43), "ruim p/ sensíveis"),
         (125.5, (240, 62, 62), "ruim"), (225.5, (174, 62, 201), "muito ruim"), (math.inf, (134, 46, 58), "perigoso")]


def distance_km(lat1, lon1, lat2, lon2):
    rad = math.pi / 180
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) / 2 * rad)
    y = (lat2 - lat1) * rad
    return 6371 * math.hypot(x, y)


def load(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def band(v):
    return next(b for b in BANDS if v < b[0])


def fmt_int(n):
    return f"{n:,}".replace(",", ".")


def resumo():
    """Números do momento, a partir dos mesmos arquivos que a página usa."""
    agora = datetime.now(timezone.utc)
    r = {"quando": agora}
    sensores = load("sensores.json")
    if sensores:
        perto = [s["pm25"] for s in sensores["sensores"] if distance_km(*MANAUS, s["lat"], s["lon"]) <= 25]
        if len(perto) >= 3:
            v = sorted(perto)
            m = len(v) // 2
            r["pm25"] = v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2
            r["n_sensores"] = len(v)
            r["quando"] = datetime.fromisoformat(sensores["atualizado_em"])
    focos = load("focos.json")
    if focos:
        # últimas 24 h contra as 24 h anteriores: "hoje" logo depois da meia-noite daria zero focos
        agora_min = agora.timestamp() / 60
        hoje_n = ontem_n = 0
        mais_perto = None
        for f in focos["focos"]:
            idade_h = (agora_min - f[2]) / 60
            if idade_h <= 24:
                hoje_n += 1
            elif idade_h <= 48:
                ontem_n += 1
            if f[2] >= agora_min - 12 * 60:
                km = distance_km(*MANAUS, f[0], f[1])
                if not mais_perto or km < mais_perto[0]:
                    mais_perto = (km, focos["municipios"][f[3]]["nome"])
        r.update(focos_hoje=hoje_n, focos_ontem=ontem_n, foco_perto=mais_perto, focos=focos)
    return r


def textos(r):
    quando = r["quando"].astimezone(MANAUS_TZ).strftime("%d/%m às %H:%M")
    partes = []
    if "pm25" in r:
        b = band(r["pm25"])
        partes.append(f"Ar agora: {r['pm25']:.0f} µg/m³ de PM2.5 ({b[2]}, mediana de {r['n_sensores']} sensores), "
                      f"{r['pm25'] / OMS_PM25:.0f}× a referência da OMS.")
    if r.get("foco_perto"):
        km, nome = r["foco_perto"]
        partes.append(f"Foco ativo a {km:.0f} km de Manaus ({nome})." if km <= 100 else "Nenhum foco a menos de 100 km.")
    if "focos_hoje" in r:
        partes.append(f"{fmt_int(r['focos_hoje'])} focos nas últimas 24 h na região.")
    partes.append(f"Dados de {quando} (hora de Manaus).")
    titulo = "Radar da Fumaça · Manaus"
    if "pm25" in r:
        titulo = f"Radar da Fumaça · ar {band(r['pm25'])[2]} em Manaus"
    return titulo, " ".join(partes)


def fonte(nome, tamanho, peso=None):
    f = ImageFont.truetype(str(FONTS / nome), tamanho)
    if peso:
        try:
            f.set_variation_by_axes([peso])
        except (OSError, AttributeError):
            pass
    return f


def imagem(r, destino):
    img = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(img)
    display = lambda s: fonte("BarlowCondensed-Bold.ttf", s)
    body = lambda s, w=400: fonte("PublicSans-Variable.ttf", s, w)

    # radar à direita: anéis de distância e focos das últimas 24 h em volta de Manaus
    cx, cy, raio = 905, 330, 255
    k = raio / 300
    coslat = math.cos(math.radians(MANAUS[0]))
    d.rectangle([640, 0, W, H], fill=SURFACE)
    for km in (50, 100, 200, 300):
        rr = km * k
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=LINE, width=2)
    d.text((cx + 6, cy - 300 * k - 22), "300 km", font=body(15), fill=MUTED)
    if r.get("focos"):
        agora_min = datetime.now(timezone.utc).timestamp() / 60
        focos = [f for f in r["focos"]["focos"] if f[2] >= agora_min - 24 * 60]
        for f in sorted(focos, key=lambda f: f[2]):  # recentes por cima
            x = cx + (f[1] - MANAUS[1]) * coslat * 111.2 * k
            y = cy - (f[0] - MANAUS[0]) * 111.2 * k
            idade = (agora_min - f[2]) / 60
            cor = AGE_COLORS[0 if idade < 6 else 1 if idade < 24 else 2]
            d.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=cor)
    d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=GROUND, outline=INK, width=3)
    # contorno escuro: o nome fica legível mesmo sobre os pontos de fogo
    d.text((cx + 14, cy - 2), "Manaus", font=body(22, 650), fill=INK, anchor="lm", stroke_width=4, stroke_fill=SURFACE)

    # título
    x0 = 60
    d.text((x0, 52), "RADAR DA", font=display(56), fill=INK)
    w_radar = d.textlength("RADAR DA ", font=display(56))
    d.text((x0 + w_radar, 52), "FUMAÇA", font=display(56), fill=EMBER)
    d.text((x0, 118), "Manaus · qualidade do ar e focos de incêndio", font=body(24), fill=MUTED)

    # número principal
    y = 178
    if "pm25" in r:
        b = band(r["pm25"])
        valor = f"{r['pm25']:.0f}"
        d.text((x0 - 6, y - 30), valor, font=display(200), fill=INK)
        w_val = d.textlength(valor, font=display(200))
        d.text((x0 + w_val + 10, y + 70), "µg/m³", font=body(26, 500), fill=MUTED)
        d.text((x0 + w_val + 10, y + 102), "PM2.5 agora", font=body(26, 500), fill=MUTED)
        rotulo = f"{b[2].upper()} · {r['pm25'] / OMS_PM25:.0f}× O LIMITE DA OMS"
        tf = body(22, 700)
        tw = d.textlength(rotulo, font=tf)
        d.rounded_rectangle([x0, y + 196, x0 + tw + 36, y + 240], radius=22, fill=b[1])
        texto_cor = (255, 255, 255) if r["pm25"] >= 55.5 else (27, 34, 32)
        d.text((x0 + 18, y + 218), rotulo, font=tf, fill=texto_cor, anchor="lm")
        y += 270
    else:
        d.text((x0, y + 20), "Qualidade do ar indisponível agora", font=body(30, 600), fill=INK)
        y += 90

    # focos
    if r.get("foco_perto") and r["foco_perto"][0] <= 100:
        km, nome = r["foco_perto"]
        d.ellipse([x0, y + 9, x0 + 16, y + 25], fill=AGE_COLORS[0])
        texto = f"Foco ativo a {km:.0f} km de Manaus · {nome}"
        tamanho = 27
        while d.textlength(texto, font=body(tamanho, 600)) > 640 - x0 - 28 - 24 and tamanho > 18:
            tamanho -= 1
        d.text((x0 + 28, y), texto, font=body(tamanho, 600), fill=INK)
        y += 46
    if "focos_hoje" in r:
        linha = f"{fmt_int(r['focos_hoje'])} focos em 24 h na região"
        if r.get("focos_ontem"):
            pct = round((r["focos_hoje"] - r["focos_ontem"]) / r["focos_ontem"] * 100)
            if abs(pct) >= 10:
                linha += f" ({'+' if pct > 0 else ''}{pct}%)"
        # não pode invadir o radar (que começa em x = 640)
        tamanho = 24
        while d.textlength(linha, font=body(tamanho)) > 640 - x0 - 24 and tamanho > 16:
            tamanho -= 1
        d.text((x0, y), linha, font=body(tamanho), fill=MUTED)

    quando = r["quando"].astimezone(MANAUS_TZ).strftime("%d/%m às %H:%M")
    d.text((x0, H - 52), f"Atualizado em {quando} (hora de Manaus)", font=body(19), fill=MUTED)
    img.save(destino, "JPEG", quality=86, optimize=True, progressive=True)


def preencher(html_path, site_url, titulo, descricao, versao):
    html = html_path.read_text(encoding="utf-8")
    valores = {
        "og:title": titulo,
        "og:description": descricao,
        "og:url": site_url,
        # o horário no endereço faz o WhatsApp buscar a imagem nova quando relê a página
        "og:image": f"{site_url}og.jpg?v={versao}",
        "og:image:alt": descricao,
        "twitter:title": titulo,
        "twitter:description": descricao,
        "twitter:image": f"{site_url}og.jpg?v={versao}",
        "description": descricao,
    }
    for chave, valor in valores.items():
        padrao = re.compile(r'(<meta (?:property|name)="' + re.escape(chave) + r'" content=")[^"]*(")')
        html, n = padrao.subn(lambda m: m.group(1) + escape(valor, quote=True) + m.group(2), html, count=1)
        if not n:
            print(f"etiqueta {chave} não encontrada no HTML")
    # endereço oficial da página (o Google usa para não tratar o antigo e o novo como páginas diferentes)
    html = re.sub(r'(<link rel="canonical" href=")[^"]*(")', lambda m: m.group(1) + escape(site_url, quote=True) + m.group(2), html, count=1)
    html_path.write_text(html, encoding="utf-8")


def main():
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    site_url = sys.argv[2] if len(sys.argv) > 2 else "https://andrecavalcantii.github.io/radar-fumaca/"
    if not site_url.endswith("/"):
        site_url += "/"
    r = resumo()
    titulo, descricao = textos(r)
    imagem(r, site / "og.jpg")
    versao = r["quando"].strftime("%Y%m%d%H%M")
    preencher(site / "index.html", site_url, titulo, descricao, versao)
    print(f"prévia: {titulo} | {descricao} ({(site / 'og.jpg').stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
