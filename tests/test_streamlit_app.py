# =============================================================================
# MODELO DE ESTUDO — tests/test_streamlit_app.py       (Dias 20-22)
# -----------------------------------------------------------------------------
# ESBOCO, e o mais provisorio de todos. Leia a secao abaixo ANTES de digitar nada.
#
# A LICAO PRINCIPAL DESTE ARQUIVO E O QUE ELE NAO TESTA.
#
# Testar interface e caro e fragil. A saida nao e "escrever teste de UI melhor" — e
# fazer o `streamlit_app.py` ter tao pouca logica que quase nao haja o que testar
# nele. Se voce precisar de um teste complicado aqui, o sintoma nao esta no teste:
# esta no app, que absorveu regra de negocio que pertence a `src/datalens/`.
#
#     REGRA: streamlit_app.py so faz 3 coisas —
#       1. ler input do usuario (upload, selectbox, slider)
#       2. chamar funcoes de src/datalens/
#       3. desenhar o resultado
#     Nenhum calculo, nenhuma regra de negocio, nenhum tratamento de dado.
#
# Se essa regra for respeitada, os testes de verdade (profiling, cleaning, detector)
# ja cobrem 95% do risco, e este arquivo vira so fumaca — smoke tests que garantem
# que a pagina sobe e nao explode.
#
# A FERRAMENTA: `streamlit.testing.v1.AppTest` roda o script sem navegador e sem
# servidor. `at.run()` executa; `at.selectbox`, `at.button`, `at.dataframe` acessam
# os widgets; `at.exception` lista o que estourou.
#
# ORDEM DE PRIORIDADE (o roteiro poe visual regression acima de teste de markup, e
# com razao): estes smoke tests valem menos que voce abrir o app e usar. O Bloco C
# do Dia 22 — "usar como um usuario leigo e listar tudo que confundiu" — pega mais
# problema real que qualquer assert daqui.
#
# -----------------------------------------------------------------------------
# O QUE O FLOCO DE NEVE TROUXE, E A TENTACAO QUE ELE CRIA
#
# Com 21 tabelas, a pergunta "de onde vem o dado?" deixou de ter resposta obvia. A
# tentacao e resolver isso NO APP: um seletor de tabela, um montador de JOIN, um
# construtor de WHERE. Cada um desses e regra de negocio entrando pela porta que este
# arquivo existe para vigiar.
#
# A resposta certa ja esta no banco: `v_assets_full` e `v_positions` foram criadas
# exatamente para achatar o floco. O app oferece as views como query pronta — uma
# constante com dois nomes e um `SELECT * FROM {view}` — e continua sem logica.
#
# Por isso os DOIS testes estruturais do fim ganharam um terceiro irmao: nenhum JOIN
# escrito dentro do app.
# =============================================================================

