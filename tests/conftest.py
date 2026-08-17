# =============================================================================
# MODELO DE ESTUDO — tests/conftest.py
# -----------------------------------------------------------------------------
# Referencia para voce LER e ESCREVER com as suas maos em:  tests/conftest.py
#
# O `conftest.py` e um arquivo especial do pytest: ele e carregado automaticamente,
# sem import, por todos os testes da pasta e das subpastas. Serve para duas coisas:
#   1. preparar o ambiente (aqui: por `src/` no sys.path);
#   2. definir FIXTURES — dados de teste reutilizaveis.
#
# FIXTURE, em uma frase: uma funcao decorada com `@pytest.fixture` cujo NOME um teste
# declara como parametro. O pytest chama a funcao e injeta o retorno. Isso e injecao
# de dependencia, e e o que evita repetir a montagem do cenario em 20 testes.
#
#     @pytest.fixture
#     def clean_csv(tmp_path): ...
#
#     def test_alguma_coisa(clean_csv):   # <- o pytest ve o nome e injeta
#         ...
#
# `tmp_path` e uma fixture NATIVA do pytest: um diretorio temporario novo por teste,
# apagado depois. E por isso que nenhum teste sujo sobra no seu disco.
#
# -----------------------------------------------------------------------------
# NOVO (schema floco de neve) — DUAS fixtures de banco, e a diferenca importa:
#
#   `sample_db`     3 linhas numa tabela plana. Serve para testar o CONECTOR:
#                   ele abre conexao, roda query, devolve DataFrame. Um conector nao
#                   sabe o que e um floco de neve, e nao deveria precisar de 21
#                   tabelas para provar que sabe rodar um SELECT.
#
#   `snowflake_db`  o schema de verdade, lido de `scripts/snowflake.sql`, com uma
#                   semente minima que percorre a cadeia inteira de FKs. Serve para
#                   testar o que so existe no floco: JOIN, view, integridade
#                   referencial, coluna que veio de outra tabela.
#
# A tentacao e ter uma fixture so. Nao ceda: se o teste do CSV quebrar porque uma FK
# do floco mudou, voce perdeu a capacidade de saber o que quebrou.
#
# ATENCAO — `snowflake_db` le o arquivo .sql de verdade, de proposito. Um schema
# copiado para dentro do teste vira uma segunda copia que envelhece em silencio: o
# arquivo muda, o teste continua verde, e o teste passa a garantir um banco que nao
# existe mais. O preco e que um erro no .sql derruba as fixtures — e esse preco e o
# beneficio, contanto que `tests/test_schema.py` diga em portugues qual e o erro.
# =============================================================================

"""Shared test setup.

The project uses a `src/` layout without being pip-installed, so `src` has to be
on `sys.path` before the tests can import `datalens`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Sem isto, `from datalens...` falha: o pacote vive em src/, que nao esta no path.
# A alternativa profissional e um pyproject.toml com `pip install -e .` — vale fazer
# no Sprint 5, quando o projeto virar pacote de verdade.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_FILE = ROOT / "scripts" / "snowflake.sql"


# --- A semente do floco -------------------------------------------------------
# Escrita na ORDEM DAS DEPENDENCIAS: com `PRAGMA foreign_keys = ON`, inserir um
# `asset` antes do `sector` dele falha. A ordem aqui e o desenho do floco lido de
# fora para dentro — dimensao nivel 3, nivel 2, nivel 1, e so entao os fatos.
#
# Os numeros foram escolhidos para serem conferiveis a mao (e o Bloco C de sempre):
#   posicao de PETR4.SA = 100 compradas - 40 vendidas         = 60
#   net_cost            = 100*40 + 5 - 40*41,50 + 3           = 2348,00
# Se `v_positions` devolver 0.0 no net_cost, o bug e o `* fees` no lugar do `+ fees`.

SEED = """
INSERT INTO macro_sectors VALUES (1, 'Materiais Basicos'), (2, 'Tecnologia');
INSERT INTO institution_types VALUES (1, 'Corretora');
INSERT INTO frequencies VALUES (1, 'daily', 1);
INSERT INTO payout_types VALUES (1, 'Dividendo', 1, 0);
INSERT INTO reit_segments VALUES (1, 'Logistica');

