"""Baixa os dados financeiros públicos de exemplo e monta o banco SQLite local.

Uso:
    python scripts/download_data.py                          # 12 ativos, 5 anos
    python scripts/download_data.py --universo b3            # ~324 ações da B3
    python scripts/download_data.py --universo tudo --anos 2 # B3 + S&P 500 (~75 min)
    python scripts/download_data.py --universo tudo --limite 20  # provar antes
    python scripts/download_data.py --inicio 2026-01-01 --fim 2026-01-31

`--anos` conta para trás a partir de hoje; `--inicio`/`--fim` recortam uma janela
exata, que é o que responde "quanto ocupa um mês fechado?" sem baixar cinco anos.

O `--universo` decide QUAIS ativos, e o padrão continua sendo os 12 curados: quem
clona o projeto e roda o script sem ler nada tem um banco utilizável em 20 segundos,
não uma espera de 20 minutos que ele não pediu.

    exemplo   12 ativos escritos à mão      ~2 MB      ~1 min
    b3       ~324 ações ON/PN da B3        ~53 MB     ~30 min
    sp500     503 ações do S&P 500         ~81 MB     ~45 min
    tudo     ~827 ações                   ~134 MB     ~75 min

Os tempos foram MEDIDOS, não estimados: o Yahoo leva cerca de 5 segundos por
ticker, e é ele que manda no relógio — a pausa entre requisições responde por
menos de um décimo do total. `--limite` prova a rodada antes de esperar.

O BANCO NÃO É VERSIONADO (ver .gitignore). Ele é dado DERIVADO: cada regeração
gravaria um blob novo inteiro no histórico do Git, e um repositório de estudo não
deveria pesar 134 MB por causa de um arquivo que este script reconstrói.

Gera em data/exemplos/:
    finance.db         banco SQLite com as tabelas assets, quotes, series e indicators
    acoes_b3.csv       cotações das ações da B3
    acoes_eua.csv      cotações das ações dos EUA

Os nomes são os mesmos de scripts/schema.sql — em inglês. O script nasceu em
português e ficou para trás quando o resto do projeto migrou; um banco com `quotes`
e `cotacoes` lado a lado é pior que qualquer um dos dois sozinho.

Fontes (ambas públicas, sem chave de API — ver data/exemplos/README.md):
    Yahoo Finance  -> cotações diárias das ações
    Banco Central (SGS) -> indicadores macroeconômicos brasileiros

Usa apenas a biblioteca padrão do Python, de propósito: o banco de exemplo precisa
ser reproduzível mesmo num ambiente recém-criado, antes do `pip install -r requirements.txt`.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
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
BANCO = DESTINO / "finance.db"

TIMEOUT_SEGUNDOS = 30
PAUSA_ENTRE_REQUISICOES = 1.0  # respeita o rate limit das APIs públicas
TENTATIVAS = 3

# Yahoo bloqueia requisições sem User-Agent de navegador.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (DataLens; projeto de estudo)"}

# --- De onde saem as listas de tickers -----------------------------------------
#
# Nenhuma das duas fontes é o Yahoo, e isso é de propósito: o Yahoo sabe responder
# SOBRE um ticker, não sabe LISTAR quais existem (o screener dele exige um crumb de
# sessão). Então a lista vem de quem publica lista, e o Yahoo entra depois, ticker a
# ticker, para o que só ele tem — nome, setor e cotação.

# A brapi publica todo ticker negociado na B3 num JSON só, sem chave.
URL_TICKERS_B3 = "https://brapi.dev/api/available"

# A composição do S&P 500 mantida como CSV versionado. Traz nome e SETOR GICS junto,
# o que economiza 503 consultas de perfil — a lista da B3 não tem equivalente.
URL_TICKERS_SP500 = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/"
    "constituents.csv"
)

# Busca de perfil: devolve nome longo, setor e o TIPO do papel, sem autenticação.
URL_PERFIL = "https://query1.finance.yahoo.com/v1/finance/search?q={ticker}&quotesCount=1&newsCount=0"

# AÇÃO NA B3 = quatro letras + 3, 4, 5 ou 6 (ordinária, preferencial, classes B/C).
#
# O que fica de FORA, e por quê:
#   * terminação 11 — são 565 tickers, e a esmagadora maioria é fundo imobiliário ou
#     ETF. Não há como separar uma unit (BPAC11, TAEE11) de um FII (ALZR11) pelo
#     código, e rankear imóvel junto com ação é o mesmo erro de correlacionar
#     `sector_id`: o número sai, e não quer dizer nada.
#   * terminação 32 a 39 — BDR, que é recibo de ação estrangeira. Entraria duas vezes
#     no ranking: uma como BDR em reais e outra como a ação original em dólar.
PADRAO_ACAO_B3 = re.compile(r"^[A-Z]{4}[3456]$")

UNIVERSOS = ("exemplo", "b3", "sp500", "tudo")

# Uma etiqueta honesta vale mais que um setor chutado: a rosca da tela inicial agrupa
# o que não se sabe numa fatia visível, em vez de espalhar por categorias inventadas.
SETOR_DESCONHECIDO = "Desconhecido"

# Um catálogo de 800 ativos não cabe em memória como lista de tuplas de cotação
# (~1 milhão de linhas). O banco é escrito ativo a ativo, com commit a cada um: uma
# falha na requisição 700 não pode custar as 699 anteriores.
ATIVOS_POR_COMMIT = 1

# Quantos ativos vão para cada CSV de exemplo. O CSV existe para provar o conector
# de CSV, não para carregar o universo: seis séries são legíveis no Excel, abrem
# instantâneo na aba de perfil e já mostram várias empresas lado a lado.
ATIVOS_POR_CSV = 6

# Catálogo curado. Vira a tabela dimensão `assets` — é ela que dá sentido
# aos JOINs do Dia 4 (cotações sozinhas não respondem "qual setor rendeu mais?").
ATIVOS_EXEMPLO = [
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


def buscar_texto(url: str) -> str:
    """Baixa uma URL e devolve o corpo como texto (para as listas em CSV)."""
    requisicao = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
        return resposta.read().decode("utf-8")


# --- Descoberta dos tickers ----------------------------------------------------


def filtrar_acoes_b3(tickers: list[str]) -> list[str]:
    """Fica só com as ações ON/PN — ver `PADRAO_ACAO_B3` para o que sai e por quê.

    Separada da requisição de propósito: é a única regra de negócio deste script, e
    uma regra que depende da rede para ser testada é uma regra que não é testada.
    """
    return sorted({ticker for ticker in tickers if PADRAO_ACAO_B3.match(ticker)})


def catalogo_sp500(csv_texto: str) -> list[tuple]:
    """Lê o CSV do S&P 500 e devolve as linhas já no formato da tabela `assets`.

    O setor vem do GICS, que é a classificação que a própria bolsa usa - melhor do
    que qualquer coisa que a busca do Yahoo devolveria, e de graça, porque já está
    na mesma linha do arquivo.
    """
    linhas = []
    for registro in csv.DictReader(io.StringIO(csv_texto)):
        ticker = registro["Symbol"].strip()
        if not ticker:
            continue
        linhas.append(
            (
                ticker,
                registro["Security"].strip(),
                "acao",
                "EUA",
                "USD",
                registro["GICS Sector"].strip() or SETOR_DESCONHECIDO,
                "NYSE/NASDAQ",
            )
        )
    return linhas


def perfil_yahoo(ticker: str) -> tuple[str, str]:
    """Nome longo e setor de um ticker, ou o que der para saber.

    NUNCA levanta. Um perfil que falha vale um ativo com setor "Desconhecido", não a
    perda das cotações dele: o preço é o dado, o setor é a etiqueta. Em 324 tickers
    da B3 há sempre alguns que a busca não reconhece, e derrubar o script por causa
    de uma etiqueta seria trocar o essencial pelo acessório.
    """
    try:
        bruto = buscar_json(URL_PERFIL.format(ticker=ticker))
        cotacoes = bruto.get("quotes") or []
        if not cotacoes:
            return ticker, SETOR_DESCONHECIDO
        primeira = cotacoes[0]
        nome = primeira.get("longname") or primeira.get("shortname") or ticker
        setor = primeira.get("sectorDisp") or primeira.get("sector") or SETOR_DESCONHECIDO
        return nome.strip(), setor.strip()
    except (RuntimeError, KeyError, TypeError):
        return ticker, SETOR_DESCONHECIDO


def catalogo_b3(pausa: float, limite: int | None = None) -> list[tuple]:
    """A lista da B3, com um perfil consultado por ticker.

    O `limite` corta a lista ANTES dos perfis, e não depois: cortar depois faria
    `--limite 4` gastar 324 requisições para usar quatro delas, que é o oposto do que
    a opção existe para fazer - provar a rodada em segundos.
    """
    tickers = filtrar_acoes_b3(buscar_json(URL_TICKERS_B3)["stocks"])
    if limite:
        tickers = tickers[:limite]
    print(f"  {len(tickers)} ações ON/PN na B3; buscando nome e setor de cada uma")

    catalogo = []
    for posicao, ticker in enumerate(tickers, start=1):
        nome, setor = perfil_yahoo(f"{ticker}.SA")
        catalogo.append((f"{ticker}.SA", nome, "acao", "Brasil", "BRL", setor, "B3"))
        if posicao % 50 == 0:
            print(f"    {posicao}/{len(tickers)} perfis")
        time.sleep(pausa)
    return catalogo


def montar_catalogo(universo: str, pausa: float, limite: int | None = None) -> list[tuple]:
    """Os ativos que serão baixados, conforme `--universo`."""
    if universo == "exemplo":
        return list(ATIVOS_EXEMPLO)[: limite or None]

    catalogo: list[tuple] = []
    if universo in ("b3", "tudo"):
        catalogo += catalogo_b3(pausa, limite)
    if universo in ("sp500", "tudo") and (limite is None or len(catalogo) < limite):
        linhas = catalogo_sp500(buscar_texto(URL_TICKERS_SP500))
        print(f"  {len(linhas)} ações no S&P 500 (nome e setor vieram do próprio CSV)")
        catalogo += linhas
    return catalogo[: limite or None]


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
        DROP TABLE IF EXISTS quotes;
        DROP TABLE IF EXISTS assets;
        DROP TABLE IF EXISTS indicators;
        DROP TABLE IF EXISTS series;
        -- Restos da versão em português, se o banco vier de um download antigo.
        DROP TABLE IF EXISTS cotacoes;
        DROP TABLE IF EXISTS ativos;
        DROP TABLE IF EXISTS indicadores;

        CREATE TABLE assets (
            ticker    TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            type      TEXT NOT NULL,
            country   TEXT NOT NULL,
            currency  TEXT NOT NULL,
            sector    TEXT NOT NULL,
            exchange  TEXT NOT NULL
        );

        CREATE TABLE quotes (
            ticker  TEXT NOT NULL REFERENCES assets(ticker),
            date    TEXT NOT NULL,
            open    REAL,
            high    REAL,
            low     REAL,
            close   REAL NOT NULL,
            volume  INTEGER,
            PRIMARY KEY (ticker, date)
        );

        CREATE TABLE series (
            code       INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            unit       TEXT NOT NULL,
            frequency  TEXT NOT NULL
        );

        CREATE TABLE indicators (
            code   INTEGER NOT NULL REFERENCES series(code),
            date   TEXT NOT NULL,
            value  REAL NOT NULL,
            PRIMARY KEY (code, date)
        );

        CREATE INDEX idx_quotes_date ON quotes(date);
        CREATE INDEX idx_indicators_date ON indicators(date);
        """
    )