"""Smoke tests for the Streamlit app.

They answer one question: does the page render without exploding? Everything about
what the numbers mean is tested where the logic lives.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")
TIMEOUT = 30

# Ativos e pregões do banco que estes testes constroem. Dois ativos, porque um Top N
# precisa de pelo menos dois para ter ordem; 90 pregões, porque `MIN_TRADING_DAYS` é
# 60 e um numero redondo acima disso deixa claro que a folga é de proposito.
ATIVOS_DO_TESTE = 2
PREGOES_DO_TESTE = 90


@pytest.fixture(autouse=True, scope="module")
def banco_pequeno(tmp_path_factory):
    """★ O TESTE NAO TOCA EM data/exemplos/finance.db, e isso levou tempo para valer.

    O `conftest.py` sempre disse: "os testes sao donos dos seus dados". Estes testes
    de fumaca violavam a regra desde o primeiro dia — eles sobem o app de verdade, e o
    app le o banco de exemplo de verdade. Ficou barato enquanto o banco tinha 12
    ativos e 2 MB.

    Com `--universo tudo` o banco passou a ter 827 ativos e 134 MB, e cada
    `AppTest.run()` — sao uns quinze aqui — passou a ler um milhao de cotacoes e a
    rodar o ranking sobre elas. A suite estourou dois minutos. Nao foi o teste que
    ficou lento: foi a dependencia escondida que ficou cara o bastante para aparecer.

    A variavel `DATALENS_DB` existe por causa disto. O banco abaixo tem duas acoes e
    e escrito uma vez por modulo.
    """
    caminho = tmp_path_factory.mktemp("app") / "finance.db"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(
        """
        CREATE TABLE assets (
            ticker TEXT PRIMARY KEY, name TEXT, type TEXT, country TEXT,
            currency TEXT, sector TEXT, exchange TEXT
        );
        CREATE TABLE quotes (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL NOT NULL, volume INTEGER, PRIMARY KEY (ticker, date)
        );
        CREATE TABLE series (code INTEGER PRIMARY KEY, name TEXT, unit TEXT, frequency TEXT);
        CREATE TABLE indicators (
            code INTEGER, date TEXT, value REAL NOT NULL, PRIMARY KEY (code, date)
        );
        INSERT INTO assets VALUES
            ('AAA3.SA','Alfa ON','acao','Brasil','BRL','Financeiro','B3'),
            ('BBB4.SA','Beta PN','acao','Brasil','BRL','Varejo','B3');
        INSERT INTO series VALUES (11, 'Taxa Selic', '% a.d.', 'diaria');
        """
    )

    # Um sobe, o outro cai: com os dois na mesma direcao, "melhor" e "pior" premio
    # cairiam no mesmo ativo e o teste do vencedor-ao-lado-do-perdedor nao provaria nada.
    inicio = date(2025, 1, 1)
    for ticker, passo in (("AAA3.SA", 1.002), ("BBB4.SA", 0.999)):
        preco = 100.0
        for dia in range(PREGOES_DO_TESTE):
            quando = (inicio + timedelta(days=dia)).isoformat()
            conexao.execute(
                "INSERT INTO quotes VALUES (?,?,?,?,?,?,?)",
                (ticker, quando, preco, preco, preco, preco, 1000),
            )
            preco *= passo
    for dia in range(PREGOES_DO_TESTE):
        conexao.execute(
            "INSERT INTO indicators VALUES (11, ?, 0.05)",
            ((inicio + timedelta(days=dia)).isoformat(),),
        )
    conexao.commit()
    conexao.close()

    anterior = os.environ.get("DATALENS_DB")
    os.environ["DATALENS_DB"] = str(caminho)
    yield caminho
    # Restaurar e nao apagar: outro modulo de teste na mesma sessao nao pode herdar
    # um caminho que so fazia sentido aqui.
    if anterior is None:
        os.environ.pop("DATALENS_DB", None)
    else:
        os.environ["DATALENS_DB"] = anterior


# --- Does it even start? ------------------------------------------------------


def test_the_app_starts_without_raising():
    """The single most valuable test here: catches import errors, typos in widget
    calls, and anything that would greet a visitor with a red traceback.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert not app.exception


def test_the_app_says_what_it_is_and_which_page_you_are_on():
    """ANTES este teste exigia `st.title`. Deixou de exigir, e vale registrar por que:

    `st.title` reserva cerca de 5rem de altura, e a pagina inicial passou a ter como
    requisito caber numa tela sem rolagem — 5rem e a diferenca entre a faixa de
    graficos aparecer ou nao. O titulo virou o bloco de marca na barra lateral mais o
    cabecalho "Page: X" no topo do conteudo.

    O que o teste protege continua sendo o mesmo: a tela diz o que e e onde voce esta.
    Trocar a asercao pelo widget seria travar a implementacao; trocar pela intencao
    mantem o guarda-corpo de pe depois do redesenho.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    text = " ".join(item.value for item in app.markdown)

    # Assert
    assert "DATALENS" in text, "a tela nao se identifica"
    assert "Page:" in text, "a tela nao diz em que pagina voce esta"


def test_the_app_offers_a_way_to_choose_a_source():
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert len(app.selectbox) > 0 or len(app.radio) > 0


def test_the_language_selector_exists():
    """O `i18n.py` foi escrito para a lingua ser POR SESSAO, com ContextVar, e nao
    global. Isso so tem valor se houver onde escolher.

    Um modulo cuidadoso servindo uma tela que nao expoe o recurso e trabalho perdido -
    e acontece com mais frequencia do que se admite. O seletor virou botoes de idioma
    na barra lateral; o que se testa e que eles existem.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    labels = " ".join(button.label for button in app.button)
    assert any(name in labels for name in ("English", "Português", "Español"))


