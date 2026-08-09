# DataLens — Roteiro Sprint: 30 dias × 4h/dia (com IA como par)

Um projeto único que costura as 5 fases da sua transição para Análise de Dados. Você **estuda**
um tema e, no mesmo dia, **constrói** o pedaço do DataLens que comprova aquele conhecimento —
tudo público no seu GitHub. Ao final de 30 dias você não tem "cursos assistidos": tem um sistema
que funciona, publicado, com o seu nome.

> **Versão sprint.** O plano original era 28 semanas a 1h/dia (~196h). Este é o mesmo destino em
> **30 dias × 4h = 120h**, usando IA para eliminar o tempo morto (scaffolding, boilerplate,
> depuração de erro bobo, busca de material) — **não** para eliminar o aprendizado.

---

## Regras do jogo (leia antes de começar)

**1. A regra inegociável: você não commita código que não sabe explicar.**
No fim de cada dia, o Bloco D te obriga a explicar em voz alta o que você escreveu. Se travar,
o dia não fechou — volte e entenda. Recrutador não pergunta "quem escreveu?", pergunta "por que
assim?". Essa é a única forma de a IA acelerar sem te deixar oco.

**2. A IA entra em 2 dos 4 blocos, nunca nos outros 2.**
Os blocos de teoria dirigida e de treino sem rede são onde o aprendizado acontece de verdade.
Se você usar IA neles, o sprint vira teatro.

**3. Consistência ganha de intensidade.** 4h todo dia > 12h no sábado. Se um dia cair, use o dia
de folga da semana como reserva — não empilhe atraso.

**4. Commite todo dia.** O histórico verde do GitHub também é portfólio, e o commit diário força
você a fechar unidades de trabalho de verdade.

**5. Só material grátis:** YouTube, documentação oficial, sites de SQL interativos que rodam no
navegador.

---

## O dia padrão (4h)

| Bloco | Tempo | O que é | IA? |
|---|---|---|---|
| **A — Teoria dirigida** | 60 min | Vídeo/doc/exercício interativo do tema do dia. Anotação á mão ou em `docs/aprendizado.md`. | ❌ **Não** |
| **B — Construção em par** | 90 min | Você especifica o que o arquivo deve fazer, a IA rascunha, **você revisa linha a linha** e ajusta. | ✅ Sim |
| **C — Sem rede** | 60 min | Exercício ou refatoração do dia **sozinho**, sem IA e sem copiar. É a prova real. | ❌ **Não** |
| **D — Fechamento** | 30 min | Testar, commitar com mensagem descritiva, e escrever 3 linhas em `docs/aprendizado.md`: o que aprendi, o que quase errei, o que ficou pendente. | ⚠️ Só para revisar texto |

**Se você só tiver 2h num dia:** faça A + B e empurre C para o dia seguinte. Nunca corte o A.

---

## Como usar a IA de forma que acelera (e não apodrece)

**Faça assim — você é o arquiteto, a IA é o digitador:**

- *"Meu `csv_connector.py` precisa implementar a interface `Conector` do `base.py` (colei abaixo).
  Ele lê um CSV com separador e encoding configuráveis e devolve um DataFrame. Escreva e explique
  cada decisão."* → você definiu o contrato, ela executa.
- *"Explique esta window function linha a linha como se eu fosse revisar num code review."*
- *"Me dê 10 exercícios de JOIN com gabarito separado, do fácil ao difícil, tema finanças."*
- *"Critique meu código: onde ele quebra com dado sujo?"* → a IA como revisora é onde ela mais rende.
- *"Erro: [colar stack trace]. Explique a causa antes de sugerir a correção."*

**Nunca faça assim:**

- ❌ "Faça o DataLens inteiro." — você não vai saber explicar nada disso.
- ❌ Colar código que roda sem entender por que roda.
- ❌ Pedir a resposta do exercício antes de tentar 15 minutos.
- ❌ Usar IA no Bloco A ou C.

**Teste do espelho (rode no Bloco D):** consegue reescrever de memória o que o arquivo de hoje
faz e por quê? Se não, você não aprendeu — você transcreveu.

---

## A base do DataLens (o que estamos construindo)

