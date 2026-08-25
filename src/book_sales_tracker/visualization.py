import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from book_sales_tracker.models import BsrPoint, BsrSummary, RankTier
from book_sales_tracker.ui.revolut_theme import ACCENT_COLORS, apply_revolut_layout

TIER_ORDER = [
    RankTier.TOP_10,
    RankTier.TOP_100,
    RankTier.TOP_500,
    RankTier.TOP_2K,
    RankTier.TOP_10K,
    RankTier.TOP_50K,
    RankTier.LONG_TAIL,
]

TIER_LABELS = [tier.label_es for tier in TIER_ORDER]

CHART_COLORS = [ACCENT_COLORS["purple"], ACCENT_COLORS["cyan"], ACCENT_COLORS["amber"]]


def points_to_dataframe(points: list[BsrPoint]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Fecha": point.timestamp.date(),
                "BSR": point.bsr,
                "Tramo": point.tier.label_es,
                "Tramo ordinal": point.tier.value,
            }
            for point in points
        ]
    )


def build_tier_timeline_chart(points: list[BsrPoint]) -> go.Figure:
    df = points_to_dataframe(points)
    fig = px.line(
        df,
        x="Fecha",
        y="Tramo ordinal",
        markers=True,
        hover_data={"BSR": True, "Tramo": True, "Tramo ordinal": False},
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=[tier.value for tier in TIER_ORDER],
        ticktext=TIER_LABELS,
        range=[0.5, RankTier.LONG_TAIL.value + 0.5],
        autorange=False,
    )
    fig.update_layout(yaxis_title="", xaxis_title="")
    return apply_revolut_layout(fig, height=320)


def build_tier_distribution_chart(summary: BsrSummary) -> go.Figure:
    labels = list(summary.tier_distribution.keys())
    values = list(summary.tier_distribution.values())
    fig = px.bar(
        x=labels,
        y=values,
        labels={"x": "Tramo", "y": "% de días"},
    )
    fig.update_traces(marker_color=ACCENT_COLORS["purple"])
    fig.update_layout(yaxis_title="", xaxis_title="")
    fig.update_xaxes(tickangle=-25)
    return apply_revolut_layout(fig, height=260)


def build_market_turnover_chart(df: pd.DataFrame) -> go.Figure | None:
    if df.empty:
        return None
    fig = px.line(
        df,
        x="fecha",
        y="rotación_%",
        color="índice",
        markers=False,
        color_discrete_sequence=CHART_COLORS,
    )
    fig.update_layout(
        yaxis_title="",
        xaxis_title="",
        showlegend=True,
    )
    return apply_revolut_layout(fig, height=280)