def test_choosing_a_language_translates_the_screen():
    """★ O seletor existir nao e o mesmo que ele FUNCIONAR.

    O teste acima passava enquanto o bug estava na tela: o seletor estava la, trocava
    o idioma, e nada mudava — porque o `i18n` so traduzia mensagem de ERRO, e todo
    rotulo da interface era literal em ingles. Este teste olha para o menu, que e
    rotulo puro, e exige que ele mude.
    """
    # Arrange
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    antes = [item.value for item in app.sidebar.markdown]

    # Act
    app.button(key="lang_pt_BR").click().run()

    # Assert
    assert not app.exception
    depois = [item.value for item in app.sidebar.markdown]
    assert any("Main menu" in item for item in antes), antes
    assert any("Menu principal" in item for item in depois), depois


def test_switching_language_does_not_move_the_page_you_are_on():
    """★ O rotulo e traduzido, o VALOR nao.

    Se o menu guardasse a frase traduzida, trocar de idioma no meio do Terminal
    jogaria o usuario de volta para a home — o valor guardado ("Terminal") deixaria
    de existir entre as opcoes. Por isso as paginas sao identificadores e a traducao
    acontece so no `format_func`.
    """
    # Arrange
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    app.radio(key="page").set_value("Terminal")
    app = app.run()

    # Act
    app.button(key="lang_es").click().run()

    # Assert
    assert not app.exception
    assert app.radio(key="page").value == "Terminal"
    assert app.radio(key="page").options == ["Inicio", "Explorar", "Terminal"]


# --- The empty state (Dia 25) -------------------------------------------------


def test_a_visitor_with_no_file_still_sees_something():
    """A blank page reads as broken. The day-25 decision was to preload an example
    so the first screen already shows the product working.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert app.dataframe or app.markdown or app.info


def test_selecting_the_example_dataset_renders_a_profile():
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    if app.selectbox:
        app.selectbox[0].select_index(0).run()

    # Assert
    assert not app.exception


# --- The app must not crash on bad input --------------------------------------


def test_an_unreadable_source_shows_a_message_instead_of_a_traceback():
    """ConnectorError exists exactly so the app can catch one type and print a
    sentence. A stack trace on screen is the app admitting it did not plan for this.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert not app.exception


# --- O floco de neve na tela --------------------------------------------------


def test_the_ready_made_views_are_offered_as_queries():
    """NOVO. `v_assets_full` e `v_positions` sao o atalho que o banco ja oferece.

    Sem elas na tela, o usuario precisa saber que existem - e escrever 8 JOINs a mao
    ou nao usar o produto. Descoberta e parte da interface.
    """
    # Act
    source = Path(APP).read_text(encoding="utf-8")

    # Assert
    assert "v_assets_full" in source
    assert "v_positions" in source


def test_the_app_does_not_assemble_sql_by_hand():
    """★ O guarda-corpo que o floco tornou necessario.

    `JOIN` escrito dentro do app significa que a regra de "como as tabelas se ligam"
    passou a morar na interface: nao da para testar, nao da para reusar no relatorio,
    e a proxima mudanca do schema quebra a tela sem nenhum teste ficar vermelho.

    Ligacao entre tabelas e trabalho do BANCO (uma view) ou da CONFIG (uma query
    escrita pelo usuario). Nunca do arquivo que desenha botao.
    """
    # Act
    source = Path(APP).read_text(encoding="utf-8").lower()

    # Assert
    assert " join " not in source, "o app esta montando SQL - mova para uma view"


# --- The structural test that actually pays off -------------------------------


def test_the_app_file_stays_thin():
    """The real guardrail. If this file grows past a few hundred lines, business
    logic has leaked into the UI - extract it into src/datalens/ and the tests that
    matter will cover it again.

    Not a style rule: logic that lives here cannot be tested, reused by the CLI, or
    used by the HTML report.
    """
    # Act
    lines = Path(APP).read_text(encoding="utf-8").splitlines()

    # Assert
    assert len(lines) < 400, "streamlit_app.py is growing logic - extract it"


# --- O terminal de investimentos ----------------------------------------------
# A aba nova traz a tentacao mais forte de todas: ela mostra RECOMENDACAO, e o
# caminho curto para uma recomendacao e calcular o premio ali mesmo, entre dois
# widgets. Os testes daqui vigiam exatamente isso — o calculo esta em
# `datalens/ranking.py`, onde `tests/test_ranking.py` confere numero por numero.

APP_DIR = Path(__file__).resolve().parent.parent / "app"
TERMINAL = str(APP_DIR / "terminal.py")
SOURCES = str(APP_DIR / "sources.py")
HOME = str(APP_DIR / "home.py")


