# Painel do Mercado Residencial de Belo Horizonte

![Python](https://img.shields.io/badge/Python-22313a?style=flat&logo=python&logoColor=f7f4ee)
![Dash](https://img.shields.io/badge/Dash-1d6f73?style=flat&logo=dash&logoColor=f7f4ee)
![Plotly](https://img.shields.io/badge/Plotly-22313a?style=flat&logo=plotly&logoColor=f7f4ee)

Mapas, distribuições e índices para explorar o mercado residencial de Belo Horizonte entre 2016 e 2025, a partir dos registros de ITBI da Prefeitura de Belo Horizonte. Filtros interativos permitem definir recortes no panorama e nos diagnósticos e compartilhar a seleção por link.

**[Acessar o painel interativo](https://bh-itbi-dashboard.onrender.com/)**

![Panorama com filtros, indicadores, mapa do valor nominal por m², histograma do valor real por m², séries mensais, distribuições por bairro e trajetórias trimestrais.](docs/images/panorama.png)

*Panorama dos valores declarados de apartamentos e casas no recorte padrão, com mapa, distribuições, séries mensais e trajetórias por bairro.*

![Índice hedônico em verde-petróleo com intervalo de confiança de 95%, média geométrica bruta pontilhada e faixas de composição por bairro, área, idade e tipo.](docs/images/indice-hedonico.png)

*Índice hedônico, média geométrica bruta e decomposição da diferença por característica observada na amostra de apartamentos e casas (1º tri. 2016 = 100).*

## Executar localmente

Com o [uv](https://docs.astral.sh/uv/) instalado, na pasta do projeto:

```bash
uv sync --frozen
uv run python main.py prepare
uv run python main.py
```

Acesse [http://127.0.0.1:8050/](http://127.0.0.1:8050/) no navegador.

## Dados

Os dados são provenientes dos registros oficiais de ITBI da Prefeitura de Belo Horizonte (CC BY 4.0), tratados e disponibilizados no conjunto de dados [pracadata/brazil-itbi](https://huggingface.co/datasets/pracadata/brazil-itbi), no Hugging Face.

O código do projeto é disponibilizado sob a licença MIT.
