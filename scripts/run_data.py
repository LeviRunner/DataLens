"""Recria o finance.db a partir do scripts/schema.sql.

O banco anterior (tabelas em portugues) e preservado como finance_legacy.db e
seus dados sao migrados para o novo esquema em ingles. As colunas estao na
mesma ordem nos dois esquemas, entao o INSERT ... SELECT * funciona direto.

Uso: python scripts/run_data.py
"""

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA = RAIZ / "scripts" / "schema.sql"
BANCO = RAIZ / "data" / "exemplos" / "finance.db"
BANCO_ANTIGO = RAIZ / "data" / "exemplos" / "finance_legacy.db"

# tabela nova -> tabela antiga (mesma ordem de colunas nos dois esquemas)
MIGRACAO = {
    "assets": "ativos",
    "quotes": "cotacoes",
    "series": "series",
    "indicators": "indicadores",
}


def criar_esquema(conexao: sqlite3.Connection) -> None:
    """Executa o schema.sql no banco recem-criado."""
    conexao.executescript(SCHEMA.read_text(encoding="utf-8"))


def migrar_dados(conexao: sqlite3.Connection, origem: Path) -> None:
    """Copia as linhas do banco legado para as tabelas do novo esquema."""
    conexao.execute("ATTACH DATABASE ? AS legado", (str(origem),))
    try:
        for nova, antiga in MIGRACAO.items():
            conexao.execute(f"INSERT INTO {nova} SELECT * FROM legado.{antiga}")
            total = conexao.execute(f"SELECT COUNT(*) FROM {nova}").fetchone()[0]
            print(f"  {nova}: {total} linhas")
    finally:
        # DETACH so funciona fora de transacao aberta
        conexao.commit()
        conexao.execute("DETACH DATABASE legado")


def main() -> int:
    if not SCHEMA.exists():
        print(f"ERRO: schema nao encontrado em {SCHEMA}", file=sys.stderr)
        return 1

    if BANCO.exists():
        if BANCO_ANTIGO.exists():
            BANCO_ANTIGO.unlink()
        BANCO.rename(BANCO_ANTIGO)
        print(f"Banco anterior movido para {BANCO_ANTIGO.name}")

    conexao = sqlite3.connect(BANCO)
    try:
        criar_esquema(conexao)
        print(f"Esquema criado em {BANCO}")

        if BANCO_ANTIGO.exists():
            migrar_dados(conexao, BANCO_ANTIGO)

        conexao.commit()
    finally:
        conexao.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