# --- A pagina inicial ---------------------------------------------------------
# O requisito da Home e uma FORMA, nao um conteudo: ela tem que responder sem que
# ninguem role a tela. Isso nao da para testar de verdade sem navegador (altura em
# pixel depende de fonte, zoom e monitor), entao o que se testa aqui e o que a forma
# EXIGE: as tres faixas existem, e a pagina abre sem pedir nada antes.


def test_the_home_page_answers_without_being_asked_anything():
    """★ A regra da pagina inicial.

    Uma home que abre num formulario vazio nao e uma home, e um formulario. Esta le o
    banco de exemplo que vem no repositorio e ja mostra numero na primeira renderizacao,
    sem upload, sem periodo, sem botao.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=120).run()

    # Assert
    assert not app.exception
    assert app.radio[0].value == "Home", "a home deixou de ser a pagina de entrada"
    assert len(app.metric) >= 5, "a faixa de numeros da home encolheu"


def test_the_home_page_shows_the_loser_next_to_the_winner():
    """Nos dados de exemplo, 10 de 12 ativos perderam da Selic. Uma manchete que so
    mostra o vencedor e uma manchete sobre o vencedor, nao sobre a carteira."""
    # Act
    app = AppTest.from_file(APP, default_timeout=120).run()
    values = [item.value for item in app.metric]

    # Assert
    assert any(value.startswith("+") for value in values), "sem ganhador na faixa"
    assert any(value.startswith("-") for value in values), "sem perdedor na faixa"


def test_the_home_page_draws_its_three_panels():
    """Linha, barra e pizza - uma pergunta cada. Menos que tres e a faixa de graficos
    virou decoracao; mais nao cabe acima da dobra.

    A barra extra da seção de simulação (Carteira Benchmark) soma um quarto gráfico -
    os três painéis da dobra principal continuam lá, agora seguidos do benchmark.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=120).run()

    # Assert
    assert len(app.get("plotly_chart")) == 4


def test_the_terminal_produces_a_ranking_when_the_form_is_submitted():
    """O unico teste de ponta a ponta da tela: baixar, cruzar e ordenar de verdade.

    Roda sobre o banco de exemplo (o benchmark ao vivo fica DESLIGADO por padrao),
    entao nao depende da internet nem do Banco Central estar de pe.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=120).run()
    app.radio[0].set_value("Terminal").run()
    submit = [button for button in app.button if "cross" in button.label.lower()]
    assert submit, "o formulario do terminal sumiu da tela"
    app = submit[0].click().run()

    # Assert
    assert not app.exception
    assert app.metric, "o ranking rodou sem mostrar nenhum numero de cabecalho"
    assert any("Why" in item.value for item in app.markdown), "ranking sem o porque"


def test_the_terminal_does_not_compute_the_ranking_itself():
    """★ O guarda-corpo que a aba nova tornou necessario.

    Anualizar, compor ou dividir por volatilidade dentro do arquivo que desenha
    botao significa que a regra nao pode ser testada com valor conferido a mao — e
    e justamente a regra que manda alguem comprar uma acao.
    """
    # Act
    source = Path(TERMINAL).read_text(encoding="utf-8").lower()

    # Assert
    for forbidden in ("sqrt(", "pct_change", "cumprod", "** (252", "std(ddof"):
        assert forbidden not in source, f"conta ({forbidden}) dentro da tela"


def test_the_terminal_does_not_assemble_sql_by_hand():
    """Mesmo motivo do app: ligacao entre tabelas e trabalho do banco.

    A busca e por JOIN dentro de uma linha de SELECT, e nao pela palavra solta: em
    ingles "join" tambem e verbo comum ("CSV files join the workspace"), e um guarda
    que proibe a palavra acaba proibindo o texto de ajuda.
    """
    # Act
    screens = "\n".join(
        Path(path).read_text(encoding="utf-8") for path in (TERMINAL, SOURCES, HOME)
    ).lower()
    queries = [line for line in screens.splitlines() if "select " in line]

    # Assert
    assert queries, "as queries do terminal sumiram - o teste parou de vigiar algo"
    assert not [line for line in queries if " join " in line]


def test_the_app_does_not_import_pandas_directly():
    """A soft signal in the same spirit: if the app needs pandas, it is probably
    transforming data instead of asking src/datalens/ to do it.

    Delete this test if it ever blocks something genuinely presentational - it is a
    heuristic, not a law.
    """
    # Act
    source = Path(APP).read_text(encoding="utf-8")

    # Assert
    assert "import pandas" not in source
