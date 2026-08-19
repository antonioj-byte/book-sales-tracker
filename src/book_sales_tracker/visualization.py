import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from book_sales_tracker.models import BsrPoint, BsrSummary, RankTier


TIER_ORDER = [
    RankTier.TOP_10,
    RankTier.TOP_100,
    RankTier.TOP_500,
    RankTier.TOP_1K,
    RankTier.TOP_5K,
    RankTier.TOP_10K,
    RankTier.TOP_50K,
    RankTier.TOP_100K,
    RankTier.TOP_150K,
    RankTier.BEYOND_150K,
]

TIER_LABELS = [tier.label_es for tier in TIER_ORDER]


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
        title="Evolución del tramo BSR (agregación diaria)",
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=[tier.value for tier in TIER_ORDER],
        ticktext=TIER_LABELS,
        range=[0.5, RankTier.BEYOND_150K.value + 0.5],
        autorange=False,
    )
    fig.update_layout(
        yaxis_title="Tramo BSR",
        xaxis_title="Fecha",
        height=480,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def build_tier_distribution_chart(summary: BsrSummary) -> go.Figure:
    labels = list(summary.tier_distribution.keys())
    values = list(summary.tier_distribution.values())
    fig = px.bar(
        x=labels,
        y=values,
        labels={"x": "Tramo", "y": "% de días"},
        title="Distribución de tiempo por tramo",
    )
    fig.update_layout(height=360, margin=dict(l=40, r=20, t=60, b=80))
    fig.update_xaxes(tickangle=-35)
    return fig
