"""Recorded-style fixtures (hand-built to match documented response shapes; no live network)."""

SERP_IL = {
    "shopping_results": [
        {
            "title": "Anker 737 Power Bank 24000mAh Black",
            "link": "https://ksp.co.il/x",
            "source": "KSP",
            "price": "₪399.00",
            "extracted_price": 399.0,
            "rating": 4.7,
            "reviews": 120,
            "delivery": "Free delivery",
        },
        {
            "title": "Anker 737 Power Bank 24000mAh White",
            "link": "https://zap.co.il/y",
            "source": "Zap",
            "price": "₪389.00",
            "extracted_price": 389.0,
        },
        {
            "title": "Unrelated phone case",
            "link": "https://ivory.co.il/z",
            "source": "Ivory",
            "price": "₪29.90",
            "extracted_price": 29.9,
        },
        {"title": "no price", "link": "https://x"},
    ]
}

SERP_US = {
    "shopping_results": [
        {
            "title": "Anker 737 Power Bank PowerCore 24K black",
            "link": "https://amazon.com/a",
            "source": "Amazon.com",
            "price": "$109.99",
            "extracted_price": 109.99,
            "rating": 4.6,
        },
    ]
}

ALI = {
    "aliexpress_affiliate_product_query_response": {
        "resp_result": {
            "result": {
                "products": {
                    "product": [
                        {
                            "product_title": "Anker 737 Power Bank 24000mAh black",
                            "shop_name": "Anker Official Store",
                            "target_sale_price": "62.10",
                            "target_sale_price_currency": "USD",
                            "product_detail_url": "https://aliexpress.com/item/1.html",
                            "evaluate_rate": "96.0%",
                            "lastest_volume": "532",
                            "product_main_image_url": "https://img/1.jpg",
                        },
                        {"product_title": "broken", "target_sale_price": "bad"},
                    ]
                }
            }
        }
    }
}

EBAY = {
    "itemSummaries": [
        {
            "title": "Anker 737 Power Bank 24000mAh Black",
            "price": {"value": "95.00", "currency": "USD"},
            "itemWebUrl": "https://ebay.com/itm/1",
            "seller": {"username": "shop1", "feedbackPercentage": "99.5"},
            "shippingOptions": [{"shippingCost": {"value": "12.00", "currency": "USD"}}],
            "itemLocation": {"country": "US"},
            "image": {"imageUrl": "https://img/e.jpg"},
        }
    ]
}

BOI_XML = (
    '<message:GenericData xmlns:message="m" xmlns:generic="g"><generic:Series>'
    '<Obs TIME_PERIOD="2026-10-07" OBS_VALUE="3.70"/>'
    '<Obs TIME_PERIOD="2026-10-08" OBS_VALUE="3.65"/></generic:Series></message:GenericData>'
)
