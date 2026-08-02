# DataLens — Árvore de arquivos

Cada arquivo já vem com um comentário simples dizendo **o que deve conter** (a ideia extraída do
ROTEIRO.md) — **sem código**. Você vai preenchendo o conteúdo real fase por fase, seguindo o
`ROTEIRO.md`. A coluna "Fase" indica quando cada arquivo entra.

```
datalens/
├── README.md                         # vitrine do projeto no GitHub            (Fase 5)
├── ROTEIRO.md                        # o roteiro de estudo completo (preenchido)
├── ARVORE.md                         # este mapa
├── requirements.txt                  # lista de dependências (nomes das libs)   (Fase 4)
├── .gitignore                        # o que o Git deve ignorar                 (Fase 4)
├── config/
│   ├── config.example.yaml           # exemplo de config: fonte + colunas + perfil (Fase 1/3)
│   └── README.md                     # explica cada campo da config
├── data/
│   ├── .gitkeep
│   └── exemplos/
│       ├── financas.db               # banco SQLite: ativos + cotações + indicadores (Fase 1)
│       ├── acoes_b3.csv              # dataset estrela: ações B3 (PETR4/VALE3)   (Fase 1)
│       ├── acoes_eua.csv             # ações EUA (Apple/Tesla)                   (Fase 1)
│       ├── cripto.csv                # vitrine: cripto                           (Fase 3)
│       ├── financas_pessoais.xlsx    # vitrine: planilha "suja" p/ limpeza       (Fase 2)
│       └── README.md                 # origem de cada dataset
├── scripts/
│   └── baixar_dados.py               # baixa os dados públicos e monta financas.db (Fase 1)
├── src/
│   └── datalens/
│       ├── __init__.py
│       ├── config_loader.py          # lê o YAML, aplica defaults, valida        (Fase 3)
│       ├── detector.py               # auto-detecta o tipo de cada coluna        (Fase 2)
│       ├── limpeza.py                # data cleaning (faltantes/duplicados)      (Fase 2)
│       ├── perfil.py                 # ★ CORAÇÃO: perfil automático (v1)         (Fase 3)
│       ├── graficos.py               # gráficos do perfil (plotly)              (Fase 3)
│       ├── relatorio.py              # monta o relatório HTML exportável         (Fase 4)
│       ├── estatistica.py            # correlações/tendências (v2)              (Fase 5)
│       └── conectores/
│           ├── __init__.py
│           ├── base.py               # ★ contrato comum: carregar() -> dados     (Fase 1)
│           ├── csv_conector.py       # lê CSV                                     (Fase 2)
│           ├── excel_conector.py     # lê Excel (.xlsx)                          (Fase 2)
│           ├── sql_conector.py       # roda a QUERY do usuário no banco          (Fase 1)
│           └── api_conector.py       # puxa dados de uma API (JSON)              (Fase 3)
├── app/
│   └── streamlit_app.py              # ★ a interface pública (deploy grátis)     (Fase 4)
├── notebooks/
│   ├── 01_exploracao_sql.ipynb       # rascunho de análise em SQL                (Fase 1)
│   ├── 02_pandas_exploracao.ipynb    # rascunho de análise em pandas             (Fase 3)
│   └── README.md
├── tests/
│   ├── __init__.py
│   ├── test_conectores.py            # testes dos conectores                     (Fase 5)
│   ├── test_perfil.py                # testes do perfil                          (Fase 5)
│   └── README.md
└── docs/
    ├── arquitetura.md                # o fluxo do sistema explicado              (Fase 1)
    ├── decisoes.md                   # as decisões de design (ADR simples)       (Fase 1)
    └── screenshots/                  # prints do app para o README              (Fase 4)
```

★ = peças centrais do projeto.
