import sqlite3
import pandas as pd
import pathlib

BASE = pathlib.Path(r"C:/study/DataLens")
DB_PATH = BASE / "data" / "exemplos" / "finance.db"
OUT = BASE / "data" / "raw" / "assets.parquet"

def main():
    if not DB_PATH.exists():
        print(f"❌ Erro: Banco de dados {DB_PATH} não encontrado.")
        return
        
    print("Conectando ao banco finance.db...")
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Tenta ler a tabela chamada 'assets'
        df = pd.read_sql_query("SELECT * FROM assets", conn)
        
        # Salva o resultado no formato Parquet
        df.to_parquet(OUT, index=False)
        print(f"✅ Sucesso! {len(df)} ativos extraídos e salvos em {OUT}")
        
    except Exception as e:
        print(f"❌ Não foi possível ler a tabela 'assets'.")
        print("Tabelas disponíveis dentro do banco de dados:")
        # Lista todas as tabelas caso a 'assets' não exista
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)
        print(tables)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()