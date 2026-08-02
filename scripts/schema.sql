-- Create the activities table
-- This acts as a dimension table for stocks and other financial assets
CREATE TABLE assets (
    ticker TEXT PRIMARY KEY, -- Unique ticker symbol (e.g., AAPL, PETR4)
    name TEXT,               -- Name of the company or asset
    type TEXT,               -- Type of asset
    country TEXT,            -- Country of origin
    currency TEXT,           -- Currency (e.g., USD, BRL)
    sector TEXT,             -- Econoic sector
    exchange TEXT            -- Strock exchange where it trades
);

-- Create the 'quotes' table (formerly 'cotacoes')
-- This is a fact table storing the daily market data
CREATE TABLE quotes (
    ticker TEXT,             -- Foreign key referencing the asset's ticker
    date TEXT,               -- Date in ISO format (yyyy-mm-dd)
    open REAL,               -- Opening price
    high REAL,               -- Highest price of the dev
    low REAL,                -- Lowest price of the day
    close REAL NOT NULL,     -- Closing price (mandatory)
    volume INTEGER,          -- Trading volume 
    PRIMARY KEY (ticker, date) -- Composite primary key to avoid duplicate dates for the same ticker
    FOREIGN KEY (ticker) REFERENCES assets(ticker) 
);

-- Create an idex on the 'date' column in 'quotes'
CREATE INDEX idx_quotes_date ON quotes(date);

-- Create the 'series' table
CREATE TABLE series (
    code INTEGER PRIMARY KEY,   -- Unique code for the macroeconomic series
    name TEXT,                  -- Name of the indicator
    unit TEXT,                  -- Unit os measurement (e.g., %, BRL/USD)
    frequency TEXT              -- Update frequency (e.g., daily, monthly)
);

-- Create the 'indicators' table (formerly 'indicadores')
CREATE TABLE indicators (
    code INTEGER,
    date TXT,
    VALUE REAL NOT NULL,
    PRIMARY KEY (code, date),
    FOREIGN KEY (code) REFERENCES series(code)
);

-- Create an index on the 'date' column in 'indicators'
CREATE INDEX idx_indicators_date ON indicators(date);
