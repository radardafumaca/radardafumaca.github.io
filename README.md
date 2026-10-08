# Radar da Fumaça

Mapa dos focos de calor num raio de 300 km de Manaus, qualidade do ar na cidade agora e de onde a fumaça está vindo.

## Como rodar

```
python3 scripts/update_data.py   # baixa os focos da NASA FIRMS e gera data/focos.json
python3 -m http.server 8765      # abra http://localhost:8765
```

A página precisa ser aberta por um servidor (não pelo arquivo direto), porque carrega `data/focos.json`.

## Como funciona

- `scripts/update_data.py` baixa os arquivos abertos de 48 h da NASA FIRMS (VIIRS dos satélites Suomi NPP, NOAA-20 e NOAA-21, e MODIS), mantém os focos dentro do raio, descarta os de baixa confiança e descobre o município de cada um pelos limites do IBGE. Do INPE vêm os dias sem chuva e o risco de fogo por município. Usa só a biblioteca padrão do Python.
- `scripts/build_municipios.py` gera `data/municipios.json` com os limites dos municípios do raio. Só precisa rodar de novo se o raio mudar.
- `index.html` é um site estático: desenha os focos com Leaflet e busca qualidade do ar (PM2.5, AQI) e vento ao vivo na Open-Meteo.
- O índice "municípios que mais mandam fumaça" soma os focos de cada município, pesando pela distância até Manaus e pelo alinhamento com a direção do vento das últimas 6 h. É uma estimativa relativa, não uma medição.
- `.github/workflows/update-data.yml` atualiza `data/focos.json` a cada 30 minutos quando o projeto estiver no GitHub.

## Publicar

Qualquer hospedagem de site estático serve (GitHub Pages, Vercel, Netlify). Com o repositório no GitHub, a Action mantém os dados atualizados e cada commit dela republica o site.

## Fontes

- Focos de calor: NASA FIRMS
- Dias sem chuva e risco de fogo: INPE, Programa Queimadas
- Limites dos municípios: IBGE
- Qualidade do ar e clima: Open-Meteo (modelo CAMS, Copernicus)
- Mapa: OpenStreetMap e CARTO
