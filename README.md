# Painel do Mercado Residencial de Belo Horizonte

Projeto em desenvolvimento.

Painel interativo para exploração de dados de transações imobiliárias de Belo Horizonte, utilizando Python, Dash e Plotly.

## Como executar

É necessário ter o [uv](https://docs.astral.sh/uv/) instalado.

```bash
uv sync --frozen
uv run python main.py prepare
uv run python main.py
```

Depois, acesse http://127.0.0.1:8050 no navegador.

## Dados

Fonte: [pracadata/brazil-itbi](https://huggingface.co/datasets/pracadata/brazil-itbi), a partir de dados abertos da Prefeitura de Belo Horizonte.
