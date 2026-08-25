"""Revolut Markets design tokens and global Streamlit theme injection."""

from __future__ import annotations

import streamlit as st

REVOLUT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --rv-bg-primary: #000000;
    --rv-bg-elevated: #141414;
    --rv-bg-card: #1C1C1E;
    --rv-bg-pill-active: #2C2C2E;
    --rv-text-primary: #FFFFFF;
    --rv-text-secondary: #8E8E93;
    --rv-text-tertiary: #636366;
    --rv-accent-purple: #8B5CF6;
    --rv-accent-cyan: #22D3EE;
    --rv-accent-amber: #F59E0B;
    --rv-positive: #34D759;
    --rv-negative: #FF453A;
    --rv-link: #007AFF;
    --rv-border: rgba(255, 255, 255, 0.06);
    --rv-radius-pill: 9999px;
    --rv-radius-card: 18px;
}

.stApp {
    background-color: var(--rv-bg-primary) !important;
    color: var(--rv-text-primary);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

#MainMenu, footer, header[data-testid="stHeader"] {
    visibility: hidden;
    height: 0;
}

.block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 5rem !important;
    max-width: 720px !important;
}

h1, h2, h3, .rv-title {
    color: var(--rv-text-primary) !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}

p, label, .stMarkdown, span {
    font-family: 'Inter', sans-serif !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.35rem;
    background: transparent;
    border-bottom: none;
    padding-bottom: 0.5rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--rv-text-secondary) !important;
    border-radius: var(--rv-radius-pill) !important;
    padding: 0.45rem 1rem !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    border: none !important;
}

.stTabs [aria-selected="true"] {
    background: var(--rv-bg-pill-active) !important;
    color: var(--rv-text-primary) !important;
}

.stButton > button[kind="primary"] {
    background: var(--rv-text-primary) !important;
    color: #000 !important;
    border: none !important;
    border-radius: var(--rv-radius-pill) !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.25rem !important;
}

.stButton > button[kind="secondary"] {
    background: var(--rv-bg-pill-active) !important;
    color: var(--rv-text-primary) !important;
    border: 1px solid var(--rv-border) !important;
    border-radius: var(--rv-radius-pill) !important;
}

.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"],
.stDateInput input, .stMultiSelect div[data-baseweb="select"] {
    background: var(--rv-bg-elevated) !important;
    color: var(--rv-text-primary) !important;
    border: 1px solid var(--rv-border) !important;
    border-radius: 12px !important;
}

.stMetric {
    background: var(--rv-bg-elevated);
    border: 1px solid var(--rv-border);
    border-radius: var(--rv-radius-card);
    padding: 0.75rem 1rem;
}

.stMetric label { color: var(--rv-text-secondary) !important; }
.stMetric [data-testid="stMetricValue"] { color: var(--rv-text-primary) !important; }

div[data-testid="stAlert"] {
    background: var(--rv-bg-card) !important;
    border: 1px solid var(--rv-border) !important;
    border-radius: var(--rv-radius-card) !important;
    color: var(--rv-text-primary) !important;
}

.stDataFrame { border-radius: var(--rv-radius-card); overflow: hidden; }

.rv-page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.25rem;
}

.rv-page-header h1 {
    font-size: 2rem;
    margin: 0;
    line-height: 1.1;
}

.rv-pill-row {
    display: flex;
    gap: 0.5rem;
    overflow-x: auto;
    padding: 0.25rem 0 1rem;
    scrollbar-width: none;
    -ms-overflow-style: none;
}
.rv-pill-row::-webkit-scrollbar { display: none; }

.rv-pill {
    flex-shrink: 0;
    padding: 0.45rem 1rem;
    border-radius: var(--rv-radius-pill);
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--rv-text-secondary);
    background: transparent;
    border: none;
    cursor: default;
    white-space: nowrap;
}

.rv-pill-active {
    background: var(--rv-bg-pill-active);
    color: var(--rv-text-primary);
}

.rv-kpi-row {
    display: flex;
    gap: 1.25rem;
    overflow-x: auto;
    margin-bottom: 1.25rem;
    padding-bottom: 0.25rem;
}

.rv-kpi {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    min-width: 0;
    flex: 1;
}

.rv-kpi-bar {
    width: 3px;
    height: 2.5rem;
    border-radius: 2px;
    flex-shrink: 0;
}

.rv-kpi-label {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--rv-text-primary);
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.rv-kpi-change {
    font-size: 0.8125rem;
    font-weight: 600;
    margin: 0.15rem 0 0;
}

