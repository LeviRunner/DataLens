"""Baixa os dados financeiros públicos de exemplo e monta o banco SQLite local.

Uso:
    python scripts/baixar_dados.py            # 2 anos de histórico (padrão)
    python scripts/baixar_dados.py --anos 5

Gera em data/exemplos/:
    financas.db        banco SQLite com as tabelas ativos, cotacoes e indicadores
    acoes_b3.csv       cotações das ações da B3
    acoes_eua.csv      cotações das ações dos EUA

Fontes (ambas públicas, sem chave de API — ver data/exemplos/README.md):
    Yahoo Finance  -> cotações diárias das ações
    Banco Central (SGS) -> indicadores macroeconômicos brasileiros

Usa apenas a biblioteca padrão do Python, de propósito: o banco de exemplo precisa
ser reproduzível mesmo num ambiente recém-criado, antes do `pip install -r requirements.txt`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# --- Constantes de configuração ------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "exemplos"
BANCO = DESTINO / "financas.db"

TIMEOUT_SEGUNDOS = 30
PAUSA_ENTRE_REQUISICOES = 1.0  # respeita o rate limit das APIs públicas
TENTATIVAS = 3

# Yahoo bloqueia requisições sem User-Agent de navegador.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (DataLens; projeto de estudo)"}

# Catálogo dos ativos. Vira a tabela dimensão `ativos` — é ela que dá sentido
# aos JOINs do Dia 4 (cotações sozinhas não respondem "qual setor rendeu mais?").
ATIVOS = [
    # (ticker,     nome,                     tipo,   pais,   moeda,  setor,           bolsa)
    ("PETR4.SA", "Petrobras PN", "acao", "Brasil", "BRL", "Petróleo e Gás", "B3"),
    ("VALE3.SA", "Vale ON", "acao", "Brasil", "BRL", "Mineração", "B3"),
    ("ITUB4.SA", "Itaú Unibanco PN", "acao", "Brasil", "BRL", "Financeiro", "B3"),
    ("BBAS3.SA", "Banco do Brasil ON", "acao", "Brasil", "BRL", "Financeiro", "B3"),
    ("ABEV3.SA", "Ambev ON", "acao", "Brasil", "BRL", "Bebidas", "B3"),
    ("MGLU3.SA", "Magazine Luiza ON", "acao", "Brasil", "BRL", "Varejo", "B3"),
    ("AAPL", "Apple Inc.", "acao", "EUA", "USD", "Tecnologia", "NASDAQ"),
    ("MSFT", "Microsoft Corp.", "acao", "EUA", "USD", "Tecnologia", "NASDAQ"),
    ("NVDA", "NVIDIA Corp.", "acao", "EUA", "USD", "Semicondutores", "NASDAQ"),
    ("TSLA", "Tesla Inc.", "acao", "EUA", "USD", "Automotivo", "NASDAQ"),
    ("AMZN", "Amazon.com Inc.", "acao", "EUA", "USD", "Varejo", "NASDAQ"),
    ("KO", "Coca-Cola Co.", "acao", "EUA", "USD", "Bebidas", "NYSE"),
]

# Séries do SGS (Sistema Gerenciador de Séries Temporais) do Banco Central.
INDICADORES = [
    (1, "Dólar comercial (venda)", "BRL/USD", "diaria"),
    (11, "Taxa Selic", "% a.d.", "diaria"),
    (433, "IPCA", "% a.m.", "mensal"),
]


# --- Download bruto ------------------------------------------------------------


def buscar_json(url: str) -> dict | list:
    """Baixa uma URL e devolve o JSON já decodificado, com retentativa.

    Falha alto e claro: se a fonte não responder, o banco não deve ser gerado
    pela metade e fingir que está tudo bem.
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            requisicao = urllib.request.Request(url, headers=CABECALHOS)
            with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as erro:
            ultimo_erro = erro
            if tentativa < TENTATIVAS:
                espera = tentativa * 2
                print(f"    tentativa {tentativa} falhou ({erro}); repetindo em {espera}s")
                time.sleep(espera)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def baixar_cotacoes(ticker: str, inicio: date, fim: date) -> list[tuple]:
    """Cotações diárias de um ticker no Yahoo Finance.

    Devolve linhas (ticker, data, abertura, maxima, minima, fechamento, volume).
    Dias sem negociação vêm com valores nulos na API e são descartados aqui.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={int(datetime.combine(inicio, datetime.min.time()).timestamp())}"
        f"&period2={int(datetime.combine(fim, datetime.min.time()).timestamp())}"
        f"&interval=1d"
    )
    bruto = buscar_json(url)

    resultado = bruto.get("chart", {}).get("result")
    if not resultado:
        erro = bruto.get("chart", {}).get("error")
        raise RuntimeError(f"Yahoo não retornou dados para {ticker}: {erro}")

    dados = resultado[0]
    carimbos = dados.get("timestamp", [])
    cotacao = dados["indicators"]["quote"][0]

    linhas = []
    for i, carimbo in enumerate(carimbos):
        fechamento = cotacao["close"][i]
        if fechamento is None:  # feriado/pregão sem dado — não inventamos valor
            continue
        linhas.append(
            (
                ticker,
                datetime.fromtimestamp(carimbo, tz=timezone.utc).date().isoformat(),
                _arredondar(cotacao["open"][i]),
                _arredondar(cotacao["high"][i]),
                _arredondar(cotacao["low"][i]),
                _arredondar(fechamento),
                int(cotacao["volume"][i] or 0),
            )
        )
    return linhas


def baixar_indicador(codigo: int, inicio: date, fim: date) -> list[tuple]:
    """Série histórica de um indicador do Banco Central (API SGS).

    Devolve linhas (codigo_serie, data, valor).
    """
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        f"?formato=json&dataInicial={inicio.strftime('%d/%m/%Y')}"
        f"&dataFinal={fim.strftime('%d/%m/%Y')}"
    )
    bruto = buscar_json(url)
    return [
        (
            codigo,
            datetime.strptime(item["data"], "%d/%m/%Y").date().isoformat(),
            float(item["valor"]),
        )
        for item in bruto
    ]


def _arredondar(valor: float | None) -> float | None:
    """Preços com 4 casas: suficiente para ação e centavos, sem ruído de float."""
    return None if valor is None else round(float(valor), 4)


# --- Escrita: SQLite e CSV -----------------------------------------------------


def criar_esquema(conexao: sqlite3.Connection) -> None:
    """(Re)cria as tabelas do zero — o script é idempotente por design."""
    conexao.executescript(
        """
        DROP TABLE IF EXISTS cotacoes;
        DROP TABLE IF EXISTS ativos;
        DROP TABLE IF EXISTS indicadores;
        DROP TABLE IF EXISTS series;

        CREATE TABLE ativos (
            ticker  TEXT PRIMARY KEY,
            nome    TEXT NOT NULL,
            tipo    TEXT NOT NULL,
            pais    TEXT NOT NULL,
            moeda   TEXT NOT NULL,
            setor   TEXT NOT NULL,
            bolsa   TEXT NOT NULL
        );

        CREATE TABLE cotacoes (
            ticker      TEXT NOT NULL REFERENCES ativos(ticker),
            data        TEXT NOT NULL,
            abertura    REAL,
            maxima      REAL,
            minima      REAL,
            fechamento  REAL NOT NULL,
            volume      INTEGER,
            PRIMARY KEY (ticker, data)
        );

        CREATE TABLE series (
            codigo    INTEGER PRIMARY KEY,
            nome      TEXT NOT NULL,
            unidade   TEXT NOT NULL,
            frequencia TEXT NOT NULL
        );

        CREATE TABLE indicadores (
            codigo  INTEGER NOT NULL REFERENCES series(codigo),
            data    TEXT NOT NULL,
            valor   REAL NOT NULL,
            PRIMARY KEY (codigo, data)
        );

        CREATE INDEX idx_cotacoes_data ON cotacoes(data);
        CREATE INDEX idx_indicadores_data ON indicadores(data);
        """
    )


def exportar_csv(caminho: Path, linhas: list[tuple]) -> None:
    """Mesmos dados do banco, em CSV — é o que os conectores CSV/Excel vão ler."""
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            ["ticker", "data", "abertura", "maxima", "minima", "fechamento", "volume"]
        )
        escritor.writerows(linhas)


# --- Orquestração --------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anos", type=int, default=2, help="anos de histórico a baixar (padrão: 2)"
    )
    argumentos = parser.parse_args()

    fim = date.today()
    inicio = fim - timedelta(days=365 * argumentos.anos)
    DESTINO.mkdir(parents=True, exist_ok=True)

    print(f"Baixando {argumentos.anos} ano(s) de dados ({inicio} a {fim})\n")

    cotacoes_por_pais: dict[str, list[tuple]] = {"Brasil": [], "EUA": []}
    todas_cotacoes: list[tuple] = []

    for ticker, nome, _tipo, pais, *_resto in ATIVOS:
        print(f"  {ticker:<10} {nome}")
        linhas = baixar_cotacoes(ticker, inicio, fim)
        print(f"             {len(linhas)} pregões")
        cotacoes_por_pais[pais].extend(linhas)
        todas_cotacoes.extend(linhas)
        time.sleep(PAUSA_ENTRE_REQUISICOES)

    print()
    todos_indicadores: list[tuple] = []
    for codigo, nome, *_resto in INDICADORES:
        print(f"  SGS {codigo:<6} {nome}")
        linhas = baixar_indicador(codigo, inicio, fim)
        print(f"             {len(linhas)} observações")
        todos_indicadores.extend(linhas)
        time.sleep(PAUSA_ENTRE_REQUISICOES)

    with sqlite3.connect(BANCO) as conexao:
        criar_esquema(conexao)
        conexao.executemany("INSERT INTO ativos VALUES (?,?,?,?,?,?,?)", ATIVOS)
        conexao.executemany("INSERT INTO cotacoes VALUES (?,?,?,?,?,?,?)", todas_cotacoes)
        conexao.executemany("INSERT INTO series VALUES (?,?,?,?)", INDICADORES)
        conexao.executemany("INSERT INTO indicadores VALUES (?,?,?)", todos_indicadores)

    exportar_csv(DESTINO / "acoes_b3.csv", cotacoes_por_pais["Brasil"])
    exportar_csv(DESTINO / "acoes_eua.csv", cotacoes_por_pais["EUA"])

    print(
        f"\nPronto:"
        f"\n  {BANCO.relative_to(RAIZ)} — {len(ATIVOS)} ativos, "
        f"{len(todas_cotacoes)} cotações, {len(todos_indicadores)} indicadores"
        f"\n  data/exemplos/acoes_b3.csv  — {len(cotacoes_por_pais['Brasil'])} linhas"
        f"\n  data/exemplos/acoes_eua.csv — {len(cotacoes_por_pais['EUA'])} linhas"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
