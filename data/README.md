# Datasets de exemplo

Catálogo dos dados de demonstração do DataLens: de onde vêm, o que representam e como
reproduzir. Todos são **públicos e gratuitos**, obtidos sem chave de API.

Servem para provar que o mesmo motor lê dados bem diferentes (banco SQL, CSV, Excel, JSON,
API).

---

## Arquivos

| Arquivo | Conteúdo | Conector | Fase |
|---|---|---|---|
| `finance.db` | Banco SQLite: ações da B3 + EUA e indicadores do Banco Central | `sql_connector` | 1 |
| `acoes_b3.csv` | Cotações diárias das ações da B3 (mesmos dados do banco) | `csv_connector` | 1 |
| `acoes_eua.csv` | Cotações diárias das ações dos EUA (mesmos dados do banco) | `csv_connector` | 1 |
| `selic.json` | *(placeholder)* série 11 do BCB crua, como a API devolve | `json_connector` | 2 |
| `financas_pessoais.xlsx` | *(placeholder)* planilha "suja" para o pipeline de limpeza | `excel_connector` | 2 |
| `cripto.csv` | *(placeholder)* vitrine de cripto | `csv_connector` | 3 |

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
- **Método:** `GET`, resposta é uma lista plana de `{"data": "dd/mm/aaaa", "valor": "0.05"}`.
- **Conector:** `json_connector` — é JSON público, sem autenticação. Aceita tanto a URL
  direta quanto o `selic.json` salvo em disco, e é justamente esse par que prova o
  desenho de duas origens do conector.
- **Séries baixadas:**

| Código | Série | Unidade | Frequência |
|---|---|---|---|
| 1 | Dólar comercial (venda) | BRL/USD | diária |
| 11 | Taxa Selic | % ao dia | diária |
| 433 | IPCA | % ao mês | mensal |

Atenção ao formato: `valor` vem como **string** (`"0.05"`) e `data` no formato brasileiro
(`dd/mm/aaaa`). A conversão é trabalho do `detector` + `cleaning`, não do conector.

---

### 3. Coinext — API de criptomoedas

- **Endpoint base:** `https://api.coinext.com.br:8443/AP/`
- **Chave de API:** exige — vai em variável de ambiente, nunca no código nem neste arquivo.
- **Formato:** JSON na requisição e na resposta.
- **Método:** majoritariamente `POST`, um endpoint por serviço.
- **Conector:** `api_connector` (Fase 3). O `json_connector` **não** serve aqui: ele só faz
  `GET` e não sabe de autenticação — é essa a fronteira entre os dois.

---

## Esquema do banco (`finance.db`)

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

**Ativos incluídos:** depende do `--universo` (ver abaixo). No padrão, PETR4, VALE3,
ITUB4, BBAS3, ABEV3, MGLU3 (B3) e AAPL, MSFT, NVDA, TSLA, AMZN, KO (NASDAQ/NYSE).

---

## Como gerar (obrigatório na primeira vez)

**O banco e os CSVs não estão no repositório.** São dado derivado: no universo completo
o `finance.db` passa de 130 MB, e cada regeração gravaria um blob novo inteiro no
histórico do Git. Um comando os reconstrói:

```bash
python scripts/download_data.py                 # 12 ativos curados, 5 anos  (~1 min)
python scripts/download_data.py --universo b3   # ~324 ações da B3           (~30 min)
python scripts/download_data.py --universo tudo # B3 + S&P 500, 827 ações    (~75 min)
python scripts/download_data.py --universo tudo --limite 20   # provar antes de esperar
```

| `--universo` | Ativos | Banco | Tempo |
|---|---|---|---|
| `exemplo` (padrão) | 12 | ~2 MB | ~1 min |
| `b3` | ~324 | ~53 MB | ~30 min |
| `sp500` | 503 | ~81 MB | ~45 min |
| `tudo` | ~827 | ~134 MB | ~75 min |

Tempos medidos, não estimados: o Yahoo leva ~5 s por ticker e é ele que manda no
relógio. Os CSVs de exemplo saem com 6 ativos por país mesmo no universo completo —
eles existem para demonstrar o conector de CSV, e 400 mil linhas não demonstram nada
que 7.500 não demonstrem.

**De onde saem as listas.** O Yahoo sabe responder *sobre* um ticker, mas não sabe
*listar* quais existem — o screener dele exige um crumb de sessão. Então a lista da B3
vem da [brapi](https://brapi.dev/api/available) e a do S&P 500 de um CSV público que já
traz o setor GICS junto (o que poupa 503 consultas de perfil). O setor das brasileiras
vem da busca do Yahoo, um ticker por vez.

**O que NÃO entra**, e por quê: terminação `11` (565 códigos, quase todos fundo
imobiliário ou ETF — não dá para separar uma unit de um FII pelo código, e rankear
imóvel junto com ação responde outra pergunta sem avisar) e terminação `32`–`39` (BDR:
a mesma empresa entraria duas vezes, uma em real e outra em dólar).

O script recria as tabelas do zero a cada execução (é idempotente) e regrava os dois CSVs a
partir dos mesmos dados. Um ticker que falha é pulado e listado no fim — em 827 ativos
sempre há um que saiu de negociação, e abortar no 700º custaria quinze minutos.
Usa só a biblioteca padrão do Python — roda antes mesmo de instalar o `requirements.txt`.

Como as APIs são consultadas ao vivo, o intervalo de datas muda conforme o dia da execução.
O conteúdo atual foi baixado em **02/08/2026**, cobrindo **2024-08-02 a 2026-07-31**
(5.988 cotações e 1.027 observações de indicadores).

---

## Como abrir

**DBeaver:** Nova conexão → SQLite → apontar para `data/exemplos/finance.db`.

**Linha de comando** (sem instalar nada, via Python):

```bash
python -c "import sqlite3; c=sqlite3.connect('data/exemplos/finance.db'); print(c.execute('SELECT ticker, data, fechamento FROM cotacoes ORDER BY data DESC LIMIT 5').fetchall())"
```