| Item | Decisão |
|---|---|
| Interface | Streamlit (deploy grátis na Community Cloud) |
| Fontes | CSV, Excel, SQL (rodando a SUA query), API/JSON |
| Motor | Python/pandas — **perfil automático** dos dados |
| Config | Auto-detecta + arquivo YAML (corrigir) + controles na tela |
| Saída | Perfil na tela + export de relatório **HTML** (PDF fica pra v2) |
| Tema | Finanças: ações (B3 + EUA) de estrela; cripto, finanças pessoais e indicadores como vitrine |
| Stack | python, pandas, streamlit, sqlalchemy, requests, plotly |

## Mapa dos sprints

| Sprint | Dias | Foco | Entrega |
|---|---|---|---|
| **0** | 1 | Setup e fundação | Repo no ar, ambiente rodando |
| **1** | 2–7 | SQL + conector SQL | Notebook de análise + conector executando query |
| **2** | 8–12 | Planilhas, tipos e limpeza | CSV/Excel lendo, detector e limpeza funcionando |
| **3** | 13–19 | pandas + o Perfil (núcleo) | Motor completo rodando por script nas 4 fontes |
| **4** | 20–25 | Streamlit + deploy | **DataLens público, acessível por link** |
| **5** | 26–30 | Estatística, testes, portfólio | README matador, testes, currículos enviados |

---

# Sprint 0 — Fundação (dia 1)

### Dia 1 — Ambiente, repositório e as decisões
- **A (60):** o que faz um analista de dados no dia a dia; por que SQL vem antes de Python numa
  vaga júnior. Panorama da stack que vamos usar.
- **B (90):** criar o repositório no GitHub; `git init`, `.gitignore`, ambiente virtual
  (`venv`) e `requirements.txt` inicial (pandas, streamlit, sqlalchemy, requests, plotly, pytest);
  preencher `docs/decisoes.md` e `docs/arquitetura.md` com a tabela da base acima.
- **C (60):** rodar `python -c "import pandas"` e um `streamlit hello` — resolver **você mesmo**
  qualquer erro de ambiente. Isso é 100% do trabalho real e você vai passar por ele de novo.
- **D (30):** primeiro commit. Criar `docs/aprendizado.md` com a entrada do dia 1.
- ✅ **Comprova:** repositório público iniciado, ambiente reproduzível.

---

# Sprint 1 — SQL + conector (dias 2–7)
**Meta:** consultar dados com segurança e criar o conector que roda a sua query num banco.
SQL primeiro porque é o que mais aparece em vaga júnior e o que mais cai em teste técnico.

### Dia 2 — SELECT, WHERE, ORDER BY, LIMIT
- **A:** sintaxe básica num site interativo (roda no navegador, sem instalar nada).
- **B:** baixar um banco financeiro público para `data/exemplos/`, documentar a origem em
  `data/exemplos/README.md`, abrir no DBeaver ou SQLite e rodar as primeiras queries.
- **C:** 15 queries de filtro, sozinho, sem consultar nada além da documentação.
- ✅ Base de dados local + queries salvas.

### Dia 3 — GROUP BY e agregações (COUNT, SUM, AVG, MIN, MAX)
- **A:** agrupamento, funções de agregação, `HAVING` vs `WHERE`.
- **B:** `notebooks/01_sql_exploration.ipynb` — estruturar 5 perguntas de negócio de finanças
  ("qual ação teve maior volatilidade no período?") e responder as 2 primeiras.
- **C:** escrever 3 agregações novas do zero e prever o resultado **antes** de rodar.
- ✅ Notebook iniciado com perguntas de negócio.

### Dia 4 — JOINs (INNER, LEFT, RIGHT, FULL)
- **A:** os tipos de JOIN. É o que mais trava candidato em entrevista — invista aqui.
- **B:** completar as 5 perguntas do notebook, agora cruzando 2+ tabelas.
- **C:** peça 10 exercícios de JOIN com gabarito **separado**, resolva sem olhar, depois confira.
- ✅ Consultas cruzando tabelas, notebook fechado.

### Dia 5 — Subqueries, CTEs (WITH) e o contrato dos conectores
- **A:** subconsultas e organização de query longa com CTE.
- **B:** `src/datalens/connectors/base.py` — a classe/protocolo `Conector` com o contrato comum
  `carregar() -> DataFrame`. Decida **você** a assinatura antes de pedir o rascunho.