def exportar_csv(
    caminho: Path,
    conexao: sqlite3.Connection,
    pais: str,
    ativos: int = ATIVOS_POR_CSV,
) -> None:
    """Uma AMOSTRA do banco, em CSV — é o que os conectores CSV/Excel vão ler.

    Amostra, e não o banco inteiro, porque os dois arquivos têm propósitos diferentes:
    o `finance.db` é o universo sobre o qual o ranking trabalha, e o CSV existe para
    demonstrar que o conector de CSV funciona. Exportar as 400 mil linhas da B3 daria
    um arquivo de 40 MB que ninguém abre no Excel e que faz a aba de perfil demorar
    dez segundos para descrever seis colunas.

    Lê do BANCO e não de uma lista em memória: com 827 ativos as cotações passam de um
    milhão de linhas, e guardá-las duas vezes (uma para o banco, outra para o CSV) é
    meio giga de RAM para escrever um arquivo que o SQLite já sabe percorrer.
    """
    cursor = conexao.execute(
        "SELECT q.ticker, q.date, q.open, q.high, q.low, q.close, q.volume "
        "FROM quotes q, assets a WHERE q.ticker = a.ticker AND a.country = ? "
        "  AND q.ticker IN ("
        "      SELECT ticker FROM assets WHERE country = ? ORDER BY ticker LIMIT ?"
        "  ) "
        "ORDER BY q.ticker, q.date",
        (pais, pais, ativos),
    )
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["ticker", "date", "open", "high", "low", "close", "volume"])
        escritor.writerows(cursor)


