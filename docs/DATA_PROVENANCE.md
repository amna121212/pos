# Seed data provenance

Nothing in this database is a sales export from a real Lahore restaurant. The three businesses are fictional:

- Lahore Grill House, Johar Town and DHA Phase 5
- Urban Bites Lahore, Gulberg III and Model Town
- Daily Mart Lahore, Wapda Town and Faisal Town

## Categories

| Code | Category | What it is |
| --- | --- | --- |
| PHASE1_MASTER | MANUALLY_CURATED | Original businesses, branches, short menus, registers and printers |
| PHASE2_DEMO_ORDERS | APPLICATION_GENERATED | 24 small paid tickets. Their tax is zero because that was the original demo rule |
| PHASE3_STOCK_DEMO | APPLICATION_GENERATED | One purchase and one transfer per business |
| PHASE4_CATALOG | MANUALLY_CURATED | Expanded menu, grocery list, ingredients, representative recipes, staff personas, hours and tax rules |
| SYNTHETIC_HISTORY_V1 | SYNTHETIC_HISTORICAL | Deterministic tickets from 1 May 2025 through 31 October 2026 |

`businesses.created_at` is the moment the demo row was inserted on the server. It is not the fictional opening day. `business_settings.trading_since` is 1 May 2025 and is the start of the synthetic trading story.

## Prices and costs

Menu and grocery prices are sample PKR amounts chosen so that margins, deals and the PKR 20 second-branch difference are easy to explain. They are not current market prices and were not collected from a public menu. Ingredient `standard_cost` values are the same kind of sample.

Where a recipe exists, estimated gross profit uses the recipe roll-up. Otherwise it uses `products.base_cost`. Historical tickets keep the branch price that was current when the history was generated. There is no separate collected price list for 2025.

## Planted patterns

These were written into the generator so reports have something to show. They are hypotheses in a simulation, not findings about real demand.

- Grill House dinner is busier than lunch. Johar Town sells more BBQ. DHA sells more of the higher-priced items.
- Urban Bites Gulberg is busier at lunch and late evening, with more burgers and shawarma.
- Daily Mart Wapda Town sells more staples. Faisal Town sells more snacks and drinks. Summer months add a small extra grocery count.
- December and January add a small extra Grill House count.
- 18 February 2026 through 19 March 2026 adds an iftar-style increase at Grill House only. The dates are a labelled scenario, not a claim about moon sighting or real restaurant sales.
- A few products have popularity zero so slow-mover reports are not empty: Tomato Soup, Tuna Pasta and Fenugreek Seeds.
- Sunday reconciliations are short by 20 PKR on purpose.

## People

Staff names are fictional coursework personas. Emails use `@example.invalid`. Passwords are random hashes. No password is stored in source code or printed by the seed. This phase does not enable a login screen.

## What is not claimed

- Physical printers, camera scanning and a POS screen are not implemented.
- Grok is not called. Recommendations come from SQL totals and a small rule list.
- Tax rates are illustrative. They are not FBR or PRA advice.
- Recipes cover representative popular items, not every SKU. Unmapped items do not deduct ingredients.
- Modifier add-ons such as extra raita change the price and do not deduct extra stock.
