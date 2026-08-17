"""The opening page: the whole answer on one screen, before anybody scrolls.

THE SHAPE IS THE REQUIREMENT. A dashboard is read in one glance or it is not read: the
reader arrives with a question ("how are we doing?") and either the screen answers it
where their eyes already are, or they leave. Everything below is arranged around that
and nothing else:

    cards      five numbers, the headline    (each capped by a chip that names it)
    panels     three charts, one question each
"""

from __future__ import annotations

import theme
from sources import (
    ASSETS_QUERY,
    INDICATOR_COLUMNS,
    INDICATORS_QUERY,
    QUOTES_QUERY,
    WAREHOUSE_COLUMNS,
    from_database,
)

import streamlit as st
import pandas as pd

from datalens import charts, ranking
from datalens.connectors.base import ConnectorError
from datalens.i18n import text, translate, translator
from datalens.ranking import AnalysisError

DEFAULT_BENCHMARK = 11
# SGS 1 is USD/BRL - used only by the simulation section, to put the American
# closes (quoted in USD) into the same money the Brazilian "R$" cards speak.
DOLLAR_BENCHMARK = 1
WAREHOUSE_OPTION = "warehouse"

CHIPS = [
    "ui_chip_benchmark",
    "ui_chip_best",
    "ui_chip_worst",
    "ui_chip_volatility",
    "ui_chip_coverage",
]

LEADERS_IN_CHART = 8

# ==========================================
# FLAGS DE AJUSTE RÁPIDO DOS TÍTULOS DE SEÇÃO
# Ajuste o valor em "rem" de cada título individualmente.
# ==========================================
FONT_TITULO_SIMULACAO = "2.05rem"  # Título da seção de simulação
FONT_TITULO_CARD_BENCHMARK = "2.2rem"  # Card 1: Carteira Benchmark
FONT_TITULO_CARD_POSICAO = "1.9rem"  # Card 2: Cálculo de Posição
FONT_TITULO_CARD_CUSTOS = "1.9rem"  # Card 3: Custos e Rendimentos


