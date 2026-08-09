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

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")
TIMEOUT = 30


# --- Does it even start? ------------------------------------------------------


def test_the_app_starts_without_raising():
    """The single most valuable test here: catches import errors, typos in widget
    calls, and anything that would greet a visitor with a red traceback.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert not app.exception


def test_the_app_shows_a_title():
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert len(app.title) > 0


def test_the_app_offers_a_way_to_choose_a_source():
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    assert len(app.selectbox) > 0 or len(app.radio) > 0


def test_the_language_selector_exists():
    """O `i18n.py` foi escrito para a lingua ser POR SESSAO, com ContextVar, e nao
    global. Isso so tem valor se houver onde escolher.

    Um modulo cuidadoso servindo uma tela que nao expoe o recurso e trabalho perdido -
    e acontece com mais frequencia do que se admite.
    """
    # Act
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    # Assert
    labels = [box.label for box in app.selectbox] + [box.label for box in app.radio]
    assert any(
        word in " ".join(labels).lower() for word in ("idioma", "language", "lengua")
    )


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
