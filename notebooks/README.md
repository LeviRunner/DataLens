# .private_docs — material de estudo (fora do repositorio)

Esta pasta inteira esta no `.gitignore`. Nada aqui vai para o GitHub: e o andaime do
aprendizado, nao o produto. O que vira produto mora em `src/`, `tests/` e `notebooks/`.

Tres pastas `test_*`, cada uma com um proposito diferente:

| Pasta | O que e | O que fazer com o conteudo |
|---|---|---|
| `test_model/` | Rascunho comentado de cada modulo de `src/datalens/connectors/`. | Ler e **digitar a mao** no arquivo real. Nao importar, nao executar. |
| `test_query/` | Exercicios de SQL por dia (`query/D2` … `D7`) e as exploracoes com print. | Resolver sem olhar o gabarito, depois conferir. |
| `test_import/` | Scripts soltos de experimentacao com pandas, SQLAlchemy e Streamlit. | Rodar direto (`python arquivo.py`) para testar uma ideia. |

## Por que os rascunhos ficam aqui, e nao em `tests/`

`tests/` e para pytest de verdade — o que roda no CI e prova que o codigo funciona.
Os arquivos de `test_model/` sao **copias do modulo**, nao testes: se estivessem em
`tests/`, o pytest tentaria coleta-los, e um rascunho pela metade deixaria a suite
vermelha sem nenhum teste real ter falhado. O `pytest.ini` na raiz fixa
`testpaths = tests` justamente para isolar as duas coisas.

## Estado atual dos rascunhos

Alinhados com o `base.py` real, ja em ingles:
`ConnectorError`, `Connector`, `load()`, `validate_path()`.
