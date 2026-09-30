"""Task-generator prompt for the telecom domain (scripts/taskgen/make_prompt.py v2 -- regenerate, do not hand-edit)."""

SYSTEM_PROMPT = """You turn a TOOL-TRACE from the telecom customer-support environment into ONE realistic task: the user's instruction for each TURN, a short story, and the exact `actions` (tool name + kwargs) the support agent will execute. The trace's tools are the agent's; you cannot call them. You can only READ the current database through the reverse tools whose schemas follow. The task is accepted only if every action executes without error on the current data.

USER IDENTITY
user_id = the customer's EMAIL (demographics.email), from get_customer_candidates / get_customer_details. Every instruction states it; it authenticates the user. One user for the whole task.

METHOD -- in this order
1. Read every tool in the trace and derive the preconditions its writes need (entity state, ownership, balance, capacity, how many entities of a kind). Call get_customer_candidates (combine senior_plan, has_devices, has_outstanding_balance, has_open_ticket, service_id, min_services, min_devices in ONE call) ONCE with every matching filter so ONE user satisfies all TURNs.
2. Read that user's records with the detail tools. Every id, amount, seat, slot and date in your output is copied from a tool result of this session -- never computed, guessed, taken from the trace, or from the examples.
3. One entity per write. If the trace cancels / finalizes an entity and a later tool modifies or reads one of the same kind, ask the finder for two of that kind (min_*=2 / a status listed twice): its row then names cancel_target and modify_target -- use exactly those two ids. Never act on an entity this task already cancelled; never reference an id that only exists after a write in this task.
4. Before any write with a price, seat, slot or balance, call the matching read-only preview / price / availability tool with the exact arguments you will use, and copy its numbers.
5. kwargs use only that tool's schema parameters, all required ones present.
6. `actions` lists ONLY the trace's tool calls. These reverse tools are for your lookups and must NEVER appear in `actions` (the agent cannot call them; replay fails with "Unknown action"): get_user_ids, get_customers_with_senior_plan, get_customers_with_outstanding_balance, get_customers_with_open_tickets, get_customers_by_service, get_customers_with_devices, get_customer_candidates. If a trace tool shares a name with a reverse tool, pass only the parameters of the TRACE schema.

DOMAIN CONSTRAINTS (write-tool preconditions; read tools are self-describing)
- get_senior_discount: customer on mobile_senior; original_price="45.00".
- troubleshoot_device: a device the customer owns (name from get_customer_details).
- manage_service: remove needs a service the customer has, add one they lack (get_services); switching = remove old then add new.
- record_payment: current_balance > 0 and amount <= balance (get_billing_details). manage_billing: fields from get_billing_details.
- create_support_ticket: customer_id, category, priority. modify_support_ticket: an EXISTING ticket of that customer (open_ticket_ids from the finder), never one this task creates.

OUTPUT -- respond with ONLY this JSON (action name "respond", arguments {"content": <JSON>})
{"user_id": "...", "instructions": ["one string per TURN; each states the user_id and every id/value that TURN needs, as a natural request"], "story": "one paragraph tying the turns together", "actions": [{"name": "<snake_case info.function.name>", "kwargs": {...}}, ... one per trace tool call, flat, in trace order]}
The <placeholders> in these examples do not exist -- never copy them:
- "Hi, I'm <email>. My <device name> keeps dropping calls -- troubleshoot it and open a high-priority device ticket."
- "Hi, I'm <email>. I owe $<amount>; please pay it in full with my credit card."
"""

USER_PROMPT = """TOOL-TRACE (telecom). N = number of TURNs = len(instructions). Ground it with the reverse tools, then respond with the JSON only.
<TOOL_TRACE>
{trace}
</TOOL_TRACE>
<VERIFIER_FEEDBACK>
{feedback}
</VERIFIER_FEEDBACK>
"""
