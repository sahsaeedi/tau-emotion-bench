# Retail Mock Data

This is the retail database from τ-bench
([Yao et al., 2024](https://arxiv.org/abs/2406.12045)).

Shared by both splits (at the top of `data/`):
- `products.json`: products, where each product has variants (e.g., size, color)

Per split (in `test/` and `train/`):
- `users.json`: users with their emails, addresses, and orders
- `orders.json`: orders that can be operated upon

`load_data(split)` in `__init__.py` merges the shared file with one split's files.
Check `../tools` for mock APIs on top of this data.

### How τ-bench generated it

The τ-bench paper describes the generation process for each database. In general, it involves the following stages:

1. Design the type and schema of each database. Can use GPT for co-brainstorming but has to be human decided as it is the foundation of everything else.
2. For each schema, figure out which parts can be programmaticly generated and which parts need GPT. For example,
    - Product types (shirt, lamp, pen) and user names (Sara, John, Noah) need GPT generation
    - Product price and shipping date can be generated via code
3. Use GPT to generate seed data (first names, last names, addresses, cities, etc.), then use a program to compose them with other code generated data. Code-based database construction is more reliable than GPT-based database construction (e.g., give some example user profiles and ask GPT to generate more --- issues with diversity and reliability).
