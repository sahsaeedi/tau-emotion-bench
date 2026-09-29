# Copyright Sierra

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetProductVariants(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], product_id: str) -> str:
        products = data["products"]
        if product_id not in products:
            return "Error: product not found"
        variants = [
            variant
            for variant in products[product_id]["variants"].values()
            if variant["available"]
        ]
        return json.dumps(variants)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_product_variants",
                "description": "Get the variants of a product. Each product has a variety of different items with unique item ids and options. There are only 50 product types in the store.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "The product id, such as '9523456873'. Be careful the product id is different from the item id.",
                        },
                    },
                    "required": ["product_id"],
                },
            },
        }
