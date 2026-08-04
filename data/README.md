# Datasets de exemplo

Catálogo dos dados de demonstração do DataLens: de onde vêm, o que representam e como
reproduzir. Todos são **públicos e gratuitos**, obtidos sem chave de API.

Servem para provar que o mesmo motor lê dados bem diferentes (banco SQL, CSV, Excel, API).

---

## Arquivos

| Arquivo | Conteúdo | Fase |
|---|---|---|
| `financas.db` | Banco SQLite: ações da B3 + EUA e indicadores do Banco Central | 1 |
| `acoes_b3.csv` | Cotações diárias de 6 ações da B3 (mesmos dados do banco) | 1 |
| `acoes_eua.csv` | Cotações diárias de 6 ações dos EUA (mesmos dados do banco) | 1 |
| `cripto.csv` | *(placeholder)* vitrine de cripto | 3 |
| `financas_pessoais.xlsx` | *(placeholder)* planilha "suja" para o pipeline de limpeza | 2 |

---

## Fontes

### 1. Yahoo Finance — cotações de ações

- **Endpoint:** `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=&period2=&interval=1d`
- **Chave de API:** não exige.
- **Formato:** JSON (`timestamp[]` + `indicators.quote[0]` com open/high/low/close/volume).
- **Uso:** dados de mercado, para fins pessoais e de estudo. Não redistribuir como produto.
- **Observações:**
  - Exige cabeçalho `User-Agent` de navegador; sem ele a requisição é recusada.
  - Dias sem pregão vêm com valores nulos e são **descartados** no download — o banco não
    contém linha inventada para feriado.
  - Preços **não** são ajustados por proventos (dividendos/desdobramentos). Para análise de
    retorno de longo prazo isso importa; para o objetivo aqui (praticar SQL e perfilar dados)
    não atrapalha. Fica registrado como limitação conhecida.

### 2. Banco Central do Brasil — API SGS (Sistema Gerenciador de Séries Temporais)

- **Endpoint:** `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json`
- **Chave de API:** não exige.
- **Licença:** dado público (Lei de Acesso à Informação).
- **Séries baixadas:**

| Código | Série | Unidade | Frequência |
|---|---|---|---|
| 1 | Dólar comercial (venda) | BRL/USD | diária |
| 11 | Taxa Selic | % ao dia | diária |
| 433 | IPCA | % ao mês | mensal |

---

## Esquema do banco (`financas.db`)

Quatro tabelas — duas dimensões e dois fatos. É essa separação que dá assunto para os JOINs:
`cotacoes` sozinha não responde "qual setor rendeu mais?", só `cotacoes` + `ativos` responde.

```
ativos                          cotacoes
------                          --------
ticker  TEXT PK  <------------- ticker      TEXT FK
nome    TEXT                    data        TEXT (ISO: aaaa-mm-dd)
tipo    TEXT                    abertura    REAL
pais    TEXT                    maxima      REAL
moeda   TEXT                    minima      REAL
setor   TEXT                    fechamento  REAL NOT NULL
bolsa   TEXT                    volume      INTEGER
                                PK (ticker, data)

series                          indicadores
------                          -----------
codigo     INTEGER PK <-------- codigo  INTEGER FK
nome       TEXT                 data    TEXT (ISO)
unidade    TEXT                 valor   REAL NOT NULL
frequencia TEXT                 PK (codigo, data)
```

Notas de modelagem:

- **Datas em texto ISO (`aaaa-mm-dd`)** porque SQLite não tem tipo `DATE` nativo. O formato ISO
  ordena corretamente como string e é o que as funções de data do SQLite esperam.
- **Chave primária composta** em `cotacoes` e `indicadores`: impede a mesma data duplicada para
  o mesmo ativo se o script rodar duas vezes.
- Índices em `cotacoes(data)` e `indicadores(data)` — filtro por período é a consulta mais comum.

**Ativos incluídos:** PETR4, VALE3, ITUB4, BBAS3, ABEV3, MGLU3 (B3);
AAPL, MSFT, NVDA, TSLA, AMZN, KO (NASDAQ/NYSE).

---

## Como reproduzir / atualizar

```bash
python scripts/download_data.py            # 2 anos de histórico (padrão)
python scripts/download_data.py --anos 5   # período maior
```

O script recria as tabelas do zero a cada execução (é idempotente) e regrava os dois CSVs a
partir dos mesmos dados. Usa só a biblioteca padrão do Python — roda antes mesmo de instalar
o `requirements.txt`.

Como as APIs são consultadas ao vivo, o intervalo de datas muda conforme o dia da execução.
O conteúdo atual foi baixado em **02/08/2026**, cobrindo **2024-08-02 a 2026-07-31**
(5.988 cotações e 1.027 observações de indicadores).

---

## Como abrir

**DBeaver:** Nova conexão → SQLite → apontar para `data/exemplos/financas.db`.

**Linha de comando** (sem instalar nada, via Python):

```bash
python -c "import sqlite3; c=sqlite3.connect('data/exemplos/financas.db'); print(c.execute('SELECT ticker, data, fechamento FROM cotacoes ORDER BY data DESC LIMIT 5').fetchall())"
```
