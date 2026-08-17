import sqlite3
import pandas as pd
import pathlib

BASE = pathlib.Path(r"C:/study/DataLens")
DB_PATH = BASE / "data" / "exemplos" / "finance.db"
OUT = BASE / "data" / "raw" / "indicators.parquet"

def main():
    if not DB_PATH.exists():
        print(f"❌ Erro: Banco de dados {DB_PATH} não encontrado.")
        return
        
    print("Conectando ao banco finance.db...")
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Extrai a tabela de indicadores
        df = pd.read_sql_query("SELECT * FROM indicators", conn)
        
        # Salva o resultado no formato Parquet
        df.to_parquet(OUT, index=False)
        print(f"✅ Sucesso! {len(df)} linhas extraídas e salvas em {OUT}")
        
    except Exception as e:
        print(f"❌ Não foi possível ler a tabela 'indicators'. Detalhe: {e}")
        # Lista as tabelas disponíveis para termos certeza do nome
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)
        print("Tabelas disponíveis dentro do banco de dados:")
        print(tables['name'].to_list())
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()