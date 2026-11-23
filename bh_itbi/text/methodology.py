"""User-visible Portuguese copy."""

from __future__ import annotations

from bh_itbi import config as cfg
from bh_itbi.formatting import (
    number,
    number_word,
)

METHODOLOGY_SUMMARY = "Dados, critérios e limites de interpretação"
METHODOLOGY_OBSERVED_HEADING = "O que é observado"
METHODOLOGY_OBSERVED_P1 = (
    "Valores declarados à autoridade tributária na data de pagamento do ITBI. "
    "A fonte de BH não distingue a natureza da transferência; "
    "os registros não podem ser tratados como vendas de mercado verificadas."
)
METHODOLOGY_OBSERVED_P2 = (
    "Apartamentos e casas sem sinalização em value_flag e com valor nominal "
    f"entre R$ {number(cfg.PRICE_PER_M2_MIN)} e R$ {number(cfg.PRICE_PER_M2_MAX)}/m², "
    "inclusive. As contagens do painel são de registros elegíveis, não de todo o ITBI. "
    f"Medianas do resumo e distribuições exigem ao menos {number_word(cfg.SUMMARY_MINIMUM)} "
    "observações."
)
METHODOLOGY_TIME_HEADING = "Tempo, moeda e dispersão"
METHODOLOGY_TIME_P1 = (
    f"Janela de exploração: {cfg.START_YEAR}–{cfg.END_YEAR}, como nas séries do notebook. "
    f"Valores reais vêm da própria fonte, corrigidos pelo IPCA para {cfg.IPCA_BASE}; "
    "não são recalculados no painel. Valores nominais de vários anos não descontam a inflação."
)
METHODOLOGY_TIME_P2 = (
    "Quartis usam interpolação linear do pandas. "
    "Períodos sem amostra suficiente permanecem como lacunas; "
    "P25–P75 não é um intervalo de confiança. "
    "O diagnóstico exige também área construída positiva."
)
METHODOLOGY_GEO_HEADING = "Geografia e proveniência"
METHODOLOGY_GEO_P1 = (
    f"O mapa mostra até {number(cfg.MAP_SAMPLE_SIZE)} registros com área positiva "
    "e centroide de face, após restringir o valor real por m² (IPCA) "
    f"aos limites fixos P{cfg.MAP_LOWER_PERCENTILE}–P{cfg.MAP_UPPER_PERCENTILE} "
    f"desses registros no período completo de {cfg.START_YEAR}–{cfg.END_YEAR}. "
    "Centroides de CEP e bairro não "
    "entram no mapa. Não há deslocamento artificial dos pontos. "
    "Os resumos e as séries usam todos os registros elegíveis, "
    "independentemente da amostra desenhada."
)
METHODOLOGY_GEO_P2_PREFIX = (
    f"Fonte: Prefeitura de Belo Horizonte, dados abertos. Tratamento: {cfg.REPO_ID}. "
    "Licença dos dados de BH: CC-BY. Trabalho derivado e não oficial. "
)
METHODOLOGY_DICTIONARY_LINK = "Dicionário e limitações"
METHODOLOGY_VERSION_LINK = "Versão da fonte"
FOOTER_BRAND = "Mercado Residencial de Belo Horizonte"
FOOTER_PROVENANCE = (
    "Fonte: Prefeitura de Belo Horizonte, dados abertos. "
    f"Tratamento: {cfg.REPO_ID} (Hugging Face). Trabalho derivado e não oficial."
)
FOOTER_SOURCE_LINK = "Consultar a fonte"
