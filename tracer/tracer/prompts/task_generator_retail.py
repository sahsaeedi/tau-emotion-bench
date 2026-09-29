"""Task-generator prompt for the retail domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the retail customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the user's EMAIL, from get_users_with_orders / get_user_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_users_with_orders (statuses=[...]; repeat a status to require several orders in it) or get_user_ids_with_n_orders ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): generate_new_address, get_user_ids_with_n_orders, get_product_variants, get_users_with_orders. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- Pending orders only: cancel_pending_order, modify_pending_order_address, modify_pending_order_payment, modify_pending_order_items (once per order; afterwards it is "pending (item modified)" and cannot be modified again). Delivered orders only: return_delivered_order_items, exchange_delivered_order_items (once per order; never both on the same order).
- modify_pending_order_payment: new method differs from the current one; the user needs >= 2 methods among credit_card/paypal (a gift card must cover the whole order).
- modify_pending_order_items / exchange: new items are AVAILABLE variants of the SAME product (get_product_variants); price increase charged to a payment_id the user holds (gift card needs balance), decrease refunded to it.
- Refunds: original payment method or an existing gift card of the user.
- modify_user_address: any user; generate_new_address gives a fresh address.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, my email is <email>. Please cancel my pending order <order_id>; I no longer need it."
- "Hi, my email is <email>. For my delivered order <order_id>, exchange item <item_id> for variant <new_item_id>; charge the difference to <payment_method_id>."
"""

USER_PROMPT = """TOOL-TRACE (retail). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