# --- Orquestração --------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anos", type=int, default=5, help="anos de histórico a baixar (padrão: 5)"
    )
    parser.add_argument("--inicio", type=date.fromisoformat, help="data inicial (AAAA-MM-DD)")
    parser.add_argument("--fim", type=date.fromisoformat, help="data final (AAAA-MM-DD)")
    parser.add_argument(
        "--universo",
        choices=UNIVERSOS,
        default="exemplo",
        help="quais ativos baixar (padrão: exemplo, 12 ativos curados)",
    )
    parser.add_argument(
        "--limite",
        type=int,
        help="para depois de N ativos - serve para provar a rodada antes dos 20 minutos",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA_ENTRE_REQUISICOES,
        help=f"segundos entre requisições (padrão: {PAUSA_ENTRE_REQUISICOES})",
    )
    argumentos = parser.parse_args()

    # `--inicio`/`--fim` vencem `--anos`: quem digitou uma data exata quer aquela data.
    fim = argumentos.fim or date.today()
    inicio = argumentos.inicio or (fim - timedelta(days=365 * argumentos.anos))
    if inicio >= fim:
        parser.error(f"--inicio ({inicio}) precisa ser anterior a --fim ({fim})")
    DESTINO.mkdir(parents=True, exist_ok=True)

    print(f"Baixando de {inicio} a {fim} ({(fim - inicio).days} dias)")
    print(f"Universo: {argumentos.universo}\n")

    catalogo = montar_catalogo(argumentos.universo, argumentos.pausa, argumentos.limite)
    print(f"\n{len(catalogo)} ativos a baixar\n")

    conexao = sqlite3.connect(BANCO)
    criar_esquema(conexao)
    conexao.executemany("INSERT INTO series VALUES (?,?,?,?)", INDICADORES)
    conexao.commit()

    total_cotacoes = 0
    falhas: list[tuple[str, str]] = []

    for posicao, ativo in enumerate(catalogo, start=1):
        ticker, nome = ativo[0], ativo[1]
        try:
            linhas = baixar_cotacoes(ticker, inicio, fim)
        except RuntimeError as erro:
            # UM TICKER QUE FALHA NÃO DERRUBA A RODADA. Em 827 ativos sempre há um
            # que saiu de negociação, mudou de código ou o Yahoo simplesmente não
            # conhece. Abortar depois de 700 downloads por causa do 701 é perder
            # quinze minutos de trabalho por um papel que ninguém vai olhar.
            falhas.append((ticker, str(erro)[:90]))
            print(f"  [{posicao}/{len(catalogo)}] {ticker:<12} FALHOU - pulando")
            time.sleep(argumentos.pausa)
            continue

        if not linhas:
            falhas.append((ticker, "sem pregão no período"))
        else:
            try:
                # A dimensão ANTES do fato: a FK de `quotes` aponta para `assets`, e o
                # ativo só entra no catálogo se realmente trouxe cotação - um ticker sem
                # preço na tabela de ativos é uma linha que nenhuma tela sabe desenhar.
                conexao.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?)", ativo)
                conexao.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?)", linhas)
                conexao.commit()
                total_cotacoes += len(linhas)
            except sqlite3.IntegrityError as erro:
                # MESMO PRINCÍPIO DA FALHA DE REDE, e aprendido do mesmo jeito: uma
                # segunda cópia do script rodando em paralelo (fácil de fazer sem
                # perceber quando a primeira está com o stdout em buffer) derrubou uma
                # rodada de 35 minutos na inserção 516 com `UNIQUE constraint failed`.
                #
                # O `INSERT OR REPLACE` seria a correção preguiçosa: esconderia a
                # duplicata em vez de contá-la. Registrar e seguir preserva as 515
                # anteriores E deixa o problema visível no resumo do fim.
                conexao.rollback()
                falhas.append((ticker, f"já estava no banco: {erro}"))

        print(f"  [{posicao}/{len(catalogo)}] {ticker:<12} {len(linhas):>5} pregões  {nome[:38]}")
        time.sleep(argumentos.pausa)

    print()
    total_indicadores = 0
    for codigo, nome, *_resto in INDICADORES:
        print(f"  SGS {codigo:<6} {nome}")
        linhas = baixar_indicador(codigo, inicio, fim)
        conexao.executemany("INSERT INTO indicators VALUES (?,?,?)", linhas)
        conexao.commit()
        total_indicadores += len(linhas)
        print(f"             {len(linhas)} observações")
        time.sleep(argumentos.pausa)

    exportar_csv(DESTINO / "acoes_b3.csv", conexao, "Brasil")
    exportar_csv(DESTINO / "acoes_eua.csv", conexao, "EUA")
    ativos_gravados = conexao.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

    # `DROP TABLE` libera as páginas dentro do arquivo, mas não devolve o espaço ao
    # disco: sem isto, uma rodada de 3 ativos por cima de uma de 800 continua
    # ocupando os mesmos 134 MB, e o tamanho impresso abaixo seria uma mentira.
    conexao.execute("VACUUM")
    conexao.close()

    print(
        f"\nPronto:"
        f"\n  {BANCO.relative_to(RAIZ)} — {ativos_gravados} ativos, "
        f"{total_cotacoes} cotações, {total_indicadores} indicadores"
        f"\n  {BANCO.stat().st_size / 1_000_000:.1f} MB"
    )
    if falhas:
        # Listadas no fim e não engolidas: um ativo ausente muda o ranking, e quem
        # rodou o script tem que saber quais faltam antes de tirar conclusão da tela.
        print(f"\n{len(falhas)} ativo(s) sem dado:")
        for ticker, motivo in falhas[:20]:
            print(f"  {ticker:<12} {motivo}")
        if len(falhas) > 20:
            print(f"  ... e mais {len(falhas) - 20}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