.rv-kpi-change.positive { color: var(--rv-positive); }
.rv-kpi-change.negative { color: var(--rv-negative); }
.rv-kpi-change.neutral { color: var(--rv-text-secondary); }

.rv-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 1.5rem 0 0.75rem;
}

.rv-section-header h2 {
    font-size: 1.25rem !important;
    margin: 0 !important;
}

.rv-link {
    color: var(--rv-link);
    font-size: 0.9375rem;
    font-weight: 500;
    text-decoration: none;
}

.rv-index-row {
    display: flex;
    align-items: center;
    gap: 0.875rem;
    padding: 0.875rem 0;
    border-bottom: 1px solid var(--rv-border);
}

.rv-index-row:last-child { border-bottom: none; }

.rv-index-icon {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: var(--rv-bg-card);
    border: 1px solid var(--rv-border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--rv-text-primary);
    flex-shrink: 0;
    position: relative;
}

.rv-index-badge {
    position: absolute;
    bottom: -2px;
    right: -2px;
    font-size: 0.55rem;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 4px;
    background: var(--rv-bg-pill-active);
    color: var(--rv-text-secondary);
}

.rv-index-body { flex: 1; min-width: 0; }

.rv-index-title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--rv-text-primary);
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.rv-index-sub {
    font-size: 0.8125rem;
    color: var(--rv-text-secondary);
    margin: 0.15rem 0 0;
}

.rv-index-value {
    text-align: right;
    flex-shrink: 0;
}

.rv-index-num {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--rv-text-primary);
    margin: 0;
}

.rv-index-delta {
    font-size: 0.8125rem;
    font-weight: 600;
    margin: 0.15rem 0 0;
}

.rv-index-delta.positive { color: var(--rv-positive); }
.rv-index-delta.negative { color: var(--rv-negative); }
.rv-index-delta.neutral { color: var(--rv-text-secondary); }

.rv-empty {
    background: var(--rv-bg-elevated);
    border: 1px solid var(--rv-border);
    border-radius: var(--rv-radius-card);
    padding: 2rem 1.25rem;
    text-align: center;
    margin: 1rem 0;
}

.rv-empty-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--rv-text-primary);
    margin: 0 0 0.35rem;
}

.rv-empty-text {
    font-size: 0.875rem;
    color: var(--rv-text-secondary);
    margin: 0;
    line-height: 1.45;
}

.rv-error {
    background: rgba(255, 69, 58, 0.12);
    border: 1px solid rgba(255, 69, 58, 0.35);
    border-radius: var(--rv-radius-card);
    padding: 0.875rem 1rem;
    color: #FF6961;
    font-size: 0.875rem;
    margin: 0.75rem 0;
}

.rv-movement {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--rv-border);
}

.rv-movement:last-child { border-bottom: none; }

.rv-movement-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 0.35rem;
    flex-shrink: 0;
}

.rv-movement-dot.high { background: var(--rv-negative); }
.rv-movement-dot.medium { background: var(--rv-accent-amber); }

.rv-movement-text {
    font-size: 0.875rem;
    color: var(--rv-text-primary);
    line-height: 1.4;
    margin: 0;
}

.rv-card {
    background: var(--rv-bg-elevated);
    border: 1px solid var(--rv-border);
    border-radius: var(--rv-radius-card);
    padding: 1rem 1.125rem;
    margin-bottom: 1rem;
}

.rv-caption {
    font-size: 0.8125rem;
    color: var(--rv-text-tertiary);
    margin: 0.5rem 0 0;
}

.rv-axis-group {
    margin: 1rem 0 0.5rem;
}

.rv-axis-label {
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--rv-text-tertiary);
    margin: 0 0 0.5rem 0.25rem;
}

.js-plotly-plot .plotly .modebar { display: none !important; }
</style>
"""


def inject_revolut_theme() -> None:
    st.markdown(REVOLUT_CSS, unsafe_allow_html=True)


ACCENT_COLORS = {
    "purple": "#8B5CF6",
    "cyan": "#22D3EE",
    "amber": "#F59E0B",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#8E8E93", size=12),
    margin=dict(l=8, r=8, t=24, b=8),
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0,
        font=dict(color="#FFFFFF", size=11),
    ),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        color="#636366",
        linecolor="rgba(255,255,255,0.06)",
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)",
        zeroline=False,
        color="#636366",
    ),
)


def apply_revolut_layout(fig, *, height: int = 280):
    fig.update_layout(**PLOTLY_LAYOUT, height=height)
    return fig
