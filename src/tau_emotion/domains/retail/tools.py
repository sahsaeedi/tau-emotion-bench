"""Toolkit for the retail domain, ported from TRACER's environment
(tracer/tracer/envs/retail/).

16 tools, one per tool module in tracer/tracer/envs/retail/tools/, including
their checks, database writes and return values. Conversion rules from TRACER's tools:

- `data["orders"]` → `self.db.orders`.
- `return "Error: ..."`, and any exception TRACER's tool raises (e.g. a
  KeyError), → an exception with the same message. Both frameworks show
  exceptions to the agent as "Error: <message>".
- `return json.dumps(record)` → `_record_json(record)`, which leaves out
  fields the record never had, as TRACER's raw dict would.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.

Unlike upstream tau2-bench, returns and exchanges set "delivered (return
requested)" / "delivered (exchange requested)" and accept any order whose status
starts with "delivered", and modifying items leaves an order "pending", so it
can still be cancelled or modified again.
"""

import json
from typing import List, Literal, Optional

from pydantic import BaseModel

from tau_emotion.domains.retail.data_model import (
    Order,
    OrderPayment,
    RetailDB,
    UserAddress,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool


def _record_json(record: BaseModel, exclude: Optional[set[str]] = None) -> str:
    return json.dumps(record.model_dump(exclude_unset=True, exclude=exclude))


class RetailTools(ToolKitBase):  # Tools
    """All the tools for the retail domain."""

    db: RetailDB

    def __init__(self, db: RetailDB) -> None:
        super().__init__(db)

    def _get_order(self, order_id: str) -> Order:
        if order_id not in self.db.orders:
            raise ValueError("order not found")
        return self.db.orders[order_id]

    def _price_difference(
        self, order: Order, item_ids: List[str], new_item_ids: List[str]
    ) -> float:
        """TRACER's shared checks for exchanging or modifying items. Returns the
        total price difference (new minus old)."""
        all_item_ids = [item.item_id for item in order.items]
        for item_id in item_ids:
            if item_ids.count(item_id) > all_item_ids.count(item_id):
                raise ValueError(f"{item_id} not found")
        if len(item_ids) != len(new_item_ids):
            raise ValueError("the number of items to be exchanged should match")

        diff_price = 0
        for item_id, new_item_id in zip(item_ids, new_item_ids):
            item = [item for item in order.items if item.item_id == item_id][0]
            variants = self.db.products[item.product_id].variants
            if not (new_item_id in variants and variants[new_item_id].available):
                raise ValueError(f"new item {new_item_id} not found or available")
            diff_price += variants[new_item_id].price - item.price
        return diff_price

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The result rounded to two decimals, as a string.
        """
        if not all(char in "0123456789+-*/(). " for char in expression):
            raise ValueError("invalid characters in expression")
        return str(round(float(eval(expression, {"__builtins__": None}, {})), 2))  # noqa: S307

    @is_tool(ToolType.WRITE)
    def cancel_pending_order(
        self, order_id: str, reason: Literal["no longer needed", "ordered by mistake"]
    ) -> str:
        """Cancel a pending order. If the order is already processed or delivered, it cannot be cancelled. The agent needs to explain the cancellation detail and ask for explicit user confirmation (yes/no) to proceed. If the user confirms, the order status will be changed to 'cancelled' and the payment will be refunded. The refund will be added to the user's gift card balance immediately if the payment was made using a gift card, otherwise the refund would take 5-7 business days to process. The function returns the order details after the cancellation.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            reason: The reason for cancellation, which should be either 'no longer needed' or 'ordered by mistake'.

        Returns:
            The order details after the cancellation, as JSON.
        """
        order = self._get_order(order_id)
        if order.status != "pending":
            raise ValueError("non-pending order cannot be cancelled")
        if reason not in ["no longer needed", "ordered by mistake"]:
            raise ValueError("invalid reason")

        refunds = []
        for payment in order.payment_history:
            payment_id = payment.payment_method_id
            refunds.append(
                OrderPayment(
                    transaction_type="refund",
                    amount=payment.amount,
                    payment_method_id=payment_id,
                )
            )
            if "gift_card" in payment_id:  # refund to gift card immediately
                payment_method = self.db.users[order.user_id].payment_methods[
                    payment_id
                ]
                payment_method.balance += payment.amount
                payment_method.balance = round(payment_method.balance, 2)

        order.status = "cancelled"
        order.cancel_reason = reason
        order.payment_history.extend(refunds)
        return _record_json(order)

    @is_tool(ToolType.WRITE)
    def exchange_delivered_order_items(
        self,
        order_id: str,
        item_ids: List[str],
        new_item_ids: List[str],
        payment_method_id: str,
    ) -> str:
        """Exchange items in a delivered order to new items of the same product type. For a delivered order, return or exchange can be only done once by the agent. The agent needs to explain the exchange detail and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            item_ids: The item ids to be exchanged, each such as '1008292230'. There could be duplicate items in the list.
            new_item_ids: The item ids to be exchanged for, each such as '1008292230'. There could be duplicate items in the list. Each new item id should match the item id in the same position and be of the same product.
            payment_method_id: The payment method id to pay or receive refund for the item price difference, such as 'gift_card_0000000' or 'credit_card_0000000'. These can be looked up from the user or order details.

        Returns:
            The order details after the exchange, as JSON.
        """
        order = self._get_order(order_id)
        # TRACER's tool accepts any "delivered..." status, so an order can be
        # exchanged again.
        if not order.status.startswith("delivered"):
            raise ValueError("non-delivered order cannot be exchanged")

        diff_price = round(self._price_difference(order, item_ids, new_item_ids), 2)

        payment_methods = self.db.users[order.user_id].payment_methods
        if payment_method_id not in payment_methods:
            raise ValueError("payment method not found")
        payment_method = payment_methods[payment_method_id]
        if payment_method.source == "gift_card" and payment_method.balance < diff_price:
            raise ValueError(
                "insufficient gift card balance to pay for the price difference"
            )

        order.status = "delivered (exchange requested)"
        order.exchange_items = sorted(item_ids)
        order.exchange_new_items = sorted(new_item_ids)
        order.exchange_payment_method_id = payment_method_id
        order.exchange_price_difference = diff_price
        return _record_json(order)

    @is_tool(ToolType.READ)
    def find_user_id_by_email(self, email: str) -> str:
        """Find user id by email. If the user is not found, the function will return an error message.

        Args:
            email: The email of the user, such as 'something@example.com'.

        Returns:
            The user id.
        """
        for user_id, user in self.db.users.items():
            if user.email.lower() == email.lower():
                return user_id
        raise ValueError("user not found")

    @is_tool(ToolType.READ)
    def find_user_id_by_name_zip(
        self, first_name: str, last_name: str, zip: str
    ) -> str:
        """Find user id by first name, last name, and zip code. If the user is not found, the function will return an error message. By default, find user id by email, and only call this function if the user is not found by email or cannot remember email.

        Args:
            first_name: The first name of the customer, such as 'John'.
            last_name: The last name of the customer, such as 'Doe'.
            zip: The zip code of the customer, such as '12345'.

        Returns:
            The user id.
        """
        for user_id, user in self.db.users.items():
            if (
                user.name.first_name.lower() == first_name.lower()
                and user.name.last_name.lower() == last_name.lower()
                and user.address.zip == zip
            ):
                return user_id
        raise ValueError("user not found")

    @is_tool(ToolType.READ)
    def get_order_details(self, order_id: str) -> str:
        """Get the status and details of an order.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.

        Returns:
            The order details, as JSON.
        """
        return _record_json(self._get_order(order_id))

    @is_tool(ToolType.READ)
    def get_product_details(self, product_id: str) -> str:
        """Get the inventory details of a product.

        Args:
            product_id: The product id, such as '6086499569'. Be careful the product id is different from the item id.

        Returns:
            The product details, as JSON.
        """
        if product_id in self.db.products:
            return _record_json(self.db.products[product_id])
        raise ValueError("product not found")

    @is_tool(ToolType.READ)
    def get_user_details(self, user_id: str) -> str:
        """Get the details of a user, including their orders.

        Args:
            user_id: The user id, such as 'sara_doe_496'.

        Returns:
            The user details, as JSON.
        """
        if user_id in self.db.users:
            # Left out of the output, although TRACER's tool returns it.
            return _record_json(self.db.users[user_id], exclude={"user_id"})
        raise ValueError("user not found")

    @is_tool(ToolType.READ)
    def list_all_product_types(self) -> str:
        """List the name and product id of all product types. Each product type has a variety of different items with unique item ids and options. There are only 50 product types in the store.

        Returns:
            A JSON object mapping product names to product ids, sorted by name.
        """
        product_dict = {
            product.name: product.product_id for product in self.db.products.values()
        }
        return json.dumps(dict(sorted(product_dict.items())))

    @is_tool(ToolType.WRITE)
    def modify_pending_order_address(
        self,
        order_id: str,
        address1: str,
        address2: str,
        city: str,
        state: str,
        country: str,
        zip: str,
    ) -> str:
        """Modify the shipping address of a pending order. The agent needs to explain the modification detail and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            address1: The first line of the address, such as '123 Main St'.
            address2: The second line of the address, such as 'Apt 1' or ''.
            city: The city, such as 'San Francisco'.
            state: The state, such as 'CA'.
            country: The country, such as 'USA'.
            zip: The zip code, such as '12345'.

        Returns:
            The order details after the modification, as JSON.
        """
        order = self._get_order(order_id)
        if order.status != "pending":
            raise ValueError("non-pending order cannot be modified")
        order.address = UserAddress(
            address1=address1,
            address2=address2,
            city=city,
            state=state,
            country=country,
            zip=zip,
        )
        return _record_json(order)

    @is_tool(ToolType.WRITE)
    def modify_pending_order_items(
        self,
        order_id: str,
        item_ids: List[str],
        new_item_ids: List[str],
        payment_method_id: str,
    ) -> str:
        """Modify items in a pending order to new items of the same product type. For a pending order, this function can only be called once. The agent needs to explain the exchange detail and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            item_ids: The item ids to be modified, each such as '1008292230'. There could be duplicate items in the list.
            new_item_ids: The item ids to be modified for, each such as '1008292230'. There could be duplicate items in the list. Each new item id should match the item id in the same position and be of the same product.
            payment_method_id: The payment method id to pay or receive refund for the item price difference, such as 'gift_card_0000000' or 'credit_card_0000000'. These can be looked up from the user or order details.

        Returns:
            The order details after the modification, as JSON.
        """
        order = self._get_order(order_id)
        if order.status != "pending":
            raise ValueError("non-pending order cannot be modified")

        diff_price = self._price_difference(order, item_ids, new_item_ids)

        payment_methods = self.db.users[order.user_id].payment_methods
        if payment_method_id not in payment_methods:
            raise ValueError("payment method not found")
        payment_method = payment_methods[payment_method_id]
        if payment_method.source == "gift_card" and payment_method.balance < diff_price:
            raise ValueError("insufficient gift card balance to pay for the new item")

        order.payment_history.append(
            OrderPayment(
                transaction_type="payment" if diff_price > 0 else "refund",
                amount=abs(diff_price),
                payment_method_id=payment_method_id,
            )
        )
        if payment_method.source == "gift_card":
            payment_method.balance -= diff_price
            payment_method.balance = round(payment_method.balance, 2)

        # Each item takes its own new variant's price and options.
        for item_id, new_item_id in zip(item_ids, new_item_ids):
            item = [item for item in order.items if item.item_id == item_id][0]
            variant = self.db.products[item.product_id].variants[new_item_id]
            item.item_id = new_item_id
            item.price = variant.price
            item.options = variant.options
        # TRACER's tool leaves the order "pending", so it can still be cancelled
        # or modified.
        order.status = "pending"
        return _record_json(order)

    @is_tool(ToolType.WRITE)
    def modify_pending_order_payment(
        self, order_id: str, payment_method_id: str
    ) -> str:
        """Modify the payment method of a pending order. The agent needs to explain the modification detail and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            payment_method_id: The payment method id to pay or receive refund for the item price difference, such as 'gift_card_0000000' or 'credit_card_0000000'. These can be looked up from the user or order details.

        Returns:
            The order details after the modification, as JSON.
        """
        order = self._get_order(order_id)
        if order.status != "pending":
            raise ValueError("non-pending order cannot be modified")

        payment_methods = self.db.users[order.user_id].payment_methods
        if payment_method_id not in payment_methods:
            raise ValueError("payment method not found")

        if (
            len(order.payment_history) > 1
            or order.payment_history[0].transaction_type != "payment"
        ):
            raise ValueError("there should be exactly one payment for a pending order")
        old_payment_method_id = order.payment_history[0].payment_method_id
        if old_payment_method_id == payment_method_id:
            raise ValueError(
                "the new payment method should be different from the current one"
            )

        amount = order.payment_history[0].amount
        payment_method = payment_methods[payment_method_id]
        if payment_method.source == "gift_card" and payment_method.balance < amount:
            raise ValueError("insufficient gift card balance to pay for the order")

        order.payment_history.extend(
            [
                OrderPayment(
                    transaction_type="payment",
                    amount=amount,
                    payment_method_id=payment_method_id,
                ),
                OrderPayment(
                    transaction_type="refund",
                    amount=amount,
                    payment_method_id=old_payment_method_id,
                ),
            ]
        )
        if payment_method.source == "gift_card":
            payment_method.balance -= amount
            payment_method.balance = round(payment_method.balance, 2)
        if "gift_card" in old_payment_method_id:
            old_payment_method = payment_methods[old_payment_method_id]
            old_payment_method.balance += amount
            old_payment_method.balance = round(old_payment_method.balance, 2)
        return _record_json(order)

    @is_tool(ToolType.WRITE)
    def modify_user_address(
        self,
        user_id: str,
        address1: str,
        address2: str,
        city: str,
        state: str,
        country: str,
        zip: str,
    ) -> str:
        """Modify the default address of a user. The agent needs to explain the modification detail and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            user_id: The user id, such as 'sara_doe_496'.
            address1: The first line of the address, such as '123 Main St'.
            address2: The second line of the address, such as 'Apt 1' or ''.
            city: The city, such as 'San Francisco'.
            state: The state, such as 'CA'.
            country: The country, such as 'USA'.
            zip: The zip code, such as '12345'.

        Returns:
            The user details after the modification, as JSON.
        """
        if user_id not in self.db.users:
            raise ValueError("user not found")
        user = self.db.users[user_id]
        user.address = UserAddress(
            address1=address1,
            address2=address2,
            city=city,
            state=state,
            country=country,
            zip=zip,
        )
        return _record_json(user, exclude={"user_id"})

    @is_tool(ToolType.WRITE)
    def return_delivered_order_items(
        self, order_id: str, item_ids: List[str], payment_method_id: str
    ) -> str:
        """Return some items of a delivered order. The order status will be changed to 'return requested'. The agent needs to explain the return detail and ask for explicit user confirmation (yes/no) to proceed. The user will receive follow-up email for how and where to return the item.

        Args:
            order_id: The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id.
            item_ids: The item ids to be returned, each such as '1008292230'. There could be duplicate items in the list.
            payment_method_id: The payment method id to pay or receive refund for the item price difference, such as 'gift_card_0000000' or 'credit_card_0000000'. These can be looked up from the user or order details.

        Returns:
            The order details after requesting the return, as JSON.
        """
        order = self._get_order(order_id)
        # TRACER's tool accepts any "delivered..." status, so an order can be
        # returned again.
        if not order.status.startswith("delivered"):
            raise ValueError("non-delivered order cannot be returned")

        if payment_method_id not in self.db.users[order.user_id].payment_methods:
            raise ValueError("payment method not found")
        if (
            "gift_card" not in payment_method_id
            and payment_method_id != order.payment_history[0].payment_method_id
        ):
            raise ValueError(
                "payment method should be either the original payment method or a gift card"
            )

        all_item_ids = [item.item_id for item in order.items]
        for item_id in item_ids:
            if item_ids.count(item_id) > all_item_ids.count(item_id):
                raise ValueError("some item not found")

        order.status = "delivered (return requested)"
        order.return_items = sorted(item_ids)
        order.return_payment_method_id = payment_method_id
        return _record_json(order)

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new information or change the database, but just append the thought to the log. Use it when complex reasoning or some cache memory is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""

    @is_tool(ToolType.GENERIC)
    def transfer_to_human_agents(self, summary: str) -> str:
        """Transfer the user to a human agent, with a summary of the user's issue. Only transfer if the user explicitly asks for a human agent, or if the user's issue cannot be resolved by the agent with the available tools.

        Args:
            summary: A summary of the user's issue.

        Returns:
            A confirmation message.
        """
        return "Transfer successful"


if __name__ == "__main__":
    from tau_emotion.domains.retail.utils import RETAIL_DB_PATH

    retail = RetailTools(RetailDB.load(RETAIL_DB_PATH))
    print(retail.get_statistics())
