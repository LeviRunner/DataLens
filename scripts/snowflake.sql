-- Data warehouse financeiro

PRAGMA foreign_keys = ON; -- Precisa ser ligada em TODA conexao

-- DIMENSAO LEVEL 3
-- Nao dependem de nenhuma outra tabela

-- Grupo economico acima de setor
CREATE TABLE macro_sectors (
    macro_sector_id INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE

);

-- Tipo de instituicao financeira
CREATE TABLE institution_types (
    institution_type_id INTEGER PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE
);

-- Frequencia de publicacao de uma serie
CREATE TABLE frequencies (
    frequency_id INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE,
    approx_days          INTEGER
);

--  Tipos de remuneracao ao acionista
CREATE TABLE payout_types (
    payout_types_id INTEGER PRIMARY kEY,
    name            TEXT NOT NULL UNIQUE,
    is_cash         INTEGER NOT NULL DEFAULT 1 CHECK (is_cash IN (0, 1)), -- paga em dinheiro
    is_taxable      INTEGER NOT NULL DEFAULT 0 CHECK (is_taxable IN (0, 1)) -- sofre retencao de IR?
);

-- Segmentos de fundos imobiliarios
CREATE TABLE reit_segments (
    reit_segment_id INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

-- DIMENSAO lEVEL 2
-- dimensoes ramificadas

CREATE TABLE countries (
    country_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    iso_code   TEXT NOT NULL UNIQUE CHECK (length(iso_code) = 3), -- ISO 3166-1 alpha-3
    country_risk INTEGER -- pontos-base
);

CREATE TABLE currencies (
    currency_id INTEGER PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE CHECK (length(code) = 3), -- ISO 4217: BRL, USD, EUR
    symbol      TEXT NOT NULL,
    name        TEXT NOT NULL
);

-- sector -> macro sector - Primeiro ramo do floco
CREATE TABLE sectors (
    sector_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE, -- EX: bancos, exchange
    macro_sector_id INTERGER NOT NULL REFERENCES macro_sectors(macro_sectors_id)
);

-- Regras tributarias tem vigencia: aliquota muda e o historico precisa sobreviver
CREATE TABLE tax_rules (
    tax_rule_id        INTEGER PRIMARY KEY,
    description        TEXT NOT NULL,
    income_tax_rate    REAL NOT NULL CHECK (income_tax_rate BETWEEN 0 AND 1),
    day_trade_rate     REAL CHECK (day_trade_rate BETWEEN 0 AND 1),
    monthly_exemption  REAL,
    valid_from         TEXT NOT NULL,
    valid_to           TEXT
);

CREATE TABLE asset_categories (
    asset_category_id INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE, -- nomes padronizado para stocks, REIT, tesouro e crypto
    is_fized_income INTEGER NOT NULL DEFAULT 0 CHECK (is_fixed_income IN (0, 1)),
    tax_rule_id     INTEGER REFERENCES(tax_rules_id)
);

CREATE TABLE exchanges (
    exchange_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    mic_code    TEXT UNIQUE, -- ISO 10383 padrao para codigo MIC
    timezone    TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    country_id  INTEGER NOT NULL REFERENCES countries(country_id),
    currency_id INTEGER NOT NULL REFERENCES currencies(currency_id) -- moedas de negociacao
);

-- Pessoa juridica por tras do ativo
CREATE TABLE issuers (
    issuer_id       INTEGER PRIMARY KEY,
    legal_name      TEXT NOT NULL,
    tax_id          TEXT UNIQUE,
    ir_website      TEXT,
    country_id      INTEGER NOT NULL REFERENCES couuntries(country_id)
);

-- APIs e arquivos que alimentam o Data warehouse
CREATE TABLE data_sources (
    data_source_id INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    base_url       TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'error')),
    last_loader_at TEXT
);

-- direction = +1 entra, -1 sai, 0 e neutro (desdobramento, troca de ticker)
CREATE TABLE transaction_types (
    transaction_types_id INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE, -- buy, sell, auction, stock bonus, split
    direction            INTEGER NOT NULL CHECK (direction IN (-1, 0, 1))
);

CREATE TABLE asset_status (
    asset_status_id      INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL UNIQUE, -- listed, Delisted, tender offer, bankruptcy
    is_tradable          INTEGER NOT NULL DEFAULT 1 CHECK (is_tradable IN (0, 1))
);

-- LEVEL 1 - dimensoes core
-- Ligadas direto a tabelas fatos

