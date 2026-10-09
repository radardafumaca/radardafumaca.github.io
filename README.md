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
- `scripts/build_municipios.py` gera `data/municipios.json` (limites dos municípios do raio) e `data/cidades.json` (sedes, para os nomes no mapa). Só precisa rodar de novo se o raio mudar.
- O mesmo `update_data.py` busca, numa grade de 8 × 8 pontos sobre a região, vento (junto ao solo e a ~1,5 km), temperatura e qualidade do ar, e grava `data/grade.json`. A página usa a grade para as correntes de vento e para as camadas de cor de temperatura e de qualidade do ar. São ~6.100 consultas por dia à Open-Meteo, abaixo do limite gratuito.
- `index.html` é um site estático: desenha o mapa e os focos com MapLibre GL (na placa de vídeo) e busca qualidade do ar (PM2.5, AQI) e vento ao vivo na Open-Meteo.
- O índice "municípios que mais mandam fumaça" soma os focos de cada município, pesando pela distância até Manaus e pelo alinhamento com a direção do vento das últimas 6 h. É uma estimativa relativa, não uma medição.
- `.github/workflows/update-data.yml` roda a cada 30 minutos no GitHub: baixa os focos e publica o site no GitHub Pages. O `data/focos.json` não vai para o git; ele é gerado na hora, localmente ou pela Action.

- Sensores: a cada rodada, `update_data.py` busca os sensores PurpleAir da região (chave `PURPLEAIR_KEY`), corrige o PM2.5 pela fórmula da EPA para fumaça e grava `data/sensores.json`. A mediana dos sensores de Manaus vai para `data/historico.json` (7 dias); se o histórico tiver menos de 48 h, as horas que faltam vêm da API de histórico da PurpleAir.

## Publicação

O site fica no GitHub Pages, publicado pela Action (que também reativa a própria rotina agendada antes de o GitHub desligá-la por inatividade, aos 60 dias sem commit) (em Settings → Pages, a fonte é "GitHub Actions"). A chave da FIRMS vai no secret `FIRMS_MAP_KEY` do repositório.

## Fontes

- Focos de calor: NASA FIRMS
- Dias sem chuva e risco de fogo: INPE, Programa Queimadas
- Limites dos municípios: IBGE
- Sedes dos municípios: kelvins/municipios-brasileiros (MIT)
- Vento, temperatura e qualidade do ar em grade: Open-Meteo
- Letras do mapa: OpenFreeMap
- Qualidade do ar e clima: Open-Meteo (modelo CAMS, Copernicus)
- Mapa: Esri (World Light/Dark Gray Canvas), com dados do OpenStreetMap