- **C:** reescrever uma query aninhada feia como CTE legível, sozinho.
- ✅ Interface dos conectores definida (a peça que faz o projeto ser extensível).

### Dia 6 — Window functions
- **A:** `ROW_NUMBER`, `RANK`, `LAG`/`LEAD`, médias móveis (ouro puro para finanças).
- **B:** `src/datalens/connectors/sql_connector.py` — recebe string de conexão + a query do
  usuário via SQLAlchemy e devolve DataFrame. **Atenção:** parâmetros vinculados, nunca
  concatenação de string (é assim que se evita SQL injection — e é ótima resposta de entrevista).
- **C:** média móvel de 7 dias de uma ação, escrita por você.
- ✅ Conector SQL executando query real.

### Dia 7 — Consolidação + config SQL
- **A:** revisão geral + **simulado cronometrado** de teste técnico (60 min, sem consulta).
- **B:** `config/config.example.yaml` (bloco de fonte SQL) e `config/README.md`.
- **C:** rodar o conector por 3 queries diferentes e quebrá-lo de propósito: query inválida,
  conexão errada, tabela inexistente. Ver as mensagens de erro.
- 🏆 **Marco:** notebook de análise SQL + conector SQL funcionando por config.

---

# Sprint 2 — Planilhas, tipos e limpeza (dias 8–12)
**Meta:** ler CSV/Excel e transformar dado sujo em dado utilizável — 70% do trabalho real.

### Dia 8 — Planilhas de verdade + conector CSV
- **A:** PROCV/`ÍNDICE+CORRESP`, tabelas dinâmicas (Google Sheets ou Excel). Ainda é onipresente.
- **B:** `src/datalens/connectors/csv_connector.py` — separador, encoding e cabeçalho configuráveis.
- **C:** montar uma tabela dinâmica de gastos e responder 3 perguntas só com planilha.
- ✅ CSV entrando pelo mesmo contrato do SQL.

### Dia 9 — Excel programático
- **A:** como o Excel guarda dados; múltiplas abas, cabeçalho fora da primeira linha, células
  mescladas — os clássicos que quebram script.
- **B:** `src/datalens/connectors/excel_connector.py` (openpyxl via pandas), com escolha de aba
  e linha de cabeçalho.
- **C:** criar de propósito uma planilha bagunçada e fazer seu conector engolir ela.
- ✅ `.xlsx` de finanças pessoais lido pelo sistema.

### Dia 10 — Detecção de tipos
- **A:** tipos de dado (numérico, data, categoria, texto booleano) e por que a inferência do
  pandas erra tanto com dado brasileiro (vírgula decimal, `dd/mm/aaaa`, `R$`).
- **B:** `src/datalens/detector.py` — adivinha o tipo de cada coluna com um nível de confiança.
- **C:** testar o detector nos 4 datasets de exemplo e catalogar onde ele erra.
- ✅ O sistema "adivinha" o tipo das colunas de qualquer arquivo.

### Dia 11 — Data cleaning
- **A:** faltantes (dropar vs. imputar), duplicados, formatos inconsistentes, outliers óbvios.
- **B:** `src/datalens/cleaning.py` — trata faltantes/duplicados/tipos, e **registra o que fez**
  (um log de limpeza vale ouro num relatório).
- **C:** limpar uma planilha caótica de verdade, á mão, e comparar com o que seu módulo fez.
- ✅ Pipeline de limpeza rastreável.

### Dia 12 — Consolidação do Sprint 2
- **A:** revisão de tipos e limpeza; leitura da doc do pandas sobre `dtypes` e `NA`.
- **B:** integrar `csv → detector → limpeza` num fluxo único e rodá-lo nos 4 exemplos.
- **C:** documentar em `docs/decisoes.md` **por que** você escolheu cada estratégia de limpeza.
- 🏆 **Marco:** antes/depois de uma planilha caótica — material de portfólio por si só.

---

# Sprint 3 — pandas e o Perfil (dias 13–19)
**Meta:** o coração do DataLens — o perfil automático que roda em qualquer dataset.

### Dia 13 — pandas essencial
- **A:** DataFrame, seleção, filtro, `groupby`, `merge`. Mapeie cada um ao SQL equivalente —
  é o atalho mental que faz pandas ficar fácil depois de SQL.