-- dimensao de tempo. A PK e a propria data ISO, o que mantem os fatos legiveis
CREATE TABLE calender (
    date            TEXT PRIMARY KEY,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name      TEXT    NOT NULL,
    quarter         INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    half            INTEGER NOT NULL CHECK (half IN (1, 2)),
    day_of_week     INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0 = Sunday / Domingo
    is_business_day INTEGER NOT NULL DEFAULT 1 CHECK (is_business_day IN (0, 1)),
    is_holiday      INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday IN (0, 1))
);

-- Mesma PK do seu 'assets' atual; as colunas de texto viraram chaves estrageiras
CREATE TABLE assets (
    ticker              TEXT PRIMARY KEY, -- AAPL, PETR4, BRAS3.SA
    name                TEXT NOT NULL,
    isin                TEXT UNIQUE,      -- identificador internacional
    asset_category_id   INTEGER NOT NULL REFERENCES asset_categories(asset_category_id),
    asset_status_id     INTEGER NOT NULL REFERENCES asset_statuses(asset_status_id),
    sector_id           INTEGER REFERENCES sectors(sector_id), -- NULL for crypto/bands / nulo p/ cripto e renda
    exchange_id         INTERGER REFERENCES exchanges(exchange_id),
    issuer_id           INTEGER REFERENCES issuers(issuer_id),
    reit_segment_id     INTEGER REFERENCES reit_segments(reit_segment_id) -- only for REITs / so para FIIs
);

-- Corretoras e bancos custodiantes
CREATE TABLE institutions (
    institutions_id         INTEGER PRIMARY KEY,
    name                    TEXT NOT NULL UNIQUE, -- XP, BTG, Nunvest
    tax_id                  TEXT UNIQUE,
    institutions_type_id    INTEGER NOT NULL REFERENCES institutions_types(institutions_type_id),
    country_id              INTEGER NOT NULL REFERENCES countries(country_id)
);

-- Carteiras logicas: Retirement, Swing Trade, REITs
CREATE TABLE portfolios (
    portfolio_id       INTEGER PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    description        TEXT,
    target_allocation  TEXT,
    currency_id        INTEGER NOT NULL REFERENCES currencies(currency_id),
    created_at         TEXT NOT NULL DEFAULT (date('now'))
);

-- Mantem a PK inteira 'code' do seu esquema
CREATE TABLE series (
    code            INTEGER PRIMARY KEY, -- ex: numero da serie no SGS
    name            TEXT NOT NULL, -- CPI, CDIm policy rate / IPCA, CDI, Selic
    unit            TEXT NOT NULL, -- %, index points, BRL/USD
    frequency       INTEGER NOT NULL REFERENCES frequencies(frequency_id),
    data_source_id  INTEGER NOT NULL REFERENCES data_sources(data_source_id)
);

-- Tabelas fato

-- OHLCV diario. Mesmo formato e PK composto do seu 'qoutes' atual
CREATE TABLE quotes (
    ticker          TEXT    NOT NULL REFERENCES assets(ticker),
    date            TEXT    NOT NULL REFERENCES calendar(date),
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL        NOT NULL, -- obrigatorio
    volume          INTEGER,
    data_source_id  INTEGER REFERENCES data_sources(data_sources_id), -- procedencia do dado
    PRIMARY KEY (ticker, date),
    CHECK (high IS NULL OR low IS NULL OR high >= low)
);

-- Compras, vendas e eventos societarios que mexem na posicao
CREATE TABLE trasactions (
    trasaction_id          INTEGER PRIMARY KEY,
    ticker                  TEXT    NOT NULL REFERENCES assets(ticker),
    DATABASE                TEXT    NOT NULL REFERENCES calender(date),
    instituition_id         INTEGER NOT NULL REFERENCES institutions(institution_id),
    portfolio_id            INTEGER NOT NULL REFERENCES portfolios(portfolio_id),
    trasaction_type_id      INTEGER NOT NULL REFERENCES transaction_types(transaction_types_id),
    quantity                REAL    NOT NULL CHECK (quantity > 0),
    unit_price              REAL    NOT NULL CHECK (unit_price >= 0),
    fees                    REAL    NOT NULL DEFAULT 0 CHECK (fess >= 0)
);

