# CHeck de ordem dos arquivos — `src/datalens/`

* *um sistema de análise de dados configurável que gera o "perfil" automático de qualquer
  fonte (CSV, Excel, JSON, SQL, API) sem mudar o código.*


* **[x] i18n.py** — catálogo de mensagens en/pt_BR/es; o erro carrega código, a frase nasce na borda.
*---------------------------------------------------------------------------*
* **[x] connectors/base.py** — o contrato comum: uma exceção e um `load()` que toda fonte implementa.
*---------------------------------------------------------------------------*
* **[x] connectors/sql_connector.py**  — roda a query do usuário no banco com bind parameters, que é o que barra SQL injection.
*---------------------------------------------------------------------------*
* **[x] connectors/csv_connector.py**  — lê CSV obedecendo separador, encoding e decimal da config, em vez de adivinhar.
*---------------------------------------------------------------------------*
* **[x] connectors/excel_connector.py** — lê uma aba da planilha, com o cabeçalho na linha que o usuário indicar.
*---------------------------------------------------------------------------*
* **[x] connectors/json_connector.py**  — lê JSON de arquivo local ou de URL pública, sem chave de API.
*---------------------------------------------------------------------------*
* **[x] detector.py** — opina sobre o tipo de cada coluna, com uma confiança, e nunca converte.
*---------------------------------------------------------------------------*
* **[x] cleaning.py** — age sobre o palpite do detector e registra num log tudo o que mudou.
*---------------------------------------------------------------------------*
* **[x] config_loader.py** — lê o YAML, aplica defaults e falha com mensagem que orienta, nunca em silêncio.
*---------------------------------------------------------------------------*
* **[x] profiling.py** — o coração: perfila cada coluna numa estrutura de saída única para todos os tipos.
*---------------------------------------------------------------------------*
* **[x] charts.py** — transforma o perfil em gráficos plotly.
*---------------------------------------------------------------------------*
* **[x] connectors/api_connector.py** — puxa JSON de API autenticada, com a chave vinda de variável de ambiente.
*---------------------------------------------------------------------------*
* **[x] report.py** — junta perfil, log de limpeza e gráficos num HTML exportável.
*---------------------------------------------------------------------------*
* **[x] statistics.py** — correlações e tendências: a camada v2 que se apoia no perfil.
*---------------------------------------------------------------------------*
Fora de `src/`:
* **[x] app/streamlit_app.py** — a interface pública: escolhe a fonte, corrige o detector e mostra o perfil.
*---------------------------------------------------------------------------*
* **[x] scripts/snowflake.sql** — o data warehouse em floco de neve: 21 tabelas, 3 views, 12 índices.
*---------------------------------------------------------------------------*
* **[x] scripts/download_data.py** — 5 anos de dados públicos em `finance.db`, com janela por `--anos` ou `--inicio/--fim`.
*---------------------------------------------------------------------------*

Suíte: **198 testes**, todos passando (`python -m pytest -q`).

Pendências conhecidas, nenhuma bloqueante:
* o relatório com gráficos pesa ~4,7 MB porque embute o `plotly.min.js` inteiro; trocar
  pelo bundle `basic` derruba para perto de 1 MB.
* `test_the_report_is_self_contained` roda **sem** gráficos, então não cobre o caso em
  que a pergunta "abre offline?" realmente importa.
* o app não oferece `json` no seletor de fonte — sobra do período em que o conector não
  existia; agora é uma entrada em `SOURCES` e uma função construtora.
