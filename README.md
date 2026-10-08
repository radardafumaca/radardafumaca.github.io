# Radar da Fumaça

Mapa dos focos de calor num raio de 300 km de Manaus, qualidade do ar na cidade agora e de onde a fumaça está vindo.

## Como rodar

```
python3 scripts/update_data.py   # baixa os focos da NASA FIRMS e gera data/focos.json
python3 -m http.server 8765      # abra http://localhost:8765
```

Com uma chave da FIRMS (grátis em https://firms.modaps.eosdis.nasa.gov/api/map_key/), crie um `.env` com `FIRMS_MAP_KEY=sua_chave`: o script passa a usar a API, baixa só a região e busca 5 dias em vez de 48 h. No GitHub, cadastre a chave como secret `FIRMS_MAP_KEY`. O `.env` está no `.gitignore`.

A página precisa ser aberta por um servidor (não pelo arquivo direto), porque carrega `data/focos.json`.

## Como funciona

- `scripts/update_data.py` baixa os arquivos abertos de 48 h da NASA FIRMS (VIIRS dos satélites Suomi NPP, NOAA-20 e NOAA-21, e MODIS), mantém os focos dentro do raio, descarta os de baixa confiança e descobre o município de cada um pelos limites do IBGE. Do INPE vêm os dias sem chuva e o risco de fogo por município. Usa só a biblioteca padrão do Python.
- `scripts/build_municipios.py` gera `data/municipios.json` com os limites dos municípios do raio. Só precisa rodar de novo se o raio mudar.
- `index.html` é um site estático: desenha os focos com Leaflet e busca qualidade do ar (PM2.5, AQI) e vento ao vivo na Open-Meteo.
- O índice "municípios que mais mandam fumaça" soma os focos de cada município, pesando pela distância até Manaus e pelo alinhamento com a direção do vento das últimas 6 h. É uma estimativa relativa, não uma medição.
- `.github/workflows/update-data.yml` roda a cada 30 minutos no GitHub: baixa os focos e publica o site no GitHub Pages. O `data/focos.json` não vai para o git; ele é gerado na hora, localmente ou pela Action.

## Publicação

O site fica no GitHub Pages, publicado pela Action (em Settings → Pages, a fonte é "GitHub Actions"). A chave da FIRMS vai no secret `FIRMS_MAP_KEY` do repositório.

## Fontes

- Focos de calor: NASA FIRMS
- Dias sem chuva e risco de fogo: INPE, Programa Queimadas
- Limites dos municípios: IBGE
- Qualidade do ar e clima: Open-Meteo (modelo CAMS, Copernicus)
- Mapa: Esri (World Light/Dark Gray Canvas), com dados do OpenStreetMap