INSERT INTO countries VALUES (1, 'Brasil', 'BRA', 250), (2, 'Estados Unidos', 'USA', 50);
INSERT INTO currencies VALUES (1, 'BRL', 'R$', 'Real'), (2, 'USD', 'US$', 'Dolar');
INSERT INTO sectors VALUES (1, 'Petroleo e Gas', 1), (2, 'Hardware', 2);
INSERT INTO tax_rules VALUES (1, 'Acoes - 15% sobre ganho', 0.15, 0.20, 20000.0, '2026-01-01', NULL);
INSERT INTO asset_categories VALUES (1, 'Acao', 0, 1);
INSERT INTO exchanges VALUES
    (1, 'B3', 'BVMF', 'America/Sao_Paulo', 1, 1),
    (2, 'NASDAQ', 'XNAS', 'America/New_York', 2, 2);
INSERT INTO issuers VALUES
    (1, 'Petroleo Brasileiro S.A.', '33.000.167/0001-01', 'https://ri.petrobras.com.br', 1),
    (2, 'Apple Inc.', '94-2404110', 'https://investor.apple.com', 2);
INSERT INTO data_sources VALUES
    (1, 'yfinance', 'https://finance.yahoo.com', 'active', '2026-01-03'),
    (2, 'BCB SGS', 'https://api.bcb.gov.br', 'active', '2026-01-03');
INSERT INTO transaction_types VALUES (1, 'buy', 1), (2, 'sell', -1), (3, 'split', 0);
INSERT INTO asset_statuses VALUES (1, 'listed', 1), (2, 'delisted', 0);

-- 02/01/2026 e uma sexta-feira; 03/01 e sabado. day_of_week: 0 = domingo.
INSERT INTO calendar VALUES
    ('2026-01-02', 2026, 1, 'January', 1, 1, 5, 1, 0),
    ('2026-01-03', 2026, 1, 'January', 1, 1, 6, 0, 0);

INSERT INTO assets VALUES
    ('PETR4.SA', 'Petrobras PN', 'BRPETRACNPR6', 1, 1, 1, 1, 1, NULL),
    ('AAPL',     'Apple Inc.',   'US0378331005', 1, 1, 2, 2, 2, NULL);
INSERT INTO institutions VALUES (1, 'XP Investimentos', '02.332.886/0001-04', 1, 1);
INSERT INTO portfolios VALUES (1, 'Aposentadoria', 'longo prazo', NULL, 1, '2026-01-01');
INSERT INTO series VALUES (11, 'Selic diaria', '%', 1, 2);

-- O `open` nulo em AAPL e de proposito: o profiling precisa de faltante para medir.
INSERT INTO quotes VALUES
    ('PETR4.SA', '2026-01-02', 39.50, 40.80, 39.20, 40.00, 1000000, 1),
    ('PETR4.SA', '2026-01-03', 40.10, 41.90, 40.00, 41.50,  850000, 1),
    ('AAPL',     '2026-01-02', NULL,  NULL,  NULL,  210.00,  500000, 1);

INSERT INTO transactions VALUES
    (1, 'PETR4.SA', '2026-01-02', 1, 1, 1, 100, 40.00, 5.00),
    (2, 'PETR4.SA', '2026-01-03', 1, 1, 2,  40, 41.50, 3.00);

