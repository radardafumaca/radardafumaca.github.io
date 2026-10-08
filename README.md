# Radar da Fumaça

Mapa dos focos de calor num raio de 300 km de Manaus, qualidade do ar na cidade agora e de onde a fumaça está vindo.

## Como rodar

```
python3 scripts/update_data.py   # baixa os focos do INPE e gera data/focos.json
python3 -m http.server 8765      # abra http://localhost:8765
```

A página precisa ser aberta por um servidor (não pelo arquivo direto), porque carrega `data/focos.json`.

## Como funciona

- `scripts/update_data.py` baixa os arquivos diários de focos do INPE (Programa Queimadas), mantém só os das últimas 48 h dentro do raio e gera um JSON pequeno. Usa só a biblioteca padrão do Python.
- `index.html` é um site estático: desenha os focos com Leaflet e busca qualidade do ar (PM2.5, AQI) e vento ao vivo na Open-Meteo.
- O índice "municípios que mais mandam fumaça" soma os focos de cada município, pesando pela distância até Manaus e pelo alinhamento com a direção do vento das últimas 6 h. É uma estimativa relativa, não uma medição.
- `.github/workflows/update-data.yml` atualiza `data/focos.json` a cada 30 minutos quando o projeto estiver no GitHub.

## Publicar

Qualquer hospedagem de site estático serve (GitHub Pages, Vercel, Netlify). Com o repositório no GitHub, a Action mantém os dados atualizados e cada commit dela republica o site.

## Fontes

- Focos de calor: INPE, Programa Queimadas
- Qualidade do ar e clima: Open-Meteo (modelo CAMS, Copernicus)
- Mapa: OpenStreetMap e CARTO
