# Power BI Design System

## Product Tone

Professional analytical product. The report should feel like a sovereign-risk
briefing tool, not a generic chart gallery.

## Layout

- page title at top left
- run freshness and active score version at top right
- 2-4 primary visuals per page
- supporting evidence below the fold where needed
- consistent country selector placement

## Colour Semantics

Risk:

- lower risk: muted green-blue
- medium risk: amber
- high risk: red

Confidence:

- use a separate blue scale
- never use the risk scale for confidence

Diagnostics:

- neutral greys and blues
- diagnostic-only labels should be explicit text, not just colour

## Accessibility

- avoid colour-only meaning
- use direct labels on key cards
- keep tables sortable
- use tooltips for component definitions and caveats
- keep chart titles question-oriented

## Formatting

- risk scores: one decimal place
- ranks: integer
- confidence: percent-like 0-100 score, one decimal place
- coverage: percentage
- interval width and MAE: three decimals unless page context requires more

## Avoid

- pie charts unless a strict part-to-whole question needs one
- decorative imagery
- recomputing methodology in DAX
- hiding calibration limitations
