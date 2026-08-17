'''write_parquet.py
Convert the sample CSVs into the Parquet file required by DuckDB.
'''
import pathlib
import pandas as pd

BASE = pathlib.Path(r"C:/study/DataLens")

# 1. Transformamos em uma lista contendo os dois arquivos
CSVS = [
    BASE / "data" / "exemplos" / "acoes_b3.csv",
    BASE / "data" / "exemplos" / "acoes_eua.csv"
]

OUT = BASE / "data" / "raw" / "quotes.parquet"

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)   # cria data/raw se estiver faltando
    
    dfs = [] # Lista vazia para guardar os dados de cada CSV temporariamente
    
    # 2. Lemos cada arquivo da lista
    for csv_path in CSVS:
        if csv_path.exists():
            print(f"Lendo {csv_path.name}...")
            df = pd.read_csv(csv_path)
            dfs.append(df)
        else:
            print(f"⚠️ Aviso: O arquivo {csv_path.name} não foi encontrado e será ignorado.")
            
    if not dfs:
        print("❌ Erro: Nenhum arquivo CSV foi encontrado na pasta exemplos.")
        return
        
    # 3. Juntamos (concatenamos) os dados do Brasil e dos EUA em uma única tabela
    df_final = pd.concat(dfs, ignore_index=True)
    
    # 4. Salvamos tudo em um único arquivo Parquet
    df_final.to_parquet(OUT, index=False)
    print(f"✅ Parquet unificado gravado em {OUT} (Total de linhas: {len(df_final)})")

if __name__ == "__main__":
    main()