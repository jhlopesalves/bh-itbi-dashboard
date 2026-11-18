"""Expandable methodology section and page footer with data provenance links."""

from __future__ import annotations

from dash import html

from bh_itbi.config import SOURCE_BLOB_URL, SOURCE_URL
from bh_itbi.text import methodology as text


def methodology() -> html.Details:
    """Render the expandable methodology, screening criteria and provenance section."""
    return html.Details(
        [
            html.Summary(text.METHODOLOGY_SUMMARY),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_OBSERVED_HEADING),
                            html.P(text.METHODOLOGY_OBSERVED_P1),
                            html.P(text.METHODOLOGY_OBSERVED_P2),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_TIME_HEADING),
                            html.P(text.METHODOLOGY_TIME_P1),
                            html.P(text.METHODOLOGY_TIME_P2),
                        ]
                    ),
                    html.Div(
                        [
                            html.H3(text.METHODOLOGY_GEO_HEADING),
                            html.P(text.METHODOLOGY_GEO_P1),
                            html.P(
                                [
                                    text.METHODOLOGY_GEO_P2_PREFIX,
                                    html.A(
                                        text.METHODOLOGY_DICTIONARY_LINK,
                                        href=f"{SOURCE_BLOB_URL}/DATA_DICTIONARY.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                    " · ",
                                    html.A(
                                        text.METHODOLOGY_VERSION_LINK,
                                        href=f"{SOURCE_BLOB_URL}/README.md",
                                        target="_blank",
                                        rel="noopener noreferrer",
                                    ),
                                ]
                            ),
                        ]
                    ),
                ],
                className="methodology-grid",
            ),
        ],
        id="metodologia",
        className="methodology",
    )


def footer() -> html.Footer:
    """Render the application footer with source attribution and Hugging Face link."""
    return html.Footer(
        [
            html.Span(text.FOOTER_BRAND, className="footer-brand"),
            html.P(text.FOOTER_PROVENANCE),
            html.A(
                text.FOOTER_SOURCE_LINK,
                href=SOURCE_URL,
                target="_blank",
                rel="noopener noreferrer",
            ),
        ],
        className="footer",
    )
