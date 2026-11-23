"""Editorial masthead header displaying title, period, source row count and IPCA base."""

from __future__ import annotations

from dash import html

from bh_itbi.formatting import number
from bh_itbi.text import shared as text


def masthead(source_rows: int, eligible_rows: int) -> html.Header:
    """Render the top editorial masthead and provenance definition list."""
    return html.Header(
        [
            html.Div(
                [
                    html.Span(text.MASTHEAD_EYEBROW, className="eyebrow"),
                    html.A(
                        text.MASTHEAD_ABOUT_LINK,
                        href="#metodologia",
                        className="about-link",
                    ),
                ],
                className="masthead-top",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H1(text.APP_TITLE),
                            html.P(text.APP_SUBTITLE, className="subtitle"),
                        ],
                        className="masthead-title",
                    ),
                    html.Div(
                        [
                            html.P(text.MASTHEAD_META_LABEL, className="meta-label"),
                            html.Dl(
                                [
                                    html.Dt(text.PERIOD_LABEL),
                                    html.Dd(text.MASTHEAD_PERIOD_DD),
                                    html.Dt(text.MASTHEAD_SOURCE_ROWS_DT),
                                    html.Dd(number(source_rows)),
                                    html.Dt(text.MASTHEAD_ELIGIBLE_ROWS_DT),
                                    html.Dd(number(eligible_rows)),
                                    html.Dt(text.MASTHEAD_REAL_DT),
                                    html.Dd(text.MASTHEAD_REAL_DD),
                                ],
                                className="masthead-facts",
                            ),
                        ],
                        className="masthead-meta",
                    ),
                ],
                className="masthead-main",
            ),
        ],
        className="masthead",
    )
