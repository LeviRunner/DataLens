<h1 align="center">DataLens</h1>

<p align="center">
  <b>Análise de dados configurável: gere o perfil automático de qualquer fonte — CSV, Excel, SQL, JSON ou API — sem alterar uma linha de código.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Streamlit-1.60-red.svg" alt="Streamlit">
  <img src="https://img.shields.io/badge/DuckDB-1.1-yellow.svg" alt="DuckDB">
  <img src="https://img.shields.io/badge/Polars-1.6-orange.svg" alt="Polars">
  <img src="https://img.shields.io/badge/tests-pytest-green.svg" alt="pytest">
</p>

---

## O que é

O **DataLens** é um sistema de análise de dados com interface web (Streamlit) que **descreve qualquer base de dados automaticamente**: tipos de coluna, valores ausentes, estatísticas, distribuições e séries temporais — sem que o usuário precise escrever código.

O mesmo motor lê um arquivo CSV, uma planilha Excel, um banco SQL, um JSON público ou uma API externa. Basta apontar a fonte e o DataLens faz o resto.

## O problema que resolve

Analistas e engenheiros de dados repetem o mesmo trabalho a cada novo conjunto de dados: abrir, inspecionar, entender tipos, verificar lacunas e montar estatísticas. O DataLens **automatiza essa primeira etapa** — o "perfil" dos dados — para **qualquer fonte**, em **qualquer projeto**.

Para quem serve:

- **Analistas** que querem entender um dataset em segundos, sem abrir o pandas.
- **Engenheiros de dados** que precisam validar contratos e qualidade de dados.
- **Estudantes e recrutadores** que querem ver um pipeline completo e testável.

## Recursos

| Recurso | Descrição |
|---|---|
| **Perfil automático** | Detecta tipos (numérico, data, booleano, categoria, texto), faltantes, estatísticas e distribuições de cada coluna |
| **5 conectores** | CSV, Excel, SQL, JSON e API — todos seguindo um contrato comum e testado |
| **Config híbrida** | Auto-detecção + sobrescrita por `YAML` + ajuste manual na tela |
| **Limpeza de dados** | Pipeline de limpeza com log de cada transformação aplicada |
| **Dashboard financeiro** | Home com ranking de ativos por **excesso geométrico ajustado ao risco** (Sharpe) sobre o benchmark |
| **Terminal de investimentos** | Cruzamento de preços (Brasil e EUA) com Selic/CDI/IPCA via API do Banco Central |
| **Relatório exportável** | Gráficos interativos em Plotly + exportação para Excel via Polars |
| **Três idiomas** | Português, Inglês e Espanhol |
| **Arquitetura de dados** | DuckDB (SQL analítico in-process), Polars (transformação multithread), pandera (contratos de dados), APScheduler (automação de carga) e Parquet como warehouhouse |

## Como funciona

```
Config -> Conector -> Limpeza -> Perfil -> Tela + Relatório HTML
```

Cada peça tem um papel único e testável em `src/datalens/`:

1. **Config** — o usuário escolhe a fonte e, opcionalmente, corrige o mapeamento de colunas.
2. **Conector** — um `connector` por origem (CSV, Excel, SQL, JSON, API), todos com a mesma interface.
3. **Limpeza** — o pipeline de limpeza corrige o que o auto-detector encontrou.
4. **Perfil** — estatísticas, distribuições e gráficos.
5. **Saída** — painel interativo no navegador ou relatório HTML exportável.

## Tecnologias

`Python` · `pandas` · `Streamlit` · `SQLAlchemy` · `requests` · `plotly` · `DuckDB` · `Polars` · `pandera` · `APScheduler` · `PyYAML` · `openpyxl`

## Como usar

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Preparar os dados de exemplo

Os dados de exemplo são **públicos e gratuitos**, sem chave de API:

| Origem | Dados | Conector |
|---|---|---|
| Yahoo Finance | Cotações diárias de ações da B3 e dos EUA | `csv` / `sql` |
| Banco Central do Brasil (SGS) | Selic, CDI, IPCA, dólar comercial | `json` / `api` |
| Coinext | Criptomoedas | `api` |

```bash
python scripts/download_data.py          # gera finance.db e os CSVs de exemplo (~1 min)
python scripts/write_parquet.py          # gera o warehouse Parquet unificado
python scripts/write_indicators.py       # extrai indicadores do banco
python scripts/open_duckdb.py --run      # inicializa o DuckDB e cria as views
```

### 3. Abrir a aplicação

```bash
python -m streamlit run app/streamlit_app.py
```

Abra no navegador e escolha a fonte: **exemplo**, CSV, Excel, SQL ou API. Nenhuma configuração é obrigatória — o app responde na primeira renderização.

## Estrutura do projeto

```
app/                    Interface Streamlit (Home, Explore, Terminal)
src/datalens/           Motor: conectores, detecção, limpeza, perfil, ranking, relatório
config/                 Configuração por YAML (config.example.yaml)
scripts/                Geração de dados, DuckDB, automação (APScheduler)
data/exemplos/          Datasets de demonstração (B3, EUA, cripto, finanças pessoais)
data/raw/               Warehouse Parquet (quotes, assets, indicators)
docs/                   Arquitetura e decisões de projeto
tests/                  Suíte de testes automatizados (pytest)
```

## Testes

A suíte garante que o motor não quebra ao mudar código — cobertura dos conectores, detecção, limpeza, perfil, ranking, relatório e telas:

```bash
python -m pytest
```

## Exemplos de uso

O mesmo motor perfila dados completamente diferentes, comprovando o reuso:

- **Ações da B3** (`acoes_b3.csv`) — cotações de PETR4, VALE3, ITUB4 e outras.
- **Ações dos EUA** (`acoes_eua.csv`) — AAPL, MSFT, NVDA, TSLA, AMZN.
- **Cripto** (`cripto.csv`) — vitrine do conector de API.
- **Finanças pessoais** (`financas_pessoais.xlsx`) — planilha "suja" para o pipeline de limpeza.

## Roadmap

- [x] Perfil automático (v1)
- [x] Config híbrida (auto + YAML + tela)
- [x] Conectores CSV, Excel, SQL, JSON e API
- [x] Relatório HTML e exportação Excel
- [x] Ranking por excesso ajustado ao risco (Sharpe geométrico)
- [ ] Deploy público no Streamlit Community Cloud
- [ ] Relatórios em PDF
- [ ] Suporte a mais fontes (cloud storage, Power BI)

---

<p align="center">
  Feito com Python, dados abertos e curiosidade.
</p>
