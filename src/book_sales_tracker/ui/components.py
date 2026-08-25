"""Revolut-style HTML components for Streamlit."""

from __future__ import annotations

import html

import streamlit as st

from book_sales_tracker.ui.revolut_theme import ACCENT_COLORS


def _esc(value: str | float | int | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def page_header(title: str, subtitle: str | None = None) -> None:
    sub = f'<p class="rv-caption">{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div class="rv-page-header">
            <div>
                <h1 class="rv-title">{_esc(title)}</h1>
                {sub}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def market_pills(labels: list[str], active: str) -> None:
    pills = []
    for label in labels:
        css = "rv-pill rv-pill-active" if label == active else "rv-pill"
        pills.append(f'<span class="{css}">{_esc(label)}</span>')
    st.markdown(
        f'<div class="rv-pill-row">{"".join(pills)}</div>',
        unsafe_allow_html=True,
    )


def timeframe_pills(labels: list[str], active: str) -> None:
    market_pills(labels, active)


def kpi_strip(items: list[dict]) -> None:
    """Each item: label, change_text, change_class (positive|negative|neutral), accent."""
    blocks = []
    for item in items:
        accent = ACCENT_COLORS.get(item.get("accent", "purple"), item.get("accent", "#8B5CF6"))
        change_class = item.get("change_class", "neutral")
        blocks.append(
            f"""
            <div class="rv-kpi">
                <div class="rv-kpi-bar" style="background:{_esc(accent)}"></div>
                <div>
                    <p class="rv-kpi-label">{_esc(item["label"])}</p>
                    <p class="rv-kpi-change {change_class}">{_esc(item["change_text"])}</p>
                </div>
            </div>
            """
        )
    st.markdown(f'<div class="rv-kpi-row">{"".join(blocks)}</div>', unsafe_allow_html=True)


def section_header(title: str, link_text: str | None = None) -> None:
    link = f'<span class="rv-link">{_esc(link_text)}</span>' if link_text else ""
    st.markdown(
        f"""
        <div class="rv-section-header">
            <h2>{_esc(title)}</h2>
            {link}
        </div>
        """,
        unsafe_allow_html=True,
    )


def index_row(
    *,
    icon: str,
    badge: str | None,
    title: str,
    subtitle: str,
    value: str,
    delta: str,
    delta_class: str = "neutral",
) -> None:
    badge_html = f'<span class="rv-index-badge">{_esc(badge)}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="rv-index-row">
            <div class="rv-index-icon">{_esc(icon)}{badge_html}</div>
            <div class="rv-index-body">
                <p class="rv-index-title">{_esc(title)}</p>
                <p class="rv-index-sub">{_esc(subtitle)}</p>
            </div>
            <div class="rv-index-value">
                <p class="rv-index-num">{_esc(value)}</p>
                <p class="rv-index-delta {delta_class}">{_esc(delta)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def movement_row(message: str, *, severity: str = "medium") -> None:
    dot_class = "high" if severity == "high" else "medium"
    st.markdown(
        f"""
        <div class="rv-movement">
            <div class="rv-movement-dot {dot_class}"></div>
            <p class="rv-movement-text">{_esc(message)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, text: str) -> None:
    st.markdown(
        f"""
        <div class="rv-empty">
            <p class="rv-empty-title">{_esc(title)}</p>
            <p class="rv-empty-text">{_esc(text)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def error_banner(message: str) -> None:
    st.markdown(f'<div class="rv-error">{_esc(message)}</div>', unsafe_allow_html=True)


def axis_label(text: str) -> None:
    st.markdown(f'<p class="rv-axis-label">{_esc(text)}</p>', unsafe_allow_html=True)