def render(connection: str) -> None:
    """Draws the home page over the example warehouse."""
    theme.page_title("Home")

    try:
        quotes = from_database(connection, QUOTES_QUERY)
        assets = from_database(connection, ASSETS_QUERY)
        rates = from_database(
            connection, INDICATORS_QUERY, {"code": DEFAULT_BENCHMARK}
        )
        dollar = from_database(
            connection, INDICATORS_QUERY, {"code": DOLLAR_BENCHMARK}
        )
    except ConnectorError as error:
        st.error(translate(error.message))
        return

    label = translator()
    st.sidebar.selectbox(
        text("ui_data_source"),
        (WAREHOUSE_OPTION,),
        format_func=lambda _: label(
            "ui_example_warehouse", quotes=len(quotes), assets=len(assets)
        ),
        label_visibility="collapsed",
        help=text("ui_data_source_help"),
        key="home_source",
    )

    countries, sectors = _filters(assets)

    try:
        panel = ranking.price_panel(quotes, *WAREHOUSE_COLUMNS)
        universe = panel["ticker"].nunique()
        panel = panel[panel["ticker"].isin(_wanted(assets, countries, sectors))]
        benchmark = ranking.benchmark_series(rates, *INDICATOR_COLUMNS)
        scores = ranking.rank(panel, benchmark, top=panel["ticker"].nunique())
    except AnalysisError as error:
        st.error(translate(error.message))
        return

    _cards(scores, universe)
    _panels(rates, scores, assets[assets["ticker"].isin(panel["ticker"].unique())])

    # Phase 4: Excel Export using Polars (Movido para a barra lateral)
    import io
    import polars as pl

    def generate_excel():
        buffer = io.BytesIO()
        df_export = pl.DataFrame(ranking.as_frame(scores))
        df_export.write_excel(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Export Report")
    st.sidebar.download_button(
        label="Download Excel (.xlsx)",
        data=generate_excel(),
        file_name="report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # ==========================================
    # SEÇÃO DOS CARDS DE SIMULAÇÃO DE ATIVOS (BENCHMARK & DINÂMICO)
    # ==========================================
    st.markdown("---")

    data_inicio = panel["date"].min().strftime("%d/%m/%Y")
    data_fim = panel["date"].max().strftime("%d/%m/%Y")

    st.markdown(
        f"<div class='dl-sim-heading' style='font-size: {FONT_TITULO_SIMULACAO}'>"
        f"{text('ui_sim_heading', data_inicio=data_inicio, data_fim=data_fim)}"
        f"</div>",
        unsafe_allow_html=True
    )

    # 1. Extração dos dados dinâmicos do ranking e preços mais recentes
    df_scores = ranking.as_frame(scores)
    latest_prices = quotes.sort_values('date').groupby('ticker').last().reset_index()[['ticker', 'date', 'close']]
    
    # 2. Cruza o ranking garantindo que as colunas 'sector', 'country' e 'currency' venham
    #    limpas da tabela assets.
    df_ranking_full = df_scores.merge(
        assets[['ticker', 'sector', 'country', 'currency']], on='ticker', how='inner'
    ).merge(latest_prices, on='ticker', how='inner')
    df_ranking_full = df_ranking_full.drop_duplicates(subset=['ticker'])
    df_ranking_full['sector'] = df_ranking_full['sector'].fillna('Outros')

    # O preço de fechamento está NA MOEDA do ativo: BRL para os brasileiros, USD para os
    # americanos. Somar os dois como se fossem a mesma moeda faz "Alocado (EUA)" e
    # "Posição Total" misturarem dólares com reais. Converte o preço americano pelo câmbio
    # (SGS 1) no último dia do período - que é exatamente o dia do último fechamento - para
    # que todo "R$" da seção seja o mesmo dinheiro.
    fx_rate = (
        float(dollar.sort_values('date')['value'].iloc[-1])
        if not dollar.empty else None
    )
    if fx_rate:
        usd = df_ranking_full['currency'] == 'USD'
        df_ranking_full['preco'] = df_ranking_full['close'].where(
            ~usd, df_ranking_full['close'] * fx_rate
        )
    else:
        df_ranking_full['preco'] = df_ranking_full['close']
    
    # 3. Garante até 2 ações únicas por setor mantendo explicitamente a coluna 'sector' nas colunas.
    #    `groupby().apply().reset_index()` descarta a coluna de agrupamento no pandas 3.x;
    #    `sort_values + groupby.head` preserva todas as colunas em qualquer versão.
    top_per_sector = (
        df_ranking_full.sort_values("excess", ascending=False)
        .groupby("sector", sort=False)
        .head(2)
        .reset_index(drop=True)
    )
    
    ALTURA_CARD = 600  # Altura que cabe na dobra sem rolagem interna

    col1, col2, col3 = st.columns([1.4, 1.0, 1.0])

    # ==============================
    # CARD 1: Carteira Benchmark (Comparação Vertical por Setor)
    # ==============================
    with col1:
        with st.container(height=ALTURA_CARD, border=True):
            st.markdown(
                f'<div class="dl-card-title" style="font-size: {FONT_TITULO_CARD_BENCHMARK}">{text("ui_card1_title")}</div>'
                f'<div class="dl-card-subtitle">{text("ui_card1_subtitle")}</div>',
                unsafe_allow_html=True,
            )

            if not top_per_sector.empty and 'sector' in top_per_sector.columns:
                bar_data = top_per_sector.copy()
                cotas_base = 10
                custo_total = text("ui_card1_cost_total")
                quantidade = text("ui_card1_share_count")
                pct_carteira = text("ui_card1_portfolio_pct")
                bar_data[custo_total] = bar_data['preco'] * cotas_base
                bar_data[quantidade] = cotas_base

                total_custo_carteira = bar_data[custo_total].sum()
                bar_data[pct_carteira] = (bar_data[custo_total] / total_custo_carteira) * 100

                import plotly.express as px
                fig_bar = px.bar(
                    bar_data,
                    x="ticker",
                    y=pct_carteira,
                    color="sector",
                    height=ALTURA_CARD - 90,
                )
                fig_bar.update_layout(
                    margin={"l": 0, "r": 0, "t": 0, "b": 0},
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='white'),
                    legend=dict(
                        title=dict(text=text("ui_card1_legend"), font=dict(size=11)),
                        orientation="v",
                        x=1.02,
                        y=1,
                        xanchor="left",
                        yanchor="top",
                        bgcolor="rgba(0,0,0,0)",
                        font=dict(size=10),
                    ),
                )
                fig_bar.update_xaxes(tickfont=dict(size=10))
                fig_bar.update_yaxes(tickfont=dict(size=10), gridcolor="rgba(255,255,255,0.08)")
                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
            else:
                st.warning(text("ui_card1_no_data"))

    def _is_br(row) -> bool:
        """Brasileiro de verdade: o país vem da tabela de ativos, não da terminação do
        código. O sufixo '.SA' é só o plano B quando o país não veio preenchido."""
        country = str(row.get("country") or "").lower()
        if country in ("brasil", "brazil"):
            return True
        if country in ("eua", "usa", "united states", "estados unidos"):
            return False
        return str(row.get("ticker") or "").endswith(".SA")

    # Preparação da lista limpa da carteira benchmark para os cálculos dos Cards 2 e 3.
    # Por setor, até 2 ativos: o melhor brasileiro e o melhor americano quando os dois
    # existem; quando um lado não tem representante entre os dois primeiros, a vaga fica
    # com o melhor ranqueado restante - cada um marcado pelo PAÍS DE VERDADE.
    carteira_benchmark = []
    if not top_per_sector.empty and 'sector' in top_per_sector.columns:
        for sector, group in top_per_sector.groupby('sector'):
            rows = group.to_dict('records')
            if not rows:
                continue

            br_stocks = [r for r in rows if _is_br(r)]
            us_stocks = [r for r in rows if not _is_br(r)]

            picks = [br_stocks[0] if br_stocks else None,
                     us_stocks[0] if us_stocks else None]
            for r in rows:
                if len([p for p in picks if p]) >= 2:
                    break
                if r not in picks:
                    picks.append(r)

            for item in picks:
                if not item:
                    continue
                carteira_benchmark.append({
                    "setor": sector,
                    "ticker": item['ticker'],
                    "preco": float(item['preco']),
                    "pais": "BR" if _is_br(item) else "EUA",
                })

    # ==============================
    # CARD 2: Cálculo de Posição
    # ==============================
    with col2:
        with st.container(height=ALTURA_CARD, border=True):
            st.markdown(
                f'<div class="dl-card-title" style="font-size: {FONT_TITULO_CARD_POSICAO}">{text("ui_card2_title")}</div>'
                f'<div class="dl-card-subtitle">{text("ui_card2_subtitle")}</div>',
                unsafe_allow_html=True,
            )
            cotas = st.number_input(text("ui_card2_volume"), min_value=1, value=10, step=1, key="input_cotas_benchmark")

            valor_total_br = sum(item['preco'] * cotas for item in carteira_benchmark if item['pais'] == "BR")
            valor_total_us = sum(item['preco'] * cotas for item in carteira_benchmark if item['pais'] == "EUA")
            valor_total_carteira = valor_total_br + valor_total_us
            total_acoes = len(carteira_benchmark) * cotas

            st.metric(
                label=text("ui_card2_assets"),
                value=text("ui_card2_assets_value", count=len(carteira_benchmark)),
                delta=text("ui_card2_shares_each", count=cotas),
            )
            st.metric(label=text("ui_card2_total_shares"), value=f"{total_acoes:,}".replace(",", "."))
            st.metric(label=text("ui_card2_allocated_br"), value=f"R$ {valor_total_br:,.2f}")
            st.metric(label=text("ui_card2_allocated_us"), value=f"R$ {valor_total_us:,.2f}")
            st.markdown("---")
            st.metric(label=text("ui_card2_total_position"), value=f"R$ {valor_total_carteira:,.2f}")

    # ==============================
    # CARD 3: Custos e Rendimentos
    # ==============================
    with col3:
        with st.container(height=ALTURA_CARD, border=True):
            st.markdown(
                f'<div class="dl-card-title" style="font-size: {FONT_TITULO_CARD_CUSTOS}">{text("ui_card3_title")}</div>'
                f'<div class="dl-card-subtitle">{text("ui_card3_subtitle")}</div>',
                unsafe_allow_html=True,
            )
            dividendos_projetados = valor_total_carteira * 0.065
            total_operacoes = len(carteira_benchmark)
            custo_corretagem = 4.90 * total_operacoes
            
            st.metric(label=text("ui_card3_category"), value=text("ui_card3_equities"))
            st.metric(
                label=text("ui_card3_dividends"),
                value=f"R$ {dividendos_projetados:,.2f}",
                delta=text("ui_card3_yield_delta"),
            )
            st.metric(
                label=text("ui_card3_brokerage"), 
                value=f"R$ {custo_corretagem:,.2f}", 
                delta=text("ui_card3_ops", count=total_operacoes), 
                delta_color="inverse"
            )
            st.info(text("ui_card3_estimate_info"))


# --- The filters --------------------------------------------------------------


def _filters(assets) -> tuple[list, list]:
    """Country and sector, in the sidebar, both empty by default."""
    st.sidebar.markdown(f"**{text('ui_please_filter')}**")
    countries = st.sidebar.multiselect(
        text("ui_region"),
        sorted(assets["country"].dropna().unique()),
        placeholder=text("ui_all_regions"),
        key="home_countries",
    )
    sectors = st.sidebar.multiselect(
        text("ui_sector"),
        sorted(assets["sector"].dropna().unique()),
        placeholder=text("ui_all_sectors"),
        key="home_sectors",
    )
    return countries, sectors


def _wanted(assets, countries: list, sectors: list):
    """The tickers that survive both filters - an empty filter keeps everything."""
    kept = assets
    if countries:
        kept = kept[kept["country"].isin(countries)]
    if sectors:
        kept = kept[kept["sector"].isin(sectors)]
    return kept["ticker"].unique()


# --- The row of numbers -------------------------------------------------------


def _cards(scores, universe: int) -> None:
    best, worst = scores[0], scores[-1]
    calm = min(scores, key=lambda score: score.volatility)

    values = (
        (text("ui_card_selic"), f"{best.benchmark_return:.1%}"),
        (text("ui_card_vs_selic", ticker=best.ticker), f"{best.excess_return:+.1%}"),
        (text("ui_card_vs_selic", ticker=worst.ticker), f"{worst.excess_return:+.1%}"),
        (text("ui_card_calmest", ticker=calm.ticker), f"{calm.volatility:.1%}"),
        (text("ui_card_assets"), text("ui_count_of", count=len(scores), total=universe)),
    )
    for column, code, (label, value) in zip(st.columns(len(CHIPS)), CHIPS, values):
        with column:
            theme.chip(text(code))
            st.metric(label, value)


# --- The row of charts --------------------------------------------------------


def _panels(rates, scores, assets) -> None:
    when, who, what = st.columns([1.1, 1.1, 0.9])

    with when, theme.panel():
        theme.panel_title(text("ui_panel_benchmark"))
        _plot(charts.time_series_chart(rates, *INDICATOR_COLUMNS))

    with who, theme.panel():
        theme.panel_title(text("ui_panel_premium"))
        ends = ranking.extremes(scores, LEADERS_IN_CHART)
        _plot(
            charts.ranked_bars(ranking.as_frame(ends), "ticker", "excess"),
            x_format=".0%",
        )

    with what, theme.panel():
        theme.panel_title(text("ui_panel_universe"))
        _plot(charts.share_pie(assets, "sector"), legend=True)


def _plot(figure, x_format: str | None = None, legend: bool = False) -> None:
    figure.update_layout(
        height=theme.CHART_HEIGHT,
        margin={"l": 8, "r": 8, "t": 4, "b": 4},
        showlegend=legend,
    )
    if x_format:
        figure.update_layout(xaxis_tickformat=x_format)
    st.plotly_chart(figure, width="stretch")