INSERT INTO payouts VALUES (1, 'PETR4.SA', 1, 1, 1, '2026-01-02', '2026-01-03', 150.00, 0.00);
INSERT INTO indicators VALUES (11, '2026-01-02', 0.052), (11, '2026-01-03', 0.052);
"""


@pytest.fixture(scope="session")
def snowflake_schema() -> str:
    """O texto de `scripts/snowflake.sql`, lido uma vez por sessao.

    `scope="session"` porque ler o mesmo arquivo 40 vezes e desperdicio, e porque o
    conteudo e imutavel durante a rodada. Fixture com estado mutavel NUNCA deveria
    ser de sessao — um teste sujaria o proximo.
    """
    if not SCHEMA_FILE.exists():
        pytest.fail(f"scripts/snowflake.sql nao encontrado em {SCHEMA_FILE}")
    return SCHEMA_FILE.read_text(encoding="utf-8")


@pytest.fixture
def snowflake_db(tmp_path: Path, snowflake_schema: str) -> str:
    """O data warehouse em floco, vazio de dados reais e cheio de estrutura.

    Devolve a URL SQLAlchemy, igual a `sample_db`: quem consome nao precisa saber que
    por tras ha 21 tabelas.

    `PRAGMA foreign_keys = ON` fica LIGADO durante a carga. Sem isso a semente entra
    mesmo com FK quebrada, e o teste garante um banco que so existe no teste.
    """
    path = tmp_path / "snowflake.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        connection.executescript(snowflake_schema)
        connection.executescript(SEED)
        connection.commit()
    except sqlite3.Error as error:
        # Mensagem propria em vez de deixar o erro cru do sqlite3 subir: `foreign key
        # mismatch` nao diz qual coluna esta errada, e um erro de fixture aparece em
        # dezenas de testes de uma vez. Aponte para o teste que investiga.
        connection.close()
        pytest.fail(
            f"scripts/snowflake.sql nao carregou: {error}\n"
            f"Rode `pytest tests/test_schema.py -x` — ele isola qual comando falhou."
        )

    connection.close()
    return f"sqlite:///{path}"

@pytest.fixture
def sample_parquet(tmp_path: Path) -> Path:
    import polars as pl
    path = tmp_path / "quotes.parquet"
    df = pl.DataFrame({
        "ticker": ["PETR4.SA", "PETR4.SA", "AAPL"],
        "date": ["2026-01-02", "2026-01-03", "2026-01-02"],
        "close": [40.0, 41.5, 210.0]
    })
    df.write_parquet(path)
    return path

@pytest.fixture
def sample_db(tmp_path: Path) -> str:
    """A tiny throwaway SQLite database, returned as a SQLAlchemy URL.

    Tests own their data: they never touch data/exemplos/finance.db, so a broken
    test can't corrupt the real database and a changed database can't break a test.

    Deliberadamente plana e sem FK: aqui se testa o CONECTOR, nao o warehouse.
    """
    path = tmp_path / "test.db"
    import sqlite3
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE quotes (
            ticker TEXT,
            date   TEXT,
            close  REAL NOT NULL,
            PRIMARY KEY (ticker, date)
        );
        INSERT INTO quotes VALUES
            ('PETR4.SA', '2026-01-02', 40.0),
            ('PETR4.SA', '2026-01-03', 41.5),
            ('AAPL',     '2026-01-02', 210.0);
        """
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


@pytest.fixture
def clean_csv(tmp_path: Path) -> Path:
    """A well-behaved CSV: comma separated, UTF-8, dot decimal."""
    path = tmp_path / "quotes.csv"
    path.write_text(
        "ticker,date,close\n"
        "PETR4.SA,2026-01-02,40.0\n"
        "PETR4.SA,2026-01-03,41.5\n"
        "AAPL,2026-01-02,210.0\n",
        encoding="utf-8",
    )
    return path


# Repare no `write_bytes` + `.encode("latin-1")`: para testar leitura em latin-1 o
# arquivo precisa ESTAR em latin-1. Se escrevesse com `write_text` (utf-8), o teste
# do encoding errado nunca falharia — e um teste que nao pode falhar nao testa nada.
@pytest.fixture
def brazilian_csv(tmp_path: Path) -> Path:
    """The classic CSV exported by Excel in pt-BR.

    Semicolon separator, comma decimal, latin-1 encoding, accented header. Reading
    it with the defaults produces garbage rather than an exception - which is why
    the connector takes these three as parameters instead of guessing.
    """
    path = tmp_path / "brazilian.csv"
    path.write_bytes(
        "ticker;data;preço\n"
        "PETR4.SA;02/01/2026;40,50\n"
        "VALE3.SA;02/01/2026;61,20\n".encode("latin-1")
    )
    return path


# A planilha e montada com openpyxl em vez de commitada como arquivo binario:
# um .xlsx no repositorio e uma caixa-preta que ninguem revisa no code review.
# Aqui, o cenario de teste e legivel — da para VER que ha 3 linhas de lixo antes
# do cabecalho da aba "Expenses".
@pytest.fixture
def messy_workbook(tmp_path: Path) -> Path:
    """A workbook with the two classics that break scripts.

    Sheet "Expenses": three junk rows before the real header (header_row=3).
    Sheet "Income":   header on the first row (header_row=0).
    """
    from openpyxl import Workbook

    path = tmp_path / "personal_finance.xlsx"
    book = Workbook()

    expenses = book.active
    expenses.title = "Expenses"
    expenses.append(["Personal finance report"])
    expenses.append(["Generated on 02/01/2026"])
    expenses.append([])
    expenses.append(["date", "category", "amount"])
    expenses.append(["02/01/2026", "food", "R$ 1.234,56"])
    expenses.append(["03/01/2026", "transport", "R$ 89,90"])

    income = book.create_sheet("Income")
    income.append(["date", "source", "amount"])
    income.append(["05/01/2026", "salary", 5000])

    book.save(path)
    return path