- **B:** `notebooks/02_pandas_exploration.ipynb` — refazer a análise do Sprint 1 em pandas.
- **C:** as mesmas 5 perguntas, agora sem olhar o notebook de SQL.
- ✅ Mesma análise, duas linguagens — ótimo assunto de entrevista.

### Dia 14 — Config loader
- **A:** YAML em Python, valores padrão, validação de entrada.
- **B:** `src/datalens/config_loader.py` — lê o YAML, aplica defaults, valida e falha com
  mensagem clara (nunca silenciosamente).
- **C:** quebrar a config de 5 formas diferentes e garantir que o erro seja legível.
- ✅ Sistema configurável por arquivo.

### Dia 15 — O Perfil, parte 1 (numérico e temporal)
- **A:** estatística descritiva: média, mediana, desvio, quartis, mín/máx, % de faltantes.
- **B:** `src/datalens/profiling.py` — perfil de colunas numéricas e de data. **Núcleo do projeto.**
- **C:** calcular média/mediana/desvio á mão numa amostra pequena e conferir com seu código.
- ✅ Perfil numérico funcionando.

### Dia 16 — O Perfil, parte 2 (categórico e texto) + estrutura de saída
- **A:** cardinalidade, top-N categorias, colunas quase-únicas (chaves) e quase-constantes (lixo).
- **B:** completar o `profiling.py`; definir uma estrutura de saída única para todos os tipos.
- **C:** rodar o perfil em ações, cripto e finanças pessoais — mesmo motor, dados diferentes.
- ✅ **Núcleo do DataLens pronto.** É esta a peça que você vai mostrar em entrevista.

### Dia 17 — Gráficos
- **A:** qual gráfico para qual pergunta (histograma ≠ barra ≠ linha) e o que é gráfico mentiroso.
- **B:** `src/datalens/charts.py` — distribuição por coluna e séries temporais com plotly.
- **C:** escolher, sozinho, o gráfico certo para 5 perguntas e justificar por escrito.
- ✅ Perfil com gráficos.

### Dia 18 — Conector de API
- **A:** o que é API REST/JSON, requisições HTTP, códigos de status, rate limit, chave de API.
- **B:** `src/datalens/connectors/api_connector.py` — puxa cotações de uma API grátis.
  **Chave de API vai em variável de ambiente, nunca no código** (isso é eliminatório num review).
- **C:** tratar você mesmo os casos de falha: timeout, 404, 429, JSON inesperado.
- ✅ As 4 fontes lendo pelo mesmo contrato.

### Dia 19 — Integração do motor
- **A:** revisão geral; como as peças se encaixam (leia seu próprio `arquitetura.md`).
- **B:** amarrar `config → conector → limpeza → perfil → gráficos` num fluxo só, com um script
  de entrada (`python -m datalens config/minha_config.yaml`).
- **C:** rodar o motor completo nas 4 fontes e anotar todo atrito de UX que encontrar.
- 🏆 **Marco:** motor completo rodando via script, em 4 fontes de finanças.

---

# Sprint 4 — Streamlit e deploy (dias 20–25)
**Meta:** transformar o motor num app público que qualquer um abre e usa.

### Dia 20 — Streamlit básico
- **A:** componentes: `file_uploader`, `selectbox`, `dataframe`, `plotly_chart`; o modelo de
  re-execução do script a cada interação (entender isso evita 90% da confusão com Streamlit).
- **B:** `app/streamlit_app.py` — esqueleto: escolher fonte, carregar, ver os dados.
- **C:** trocar o layout sozinho e observar o que re-executa a cada clique.
- ✅ App roda localmente.

### Dia 21 — Perfil na tela
- **A:** layout, colunas, abas, e `@st.cache_data` (por que cachear e quando invalida).
- **B:** ligar `profiling.py` e `charts.py` na interface.
- **C:** medir o tempo de carga antes/depois do cache e anotar o ganho.
- ✅ Perfil interativo na tela.

### Dia 22 — Configuração pela tela
- **A:** `st.session_state`, widgets dinâmicos, formulários.
- **B:** dropdowns para corrigir o tipo detectado de cada coluna e escolher quais analisar —
  a config "na tela", sem editar arquivo.