-- Dividendos, JCP e rendimentos de FII
CREATE TABLE payouts (
    payout_id        INTEGER PRIMARY KEY,
    ticker           TEXT   NOT NULL REFERENCES assets(ticker),
    intitution_id    INTEGER NOT NULL REFERENCES intitutions(instituion_id),
    portfolio_id     INTEGER REFERENCES portfolios(portfolio_id), -- attribution when split across portfolios
    payout_type_id   INTEGER NOT NULL REFERENCES payout_types(payout_type_id),
    ex_date          TEXT    NOT NULL REFERENCES calendar(date),  -- BR: data com / record date
    payment_date     TEXT    NOT NULL REFERENCES calendar(date),
    gross_amount     REAL    NOT NULL,
    tax_withheld     REAL    NOT NULL DEFAULT 0,
    CHECK (payment_date >= ex_date)
);

-- Valores macro observados. Mesmo formato e PK doseu 'indicators' atual
CREATE TABLE indicators (
    code INTEGER NOT NULL REFERENCES series(code),
    date TEXT    NOT NULL REFERENCES calendar(date),
    value REAL   NOT NULL,
    PRIMARY KEY (code, date)
);

-- Fundamentos trimestrais e anuais da empresa
CREATE TABLE financial_statements (
    ticker          TEXT NOT NULL REFERENCES assets(ticker),
    priod_end       TEXT NOT NULL REFERENCES calender(date),
    net_revenue     REAL,
    net_income      REAL,
    ebitda          REAL,
    total_assets    REAL,
    total_debt      REAL,
    PRIMARY KEY (ticker, priod_end)
);

-- O SQLite nao indexa FK automaticamente. Os joins do floco dependem disso

CREATE INDEX idx_assets_sector            ON assets(sector_id);
CREATE INDEX idx_assets_category          ON assets(asset_category_id);
CREATE INDEX idx_assets_issuer            ON assets(inssuer_id);
CREATE INDEX idx_assets_exchange          ON assets(exchange_id);

CREATE INDEX idx_quotes_date              ON quotes(date);
CREATE INDEX idx_indicators_date          ON indicators(date);

CREATE INDEX idx_tx_ticker                ON transactions(ticker);
CREATE INDEX idx_tx_date                  ON transactions(date);
CREATE INDEX idx_tx_portfolio_date        ON transactions(portfolio_id, date);

CREATE INDEX idx_payouts_ticker           ON payouts(ticker);
CREATE INDEX idx_payouts_payment          ON payouts(payment_date);

CREATE INDEX idx_statements_period        ON financial_statements(period_end);

-- VIEWS

-- Achata todo o ramo de 'assets' do floco num lugar so
CREATE VIEW v_assets_full AS
SELECT
    a.ticker,
    a.name AS asset_name,
    a.isin,
    ac.name AS category,
    st.name AS status,
    s.name AS sector,
    ms.name AS macro_sector,
    e.name AS exchange,
    c.name AS exchange_country,
    cur.code AS currency,
    i.legal_name AS issuer,
    rs.name AS reit_segment
FROM assets a
JOIN asset_categories ac ON ac.asset_category_id = a.asset_category_id
JOIN asset_statuses st ON st.asset_status_id = a.asset_status_id
LEFT JOIN sectors s ON s.sector_id = a.sector_id
LEFT JOIN macro_sectors ms ON ms.macro_sector_id = s.macro_sector_id
LEFT JOIN exchanges e ON e.exchange_id = a.exchange_id
LEFT JOIN countries c ON c.country_id = e.countries_id
LEFT JOIN currencies cur ON cur.currencies_id = e.currency_id
LEFT JOIN inssuers i ON i.issuer_id = a.issuer_id
LEFT JOIN reit_sefments rs ON rs.reit_segment_id = a.reit_segment_id;

-- Compatibilidade com o seu 'assets' original, plano.
-- Queries antigas seguem rodando
CREATE VIEW v_assets_legacy AS
SELECT  ticker,
        asset_name AS name,
        category AS type,
        exchange_country AS country,
        currency,
        sector,
        exchange
FROM v_assets_full;

-- Posicao atual por carteira, derivada do sinal da transacao.
CREATE VIEW v_positions AS
SELECT
    t.portfolio_id,
    p.name AS portfolio,
    t.ticker,
    SUM(t.quantity * tt.direction) AS quantity,
    SUM(t.quantity * t.unit_price * tt.direction * t.fees) AS net_cost
FROM trasactions t
JOIN trasaction_types tt ON tt.direction_type_id = t.transaction_type_id
JOIN portfolios p ON p.portfolio_id = t.portfolio_id
GROUP BY t.portfolio_id, p.name, t.ticker
HAVING SUM(t.quantity * tt.direction) <> 0;

