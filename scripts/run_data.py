"""Cria o data/finance.db a partir do scripts/schema.sql.

Se o banco ja existir o script aborta sem tocar nos dados. Use --force para
apagar e recriar do zero.

Uso: python scripts/run_data.py [--force]
"""

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA = RAIZ / "scripts" / "schema.sql"
BANCO = RAIZ / "data" / "finance.db"


def criar_esquema(conexao: sqlite3.Connection) -> None:
    """Executa o schema.sql no banco recem-criado."""
    conexao.executescript(SCHEMA.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    forcar = "--force" in argv

    if not SCHEMA.exists():
        print(f"ERRO: schema nao encontrado em {SCHEMA}", file=sys.stderr)
        return 1

    if BANCO.exists():
        if not forcar:
            print(
                f"ERRO: {BANCO} ja existe. Rode com --force para apagar e recriar.",
                file=sys.stderr,
            )
            return 1
        BANCO.unlink()
        print(f"Banco anterior removido: {BANCO.name}")

    BANCO.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(BANCO)
    try:
        criar_esquema(conexao)
        conexao.commit()
        print(f"Esquema criado em {BANCO}")
    finally:
        conexao.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