- **C:** usar o app como se fosse um usuário leigo e listar tudo que confundiu.
- ✅ Usuário final ajusta sem tocar em YAML.

### Dia 23 — Relatório HTML
- **A:** gerar HTML a partir do pandas; template simples; embutir gráfico plotly.
- **B:** `src/datalens/report.py` + botão "baixar relatório HTML" no app.
- **C:** abrir o relatório num navegador limpo e ajustar o que ficar feio, sozinho.
- ✅ Exportação funcionando.

### Dia 24 — Deploy
- **A:** dependências travadas, `secrets` no Streamlit Community Cloud, o que **não** subir no Git.
- **B:** `requirements.txt` final, `.gitignore` revisado, publicar o app.
- **C:** abrir o link no celular, de outra rede. Corrigir o que quebrar (sempre quebra algo).
- 🏆 **Marco:** **DataLens público, acessível por link.**

### Dia 25 — Polimento de UX
- **A:** o que faz um dashboard ser entendido em 10 segundos — hierarquia, texto, valor padrão.
- **B:** textos, títulos, datasets de exemplo pré-carregados (usuário sem arquivo tem o que ver),
  `docs/screenshots/`.
- **C:** entregar o link para uma pessoa leiga, cronometrar e anotar onde ela travou.
- 🏆 **Marco:** app no ar, apresentável, com dados de exemplo.

---

# Sprint 5 — Estatística, testes e portfólio (dias 26–30)
**Meta:** fechar com estatística aplicada, testes e caça ás vagas.

### Dia 26 — Estatística aplicada
- **A:** correlação (e o clássico "correlação ≠ causa"), tendência, amostragem, noção de A/B test.
  Se você já viu na graduação, aqui é só reaplicar com o vocabulário de tech.
- **B:** `src/datalens/statistics.py` — matriz de correlação e detecção de tendência; nova aba no app.
- **C:** achar uma correlação espúria nos seus dados e escrever por que ela não é causa.
- ✅ Aba de estatística no app.

### Dia 27 — Testes
- **A:** por que testar, o padrão Arrange-Act-Assert, o que **não** vale a pena testar.
- **B:** `tests/test_connectors.py` e `tests/test_profiling.py` com pytest; rodar com cobertura.
- **C:** escrever você mesmo um teste que **falha** e depois corrigir o código até passar (TDD).
- ✅ Testes automatizados — poucos candidatos júnior têm isso, e isso é o ponto.

### Dia 28 — README matador
- **A:** anatomia de um bom README: problema → solução → tecnologias → como usar → print/GIF.
- **B:** `README.md` final com screenshots, GIF de uso e o link do app no topo.
- **C:** dar o README para alguém que não conhece o projeto e ver se entende em 30 segundos.
- ✅ Repositório com cara de produto, não de exercício.

### Dia 29 — Estudo de caso e narrativa
- **A:** como contar a história do projeto: decisão, desafio, resultado (formato STAR).
- **B:** revisar `docs/arquitetura.md` e `docs/decisoes.md`; escrever o post do LinkedIn.
- **C:** **ensaiar em voz alta** 3 minutos apresentando o DataLens. Grave e assista. Esse é o
  Bloco C mais importante do sprint inteiro.
- ✅ Narrativa pronta para entrevista.

### Dia 30 — Caça ás vagas
- **A:** currículo de analista de dados, palavras-chave que os filtros procuram.
- **B:** currículo e LinkedIn atualizados com o DataLens como peça central; publicar o post.
- **C:** aplicar para 10 vagas — hoje, não "semana que vem".
- 🏆 **Marco final:** portfólio completo no ar + primeiros currículos enviados.

---

## Depois do dia 30

O sprint acaba, o projeto não. Cada item abaixo é um commit novo e um assunto novo de entrevista —
e mantém seu GitHub vivo enquanto você entrevista:

Export em PDF; mais conectores (Google Sheets, Parquet); detecção de outliers; comparação entre
datasets; cache e performance; internacionalização; CI no GitHub Actions rodando os testes.

**E o mais importante:** continue os 60 min de Bloco A por dia. Em 30 dias você construiu a
prova de que consegue entregar. Os fundamentos continuam se aprofundando pelo resto da carreira.
