# =============================================================================
# MODELO DE ESTUDO — tests/test_i18n.py
# -----------------------------------------------------------------------------
# O QUE ESTE ARQUIVO VIGIA, E POR QUE CADA COISA ESTA AQUI.
#
# O catalogo tem tres blocos de idioma e nenhum compilador olhando para eles. Um
# codigo digitado errado no bloco `es`, um `{ticker}` que virou `{codigo}` na
# traducao, uma chave nova acrescentada so no ingles — nada disso quebra o import.
# Quebra na tela do usuario, meses depois, e so no idioma que ninguem usa no dia a
# dia. Os dois primeiros testes existem por isso.
#
# ★ O TERCEIRO TESTE E O IMPORTANTE, e ele nasceu de um bug de verdade.
#
# O idioma vive num `ContextVar`. Um `format_func` do Streamlit e um callback: o
# Streamlit guarda a funcao e a executa DEPOIS, possivelmente fora do contexto que
# definiu o idioma. Ali o ContextVar volta ao padrao, e a pagina em espanhol saia
# com uma opcao em ingles no meio. `translator()` existe para congelar o idioma no
# momento em que o widget e desenhado; o teste prova isso rodando o callback numa
# OUTRA THREAD, que e exatamente a situacao em que `text()` erraria.
# =============================================================================

"""Testes do catalogo de mensagens e da troca de idioma."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from datalens.i18n import (
    CATALOG,
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    Message,
    get_language,
    set_language,
    text,
    translate,
    translator,
)

PLACEHOLDER = re.compile(r"{(\w+)}")

OUTROS_IDIOMAS = [code for code in SUPPORTED_LANGUAGES if code != DEFAULT_LANGUAGE]


@pytest.fixture(autouse=True)
def idioma_limpo():
    """Cada teste comeca no idioma padrao e devolve o contexto como o encontrou."""
    anterior = get_language()
    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(anterior)


@pytest.mark.parametrize("idioma", OUTROS_IDIOMAS)
def test_todo_codigo_do_ingles_tem_traducao(idioma):
    """O ingles e a referencia: nenhum codigo pode existir so nele.

    A falta nao estoura — `translate` cai para o ingles de proposito, para que meio
    catalogo traduzido vire uma frase legivel e nunca um codigo cru na tela. E
    justamente por nao estourar que precisa de um teste.
    """
    # Arrange / Act
    faltando = sorted(set(CATALOG[DEFAULT_LANGUAGE]) - set(CATALOG[idioma]))

    # Assert
    assert not faltando, f"sem traducao em {idioma}: {faltando}"


@pytest.mark.parametrize("idioma", SUPPORTED_LANGUAGES)
def test_os_placeholders_sao_os_mesmos_em_todos_os_idiomas(idioma):
    """★ Um `{ticker}` que virou `{codigo}` na traducao.

    `translate` preenche o template com os parametros que o CODIGO manda. Se a
    traducao inventa um nome de placeholder, a frase sai como
    "[codigo: missing parameter ...]" — legivel, mas inutil, e so naquele idioma.
    """
    # Arrange
    divergentes = {}

    # Act
    for codigo, referencia in CATALOG[DEFAULT_LANGUAGE].items():
        traducao = CATALOG[idioma].get(codigo)
        if traducao is None:
            continue
        esperado = set(PLACEHOLDER.findall(referencia))
        encontrado = set(PLACEHOLDER.findall(traducao))
        if esperado != encontrado:
            divergentes[codigo] = (sorted(esperado), sorted(encontrado))

    # Assert
    assert not divergentes, f"placeholders diferentes em {idioma}: {divergentes}"


@pytest.mark.parametrize("idioma", SUPPORTED_LANGUAGES)
def test_o_idioma_escolhido_muda_o_texto_da_interface(idioma):
    """A troca de idioma tem que chegar nos ROTULOS, nao so nas mensagens de erro.

    O bug que originou tudo isto: o seletor trocava o idioma, as mensagens de erro
    obedeciam, e a tela inteira continuava em ingles — porque so o catalogo de erro
    existia. `ui_main_menu` e um rotulo puro, e as tres escritas dele sao diferentes.

    Nao se compara qualquer codigo: "Perfil" e a traducao certa em portugues E em
    espanhol, e um teste que exigisse tres frases distintas para todo codigo estaria
    exigindo que a traducao fosse errada em algum lugar.
    """
    # Act
    set_language(idioma)
    escrito = text("ui_main_menu")

    # Assert
    assert escrito == CATALOG[idioma]["ui_main_menu"]
    if idioma != DEFAULT_LANGUAGE:
        assert escrito != CATALOG[DEFAULT_LANGUAGE]["ui_main_menu"]


def test_translator_congela_o_idioma_mesmo_chamado_de_outra_thread():
    """★ O bug que este helper existe para nao deixar voltar.

    `text()` le o ContextVar de QUEM CHAMA. Um `format_func` do Streamlit roda
    depois, e pode rodar noutra thread — onde ninguem chamou `set_language`. Ali
    `text()` responde em ingles no meio de uma pagina em espanhol.
    """
    # Arrange
    set_language("es")
    congelado = translator()

    # Act
    with ThreadPoolExecutor(max_workers=1) as executor:
        pela_thread = executor.submit(congelado, "ui_profile").result()
        sem_congelar = executor.submit(text, "ui_profile").result()

    # Assert
    assert pela_thread == CATALOG["es"]["ui_profile"]
    assert sem_congelar == CATALOG[DEFAULT_LANGUAGE]["ui_profile"], (
        "o teste parou de provar o que dizia: `text()` deixou de depender do contexto"
    )


def test_um_codigo_desconhecido_nao_estoura_a_tela():
    """Um codigo errado e bug nosso, nao do dado do usuario. Diga isso, nao levante."""
    # Act
    escrito = translate(Message("nao_existe", {"a": 1}))

    # Assert
    assert "nao_existe" in escrito
