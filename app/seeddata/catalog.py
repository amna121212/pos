"""Curated Lahore demo menu, grocery list, ingredients and recipes.

Prices and costs are coursework sample PKR amounts chosen so margins,
combos and branch differences are explainable. They are not live market prices.
Dish names are generic foods. The businesses themselves are fictional.
"""
from collections import namedtuple

Product = namedtuple("Product", "sku name category price cost popularity tag")
Ingredient = namedtuple("Ingredient", "sku name unit reorder cost shelf_days")

# Popularity and kitchen/retail tag for the Phase 1 products already in the database.
EXISTING_META = {
    ("lahore-grill-house", "BBQ-001"): (9, "bbq"),
    ("lahore-grill-house", "BBQ-002"): (8, "bbq"),
    ("lahore-grill-house", "BBQ-003"): (6, "premium"),
    ("lahore-grill-house", "BBQ-004"): (8, "karahi"),
    ("lahore-grill-house", "RIC-001"): (9, "rice"),
    ("lahore-grill-house", "RIC-002"): (4, "rice"),
    ("lahore-grill-house", "DRI-001"): (5, "drink"),
    ("lahore-grill-house", "DRI-002"): (4, "drink"),
    ("urban-bites-lahore", "BUR-001"): (7, "burger"),
    ("urban-bites-lahore", "BUR-002"): (9, "burger"),
    ("urban-bites-lahore", "BUR-003"): (5, "premium"),
    ("urban-bites-lahore", "SID-001"): (6, "side"),
    ("urban-bites-lahore", "SID-002"): (4, "side"),
    ("urban-bites-lahore", "DRI-001"): (5, "drink"),
    ("urban-bites-lahore", "DRI-002"): (4, "drink"),
    ("urban-bites-lahore", "DRI-003"): (6, "drink"),
    ("daily-mart-lahore", "DAI-001"): (9, "staple"),
    ("daily-mart-lahore", "DAI-002"): (6, "staple"),
    ("daily-mart-lahore", "DAI-003"): (4, "staple"),
    ("daily-mart-lahore", "BAK-001"): (8, "staple"),
    ("daily-mart-lahore", "BAK-002"): (5, "staple"),
    ("daily-mart-lahore", "BEV-001"): (4, "beverage"),
    ("daily-mart-lahore", "BEV-002"): (7, "beverage"),
    ("daily-mart-lahore", "PAN-001"): (6, "staple"),
    ("daily-mart-lahore", "PAN-002"): (8, "staple"),
}

NEW_PRODUCTS = {
    "lahore-grill-house": [
        Product("LGH-KAR-001", "Chicken Karahi Full", "Karahi", 2450, 1320, 8, "karahi"),
        Product("LGH-KAR-002", "Mutton Karahi Half", "Karahi", 2680, 1540, 6, "karahi"),
        Product("LGH-KAR-003", "Mutton Karahi Full", "Karahi", 4200, 2400, 4, "premium"),
        Product("LGH-KAR-004", "White Chicken Karahi Half", "Karahi", 1680, 900, 4, "karahi"),
        Product("LGH-KAR-005", "Boneless Chicken Karahi", "Karahi", 1890, 1040, 5, "karahi"),
        Product("LGH-KAR-006", "Daal Karahi", "Karahi", 720, 310, 3, "karahi"),
        Product("LGH-HAN-001", "Chicken Handi Half", "Handi", 1550, 860, 6, "handi"),
        Product("LGH-HAN-002", "Chicken Handi Full", "Handi", 2650, 1420, 5, "handi"),
        Product("LGH-HAN-003", "Mutton Handi Half", "Handi", 2480, 1460, 4, "premium"),
        Product("LGH-HAN-004", "Paneer Handi", "Handi", 980, 480, 2, "handi"),
        Product("LGH-HAN-005", "Reshmi Handi", "Handi", 1750, 960, 3, "handi"),
        Product("LGH-BBQ-001", "Beef Behari Boti", "BBQ", 980, 540, 7, "bbq"),
        Product("LGH-BBQ-002", "Chicken Reshmi Kabab", "BBQ", 860, 450, 6, "bbq"),
        Product("LGH-BBQ-003", "Gola Kabab", "BBQ", 640, 320, 5, "bbq"),
        Product("LGH-BBQ-004", "Lamb Chops", "BBQ", 1450, 890, 4, "premium"),
        Product("LGH-BBQ-005", "Grilled Fish Tikka", "BBQ", 1120, 640, 3, "bbq"),
        Product("LGH-BBQ-006", "Chicken Boti", "BBQ", 790, 410, 6, "bbq"),
        Product("LGH-BBQ-007", "Seekh Kebab Roll", "BBQ", 420, 190, 6, "bbq"),
        Product("LGH-BBQ-008", "Chicken Malai Roll", "BBQ", 450, 200, 5, "bbq"),
        Product("LGH-BBQ-009", "Grilled Prawns", "BBQ", 1650, 980, 2, "premium"),
        Product("LGH-RIC-001", "Mutton Biryani", "Rice", 640, 340, 7, "rice"),
        Product("LGH-RIC-002", "Beef Biryani", "Rice", 610, 330, 5, "rice"),
        Product("LGH-RIC-003", "Plain Basmati Rice", "Rice", 280, 110, 3, "rice"),
        Product("LGH-RIC-004", "Zeera Rice", "Rice", 320, 130, 2, "rice"),
        Product("LGH-CHI-001", "Chicken Manchurian", "Chinese", 890, 430, 5, "chinese"),
        Product("LGH-CHI-002", "Egg Fried Rice", "Chinese", 520, 220, 4, "chinese"),
        Product("LGH-CHI-003", "Chicken Chow Mein", "Chinese", 740, 340, 4, "chinese"),
        Product("LGH-CHI-004", "Hot and Sour Soup", "Chinese", 420, 160, 3, "chinese"),
        Product("LGH-CHI-005", "Beef Chilli Dry", "Chinese", 980, 520, 3, "chinese"),
        Product("LGH-CHI-006", "Chicken Corn Soup", "Chinese", 390, 150, 4, "chinese"),
        Product("LGH-CHI-007", "Vegetable Spring Rolls", "Chinese", 450, 180, 2, "chinese"),
        Product("LGH-CHI-008", "Lemon Chicken", "Chinese", 860, 400, 2, "chinese"),
        Product("LGH-BRD-001", "Roghni Naan", "Breads", 70, 25, 9, "bread"),
        Product("LGH-BRD-002", "Garlic Naan", "Breads", 90, 30, 8, "bread"),
        Product("LGH-BRD-003", "Tandoori Roti", "Breads", 30, 10, 9, "bread"),
        Product("LGH-BRD-004", "Keema Naan", "Breads", 220, 110, 4, "bread"),
        Product("LGH-DES-001", "Gulab Jamun", "Desserts", 260, 110, 4, "dessert"),
        Product("LGH-DES-002", "Kheer", "Desserts", 280, 120, 3, "dessert"),
        Product("LGH-DES-003", "Gajar ka Halwa", "Desserts", 340, 160, 2, "dessert"),
        Product("LGH-DES-004", "Firni", "Desserts", 260, 100, 2, "dessert"),
        Product("LGH-DES-005", "Kulfi", "Desserts", 180, 70, 3, "dessert"),
        Product("LGH-DES-006", "Lab-e-Shireen", "Desserts", 420, 190, 1, "dessert"),
        Product("LGH-DRI-001", "Sweet Lassi", "Drinks", 280, 110, 7, "drink"),
        Product("LGH-DRI-002", "Salted Lassi", "Drinks", 260, 100, 5, "drink"),
        Product("LGH-DRI-003", "Fresh Lime", "Drinks", 180, 50, 6, "drink"),
        Product("LGH-DRI-004", "Kashmiri Chai", "Drinks", 240, 70, 4, "drink"),
        Product("LGH-DEA-001", "Family Grill Platter", "Deals", 3990, 2100, 6, "deal"),
        Product("LGH-DEA-002", "Karahi Dinner for Two", "Deals", 2890, 1560, 5, "deal"),
        Product("LGH-DEA-003", "Biryani Combo", "Deals", 890, 430, 7, "deal"),
        Product("LGH-DEA-004", "Student Tikka Roll Deal", "Deals", 650, 300, 4, "deal"),
        Product("LGH-DEA-005", "Weekend Mixed Grill", "Deals", 4590, 2500, 3, "premium"),
        Product("LGH-BRK-001", "Halwa Puri Plate", "Breakfast", 380, 160, 3, "breakfast"),
        Product("LGH-BRK-002", "Aloo Paratha", "Breakfast", 220, 80, 4, "breakfast"),
        Product("LGH-BRK-003", "Omelette Paratha", "Breakfast", 280, 110, 3, "breakfast"),
        Product("LGH-BRK-004", "Chana Plate", "Breakfast", 260, 90, 2, "breakfast"),
        Product("LGH-BRK-005", "Nihari Single", "Breakfast", 540, 280, 2, "breakfast"),
        Product("LGH-SOU-001", "Chicken Yakhni", "Soups", 360, 140, 2, "soup"),
        Product("LGH-SOU-002", "Mutton Soup", "Soups", 420, 200, 1, "soup"),
        Product("LGH-SOU-003", "Daal Soup", "Soups", 240, 80, 1, "soup"),
        Product("LGH-SOU-004", "Tomato Soup", "Soups", 220, 70, 0, "soup"),
        Product("LGH-SID-001", "Raita", "Sides", 120, 40, 8, "side"),
        Product("LGH-SID-002", "Green Salad", "Sides", 180, 60, 4, "side"),
        Product("LGH-SID-003", "Mint Chutney", "Sides", 60, 15, 3, "side"),
        Product("LGH-SID-004", "Masala Fries", "Sides", 280, 110, 4, "side"),
    ],
    "urban-bites-lahore": [
        Product("UBL-BUR-001", "Crispy Chicken Burger", "Burgers", 690, 330, 8, "burger"),
        Product("UBL-BUR-002", "Grilled Chicken Burger", "Burgers", 740, 360, 6, "burger"),
        Product("UBL-BUR-003", "Mushroom Beef Burger", "Burgers", 980, 520, 4, "burger"),
        Product("UBL-BUR-004", "Spicy Zinger Stack", "Burgers", 760, 380, 5, "burger"),
        Product("UBL-BUR-005", "Mini Slider Pair", "Burgers", 540, 250, 3, "burger"),
        Product("UBL-BUR-006", "Fish Fillet Burger", "Burgers", 820, 410, 2, "burger"),
        Product("UBL-SHA-001", "Chicken Shawarma", "Shawarma", 420, 190, 9, "shawarma"),
        Product("UBL-SHA-002", "Beef Shawarma", "Shawarma", 480, 230, 6, "shawarma"),
        Product("UBL-SHA-003", "Shawarma Platter", "Shawarma", 890, 420, 5, "shawarma"),
        Product("UBL-SHA-004", "Cheese Shawarma", "Shawarma", 490, 230, 7, "shawarma"),
        Product("UBL-SHA-005", "Falafel Shawarma", "Shawarma", 390, 160, 2, "shawarma"),
        Product("UBL-SHA-006", "Shawarma Bowl", "Shawarma", 640, 280, 4, "shawarma"),
        Product("UBL-SHA-007", "Chicken Shawarma Large", "Shawarma", 560, 260, 6, "shawarma"),
        Product("UBL-PIZ-001", "Chicken Tikka Pizza Small", "Pizza", 990, 480, 6, "pizza"),
        Product("UBL-PIZ-002", "Chicken Tikka Pizza Medium", "Pizza", 1590, 760, 7, "pizza"),
        Product("UBL-PIZ-003", "Chicken Tikka Pizza Large", "Pizza", 2190, 1040, 5, "pizza"),
        Product("UBL-PIZ-004", "Fajita Pizza Medium", "Pizza", 1690, 820, 4, "pizza"),
        Product("UBL-PIZ-005", "Vegetable Pizza Medium", "Pizza", 1390, 620, 2, "pizza"),
        Product("UBL-PIZ-006", "Crown Crust Pizza Large", "Pizza", 2490, 1200, 3, "premium"),
        Product("UBL-PIZ-007", "Margherita Medium", "Pizza", 1290, 540, 3, "pizza"),
        Product("UBL-PIZ-008", "Peri Peri Chicken Pizza", "Pizza", 1790, 880, 4, "pizza"),
        Product("UBL-PIZ-009", "Cheese Sticks", "Pizza", 490, 200, 3, "side"),
        Product("UBL-CHI-001", "Dynamite Chicken", "Chinese", 780, 360, 5, "chinese"),
        Product("UBL-CHI-002", "Chicken Fried Rice", "Chinese", 590, 250, 6, "chinese"),
        Product("UBL-CHI-003", "Chow Mein", "Chinese", 640, 270, 4, "chinese"),
        Product("UBL-CHI-004", "Manchurian with Rice", "Chinese", 820, 380, 3, "chinese"),
        Product("UBL-CHI-005", "Honey Wings", "Chinese", 690, 320, 4, "chinese"),
        Product("UBL-CHI-006", "Thai Sweet Chilli Bites", "Chinese", 650, 300, 1, "chinese"),
        Product("UBL-CHI-007", "Chicken Dumplings", "Chinese", 680, 300, 2, "chinese"),
        Product("UBL-DES-001", "Brownie Slice", "Desserts", 420, 180, 4, "dessert"),
        Product("UBL-DES-002", "Ice Cream Cup", "Desserts", 280, 120, 5, "dessert"),
        Product("UBL-DES-003", "Molten Lava Cake", "Desserts", 490, 210, 3, "dessert"),
        Product("UBL-DES-004", "Cheesecake Slice", "Desserts", 520, 240, 2, "dessert"),
        Product("UBL-DES-005", "Kunafa Portion", "Desserts", 640, 300, 2, "dessert"),
        Product("UBL-DES-006", "Brownie Sundae", "Desserts", 540, 230, 2, "dessert"),
        Product("UBL-DEA-001", "Burger and Fries Meal", "Deals", 890, 420, 8, "deal"),
        Product("UBL-DEA-002", "Shawarma Couple Deal", "Deals", 980, 450, 6, "deal"),
        Product("UBL-DEA-003", "Pizza and Drink Deal", "Deals", 1890, 900, 5, "deal"),
        Product("UBL-DEA-004", "Student Zinger Meal", "Deals", 720, 340, 7, "deal"),
        Product("UBL-DEA-005", "Family Pizza Night", "Deals", 3990, 1900, 3, "premium"),
        Product("UBL-DEA-006", "Late Night Slider Box", "Deals", 1100, 520, 4, "deal"),
        Product("UBL-SID-001", "Cheese Fries", "Sides", 560, 260, 5, "side"),
        Product("UBL-SID-002", "Onion Rings", "Sides", 390, 160, 3, "side"),
        Product("UBL-SID-003", "Coleslaw", "Sides", 180, 60, 2, "side"),
        Product("UBL-SID-004", "Garlic Bread", "Sides", 320, 120, 4, "side"),
        Product("UBL-DRI-001", "Mint Lemonade", "Drinks", 320, 90, 6, "drink"),
        Product("UBL-DRI-002", "Soft Drink Can", "Drinks", 150, 90, 8, "drink"),
        Product("UBL-DRI-003", "Fresh Orange", "Drinks", 360, 140, 3, "drink"),
        Product("UBL-DRI-004", "Mineral Water 500ml", "Drinks", 90, 35, 5, "drink"),
        Product("UBL-DRI-005", "Chocolate Shake", "Drinks", 450, 180, 4, "drink"),
        Product("UBL-WRP-001", "Crispy Chicken Wrap", "Wraps", 540, 250, 5, "wrap"),
        Product("UBL-WRP-002", "Grilled Wrap", "Wraps", 520, 240, 4, "wrap"),
        Product("UBL-WRP-003", "Beef Wrap", "Wraps", 580, 280, 3, "wrap"),
        Product("UBL-PAS-001", "Chicken Alfredo", "Pasta", 890, 400, 3, "pasta"),
        Product("UBL-PAS-002", "Spicy Arrabbiata", "Pasta", 720, 300, 2, "pasta"),
        Product("UBL-PAS-003", "Baked Macaroni", "Pasta", 690, 310, 2, "pasta"),
        Product("UBL-PAS-004", "Tuna Pasta", "Pasta", 760, 340, 0, "pasta"),
    ],
    "daily-mart-lahore": [
        Product("DML-DAI-001", "Milk 1.5L", "Dairy", 480, 420, 8, "staple"),
        Product("DML-DAI-002", "Yogurt 1kg", "Dairy", 390, 330, 6, "staple"),
        Product("DML-DAI-003", "Eggs Dozen", "Dairy", 360, 310, 9, "staple"),
        Product("DML-DAI-004", "Cheese Slices", "Dairy", 520, 450, 4, "staple"),
        Product("DML-DAI-005", "Cooking Cream 200ml", "Dairy", 280, 230, 3, "staple"),
        Product("DML-DAI-006", "Laban 250ml", "Dairy", 160, 120, 2, "staple"),
        Product("DML-BAK-001", "Bread Small", "Bakery", 140, 110, 7, "staple"),
        Product("DML-BAK-002", "Naan 6 Pack", "Bakery", 240, 180, 5, "staple"),
        Product("DML-BAK-003", "Cake Rusk", "Bakery", 280, 210, 3, "snack"),
        Product("DML-BAK-004", "Plain Cake Slice", "Bakery", 180, 130, 2, "snack"),
        Product("DML-BEV-001", "Cola 1.5L", "Beverages", 250, 200, 7, "beverage"),
        Product("DML-BEV-002", "Lemon Malt 1.5L", "Beverages", 220, 175, 5, "beverage"),
        Product("DML-BEV-003", "Tea Bags", "Beverages", 190, 150, 6, "staple"),
        Product("DML-BEV-004", "Green Tea", "Beverages", 280, 220, 2, "beverage"),
        Product("DML-BEV-005", "Orange Juice 500ml", "Beverages", 240, 190, 3, "beverage"),
        Product("DML-BEV-006", "Energy Drink Can", "Beverages", 280, 230, 2, "beverage"),
        Product("DML-PAN-001", "Cooking Oil 1L", "Pantry", 680, 610, 8, "staple"),
        Product("DML-PAN-002", "Atta 5kg", "Pantry", 980, 860, 7, "staple"),
        Product("DML-PAN-003", "Daal Mash 1kg", "Pantry", 420, 360, 4, "staple"),
        Product("DML-PAN-004", "Daal Chana 1kg", "Pantry", 340, 290, 5, "staple"),
        Product("DML-PAN-005", "Salt 800g", "Pantry", 70, 45, 6, "staple"),
        Product("DML-PAN-006", "Red Chilli Powder 200g", "Pantry", 220, 160, 4, "staple"),
        Product("DML-PAN-007", "Tea Whitener 1kg", "Pantry", 760, 680, 3, "staple"),
        Product("DML-PAN-008", "Basmati Rice 5kg", "Pantry", 1950, 1720, 5, "staple"),
        Product("DML-SNK-001", "Potato Crisps", "Snacks", 80, 50, 6, "snack"),
        Product("DML-SNK-002", "Nimco Mix", "Snacks", 160, 110, 5, "snack"),
        Product("DML-SNK-003", "Biscuits Family Pack", "Snacks", 220, 170, 7, "snack"),
        Product("DML-SNK-004", "Chocolate Bar", "Snacks", 180, 140, 4, "snack"),
        Product("DML-SNK-005", "Salted Peanuts", "Snacks", 200, 150, 3, "snack"),
        Product("DML-SNK-006", "Samosa 4 Pack", "Snacks", 240, 170, 4, "snack"),
        Product("DML-SNK-007", "Popcorn", "Snacks", 150, 100, 2, "snack"),
        Product("DML-SNK-008", "Imli Candy", "Snacks", 60, 35, 1, "snack"),
        Product("DML-HHD-001", "Dishwash Bar", "Household", 90, 60, 5, "household"),
        Product("DML-HHD-002", "Washing Powder 1kg", "Household", 420, 340, 4, "household"),
        Product("DML-HHD-003", "Tissue Box", "Household", 280, 210, 3, "household"),
        Product("DML-HHD-004", "Floor Cleaner 1L", "Household", 360, 280, 2, "household"),
        Product("DML-HHD-005", "Trash Bags 10", "Household", 180, 120, 2, "household"),
        Product("DML-HHD-006", "Matches Pack", "Household", 40, 20, 3, "household"),
        Product("DML-FRZ-001", "Frozen Paratha 8", "Frozen", 380, 300, 4, "frozen"),
        Product("DML-FRZ-002", "Chicken Nuggets 500g", "Frozen", 690, 560, 3, "frozen"),
        Product("DML-FRZ-003", "Frozen Fries 1kg", "Frozen", 420, 330, 4, "frozen"),
        Product("DML-FRZ-004", "Peas 400g", "Frozen", 180, 130, 2, "frozen"),
        Product("DML-FRZ-005", "Ice Cream 1L", "Frozen", 750, 600, 2, "frozen"),
        Product("DML-SPC-001", "Garam Masala 100g", "Spices", 240, 170, 3, "spice"),
        Product("DML-SPC-002", "Coriander Powder 200g", "Spices", 180, 120, 4, "spice"),
        Product("DML-SPC-003", "Turmeric 100g", "Spices", 120, 80, 5, "spice"),
        Product("DML-SPC-004", "Cumin Whole 100g", "Spices", 260, 190, 3, "spice"),
        Product("DML-SPC-005", "Black Pepper 50g", "Spices", 320, 240, 2, "spice"),
        Product("DML-SPC-006", "Fenugreek Seeds 100g", "Spices", 90, 50, 0, "spice"),
    ],
}

INGREDIENTS = [
    Ingredient("INV-CHICKEN", "Chicken", "kg", "8", "780", 5),
    Ingredient("INV-FLOUR", "Flour", "kg", "10", "95", 0),
    Ingredient("INV-OIL", "Cooking Oil", "ltr", "6", "520", 0),
    Ingredient("ING-BEEF", "Beef", "kg", "4", "1450", 5),
    Ingredient("ING-MUTTON", "Mutton", "kg", "3", "2100", 5),
    Ingredient("ING-KEEMA", "Beef keema", "kg", "3", "1300", 4),
    Ingredient("ING-YOGURT", "Yogurt", "kg", "4", "320", 5),
    Ingredient("ING-ONION", "Onion", "kg", "8", "80", 7),
    Ingredient("ING-TOMATO", "Tomato", "kg", "6", "90", 5),
    Ingredient("ING-GINGER", "Ginger", "kg", "1", "400", 10),
    Ingredient("ING-GARLIC", "Garlic", "kg", "1", "500", 14),
    Ingredient("ING-CHILLI", "Red chilli powder", "kg", "1", "600", 0),
    Ingredient("ING-CORIANDER", "Coriander powder", "kg", "1", "450", 0),
    Ingredient("ING-CUMIN", "Cumin", "kg", "0.5", "900", 0),
    Ingredient("ING-GARAM", "Garam masala", "kg", "0.4", "1100", 0),
    Ingredient("ING-TIKKA", "Tikka masala", "kg", "0.5", "700", 0),
    Ingredient("ING-SALT", "Salt", "kg", "2", "40", 0),
    Ingredient("ING-TURMERIC", "Turmeric", "kg", "0.4", "400", 0),
    Ingredient("ING-RICE", "Basmati rice", "kg", "10", "280", 0),
    Ingredient("ING-NAAN", "Naan dough ball", "pcs", "40", "18", 2),
    Ingredient("ING-BUN", "Burger bun", "pcs", "40", "35", 2),
    Ingredient("ING-CHEESE", "Cheese slice", "pcs", "30", "40", 14),
    Ingredient("ING-LETTUCE", "Lettuce", "kg", "1", "200", 3),
    Ingredient("ING-POTATO", "Potato", "kg", "8", "70", 14),
    Ingredient("ING-CREAM", "Cooking cream", "ltr", "2", "480", 7),
    Ingredient("ING-SAUCE", "Burger sauce", "kg", "2", "350", 21),
    Ingredient("ING-BUTTER", "Butter", "kg", "1", "900", 21),
    Ingredient("ING-MILK", "Milk", "ltr", "6", "220", 4),
    Ingredient("ING-SUGAR", "Sugar", "kg", "5", "150", 0),
    Ingredient("ING-TEA", "Tea leaf", "kg", "1", "900", 0),
    Ingredient("ING-LEMON", "Lemon", "pcs", "30", "15", 7),
    Ingredient("ING-MINT", "Mint", "kg", "0.4", "250", 2),
    Ingredient("ING-CABBAGE", "Cabbage", "kg", "2", "60", 5),
    Ingredient("ING-CAPSICUM", "Capsicum", "kg", "2", "160", 5),
    Ingredient("ING-TORTILLA", "Shawarma tortilla", "pcs", "30", "30", 5),
    Ingredient("ING-SHAWARMA", "Shawarma spice", "kg", "0.3", "800", 0),
    Ingredient("ING-BASE", "Pizza base", "pcs", "20", "80", 3),
    Ingredient("ING-MOZ", "Mozzarella", "kg", "2", "1200", 10),
    Ingredient("ING-BREADCRUMB", "Breadcrumb", "kg", "1", "180", 0),
    Ingredient("ING-EGG", "Egg", "pcs", "30", "28", 14),
    Ingredient("ING-SOY", "Soy sauce", "ltr", "1", "300", 0),
    Ingredient("ING-COFFEE", "Coffee powder", "kg", "0.5", "1800", 0),
    Ingredient("ING-ICE", "Ice", "kg", "5", "20", 1),
    Ingredient("ING-SODACAN", "Soft drink can", "pcs", "48", "90", 180),
    Ingredient("ING-WATERBTL", "Water bottle 500ml", "pcs", "48", "35", 365),
    Ingredient("ING-WATER", "Drinking water", "ltr", "10", "10", 0),
    Ingredient("ING-FISH", "Fish fillet", "kg", "2", "1100", 3),
    Ingredient("ING-PRAWN", "Prawns", "kg", "1", "1800", 3),
    Ingredient("ING-PANEER", "Paneer", "kg", "1", "700", 5),
    Ingredient("ING-DAAL", "Mixed daal", "kg", "4", "220", 0),
    Ingredient("ING-CUCUMBER", "Cucumber", "kg", "2", "80", 4),
    Ingredient("ING-MUSHROOM", "Mushroom", "kg", "1", "450", 3),
    Ingredient("ING-SPAGHETTI", "Pasta", "kg", "2", "280", 0),
    Ingredient("ING-FALAFEL", "Falafel mix", "kg", "1", "300", 0),
    Ingredient("ING-HONEY", "Honey", "kg", "0.5", "900", 0),
    Ingredient("ING-KETCHUP", "Ketchup", "kg", "2", "250", 60),
    Ingredient("ING-CORN", "Sweet corn", "kg", "1", "180", 4),
    Ingredient("ING-PEAS", "Peas", "kg", "1", "160", 4),
    Ingredient("ING-GHEE", "Ghee", "kg", "2", "800", 0),
    Ingredient("ING-VERMICELLI", "Vermicelli", "kg", "1", "200", 0),
    Ingredient("ING-SUJI", "Semolina", "kg", "1", "140", 0),
    Ingredient("ING-CARROT", "Carrot", "kg", "2", "70", 7),
    Ingredient("ING-COAL", "Charcoal", "kg", "5", "90", 0),
    Ingredient("ING-CARDAMOM", "Cardamom", "kg", "0.1", "4000", 0),
    Ingredient("ING-VINEGAR", "Vinegar", "ltr", "1", "180", 0),
    Ingredient("ING-PISTACHIO", "Pistachio", "kg", "0.2", "2800", 0),
    Ingredient("ING-DATES", "Dates", "kg", "0.5", "400", 0),
    Ingredient("ING-CHANA", "Chana", "kg", "3", "200", 0),
    Ingredient("ING-ORANGE", "Orange", "pcs", "20", "40", 7),
    Ingredient("ING-PEACH", "Peach pulp", "kg", "1", "280", 14),
    Ingredient("ING-CHOCO", "Chocolate sauce", "kg", "0.5", "500", 60),
    Ingredient("ING-RAISIN", "Raisins", "kg", "0.5", "600", 0),
    Ingredient("ING-WHITEPEPPER", "White pepper", "kg", "0.2", "1400", 0),
]


def _line(*pairs):
    return list(pairs)


RECIPES = {
    "lahore-grill-house": {
        "BBQ-001": _line(("INV-CHICKEN", "0.220"), ("ING-YOGURT", "0.040"), ("ING-TIKKA", "0.008"), ("INV-OIL", "0.015"), ("ING-ONION", "0.020")),
        "BBQ-002": _line(("ING-KEEMA", "0.180"), ("ING-ONION", "0.030"), ("ING-GARAM", "0.004"), ("INV-OIL", "0.010")),
        "BBQ-003": _line(("INV-CHICKEN", "0.200"), ("ING-CREAM", "0.030"), ("ING-BUTTER", "0.015")),
        "BBQ-004": _line(("INV-CHICKEN", "0.450"), ("ING-TOMATO", "0.200"), ("ING-GINGER", "0.015"), ("ING-GARLIC", "0.015"), ("ING-CHILLI", "0.008"), ("INV-OIL", "0.040")),
        "LGH-KAR-001": _line(("INV-CHICKEN", "0.850"), ("ING-TOMATO", "0.350"), ("ING-GINGER", "0.025"), ("ING-GARLIC", "0.025"), ("ING-CHILLI", "0.012"), ("INV-OIL", "0.070")),
        "LGH-KAR-005": _line(("INV-CHICKEN", "0.280"), ("ING-TOMATO", "0.150"), ("INV-OIL", "0.030"), ("ING-CHILLI", "0.006")),
        "LGH-HAN-001": _line(("INV-CHICKEN", "0.400"), ("ING-CREAM", "0.050"), ("ING-YOGURT", "0.040"), ("ING-TOMATO", "0.100"), ("INV-OIL", "0.030")),
        "LGH-HAN-002": _line(("INV-CHICKEN", "0.750"), ("ING-CREAM", "0.080"), ("ING-YOGURT", "0.060"), ("ING-TOMATO", "0.160"), ("INV-OIL", "0.050")),
        "LGH-BBQ-001": _line(("ING-BEEF", "0.220"), ("ING-YOGURT", "0.030"), ("ING-TIKKA", "0.008"), ("INV-OIL", "0.015")),
        "LGH-BBQ-002": _line(("INV-CHICKEN", "0.180"), ("ING-CREAM", "0.025"), ("ING-CHEESE", "1")),
        "LGH-BBQ-003": _line(("ING-KEEMA", "0.160"), ("ING-ONION", "0.020"), ("INV-OIL", "0.008")),
        "LGH-BBQ-006": _line(("INV-CHICKEN", "0.200"), ("ING-YOGURT", "0.020"), ("INV-OIL", "0.010")),
        "LGH-BBQ-007": _line(("ING-KEEMA", "0.120"), ("ING-NAAN", "1"), ("ING-ONION", "0.020")),
        "LGH-BBQ-008": _line(("INV-CHICKEN", "0.140"), ("ING-NAAN", "1"), ("ING-CREAM", "0.020")),
        "RIC-001": _line(("INV-CHICKEN", "0.180"), ("ING-RICE", "0.200"), ("ING-YOGURT", "0.040"), ("ING-ONION", "0.040"), ("INV-OIL", "0.020")),
        "LGH-RIC-001": _line(("ING-MUTTON", "0.180"), ("ING-RICE", "0.200"), ("ING-YOGURT", "0.040"), ("INV-OIL", "0.025")),
        "LGH-RIC-002": _line(("ING-BEEF", "0.180"), ("ING-RICE", "0.200"), ("INV-OIL", "0.020")),
        "LGH-BRD-001": _line(("ING-NAAN", "1")),
        "LGH-BRD-002": _line(("ING-NAAN", "1"), ("ING-GARLIC", "0.005"), ("ING-BUTTER", "0.008")),
        "LGH-BRD-003": _line(("INV-FLOUR", "0.040")),
        "LGH-DRI-001": _line(("ING-YOGURT", "0.150"), ("ING-MILK", "0.100"), ("ING-SUGAR", "0.020")),
        "LGH-DRI-002": _line(("ING-YOGURT", "0.150"), ("ING-MILK", "0.100"), ("ING-SALT", "0.004")),
        "LGH-DRI-003": _line(("ING-LEMON", "2"), ("ING-SUGAR", "0.015"), ("ING-WATER", "0.250")),
        "LGH-DEA-001": _line(("INV-CHICKEN", "0.350"), ("ING-KEEMA", "0.200"), ("ING-NAAN", "4"), ("ING-YOGURT", "0.080")),
        "LGH-DEA-002": _line(("INV-CHICKEN", "0.500"), ("ING-TOMATO", "0.220"), ("ING-NAAN", "2"), ("INV-OIL", "0.045")),
        "LGH-DEA-003": _line(("INV-CHICKEN", "0.180"), ("ING-RICE", "0.200"), ("ING-SODACAN", "1")),
        "LGH-SID-001": _line(("ING-YOGURT", "0.100"), ("ING-MINT", "0.010")),
    },
    "urban-bites-lahore": {
        "BUR-001": _line(("ING-BUN", "1"), ("ING-BEEF", "0.120"), ("ING-SAUCE", "0.020"), ("ING-LETTUCE", "0.015")),
        "BUR-002": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.140"), ("ING-BREADCRUMB", "0.020"), ("INV-OIL", "0.015"), ("ING-SAUCE", "0.015")),
        "BUR-003": _line(("ING-BUN", "1"), ("ING-BEEF", "0.180"), ("ING-CHEESE", "2"), ("ING-SAUCE", "0.020")),
        "UBL-BUR-001": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.130"), ("ING-BREADCRUMB", "0.020"), ("INV-OIL", "0.015")),
        "UBL-BUR-002": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.140"), ("ING-LETTUCE", "0.015"), ("ING-SAUCE", "0.015")),
        "UBL-BUR-004": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.140"), ("ING-BREADCRUMB", "0.020"), ("INV-OIL", "0.015"), ("ING-CHILLI", "0.003")),
        "UBL-SHA-001": _line(("ING-TORTILLA", "1"), ("INV-CHICKEN", "0.120"), ("ING-CABBAGE", "0.030"), ("ING-SAUCE", "0.020"), ("ING-SHAWARMA", "0.004")),
        "UBL-SHA-002": _line(("ING-TORTILLA", "1"), ("ING-BEEF", "0.120"), ("ING-CABBAGE", "0.030"), ("ING-SAUCE", "0.020")),
        "UBL-SHA-004": _line(("ING-TORTILLA", "1"), ("INV-CHICKEN", "0.120"), ("ING-CHEESE", "1"), ("ING-SAUCE", "0.020")),
        "UBL-SHA-007": _line(("ING-TORTILLA", "1"), ("INV-CHICKEN", "0.180"), ("ING-CABBAGE", "0.040"), ("ING-SAUCE", "0.025")),
        "UBL-PIZ-001": _line(("ING-BASE", "1"), ("ING-MOZ", "0.080"), ("INV-CHICKEN", "0.060"), ("ING-CAPSICUM", "0.020")),
        "UBL-PIZ-002": _line(("ING-BASE", "1"), ("ING-MOZ", "0.120"), ("INV-CHICKEN", "0.090"), ("ING-CAPSICUM", "0.030"), ("ING-ONION", "0.020")),
        "UBL-PIZ-003": _line(("ING-BASE", "1"), ("ING-MOZ", "0.180"), ("INV-CHICKEN", "0.130"), ("ING-CAPSICUM", "0.040")),
        "SID-001": _line(("ING-POTATO", "0.180"), ("INV-OIL", "0.020"), ("ING-CHEESE", "1")),
        "UBL-SID-001": _line(("ING-POTATO", "0.180"), ("INV-OIL", "0.020"), ("ING-CHEESE", "2")),
        "UBL-DEA-001": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.130"), ("ING-POTATO", "0.150"), ("INV-OIL", "0.020"), ("ING-SODACAN", "1")),
        "UBL-DEA-002": _line(("ING-TORTILLA", "2"), ("INV-CHICKEN", "0.220"), ("ING-CABBAGE", "0.050"), ("ING-SAUCE", "0.030")),
        "UBL-DEA-004": _line(("ING-BUN", "1"), ("INV-CHICKEN", "0.120"), ("ING-BREADCRUMB", "0.015"), ("INV-OIL", "0.012"), ("ING-SODACAN", "1")),
        "UBL-DRI-002": _line(("ING-SODACAN", "1")),
        "UBL-DRI-004": _line(("ING-WATERBTL", "1")),
        "UBL-CHI-002": _line(("ING-RICE", "0.180"), ("INV-CHICKEN", "0.080"), ("ING-EGG", "1"), ("INV-OIL", "0.015"), ("ING-SOY", "0.010")),
        "UBL-WRP-001": _line(("ING-TORTILLA", "1"), ("INV-CHICKEN", "0.110"), ("ING-LETTUCE", "0.015")),
        "DRI-001": _line(("ING-MILK", "0.200"), ("ING-COFFEE", "0.012"), ("ING-SUGAR", "0.015"), ("ING-ICE", "0.050")),
    },
}

EXTRA_SUPPLIERS = {
    "lahore-grill-house": [
        ("Baghbanwala Poultry Farm", 1),
        ("Canal Road Produce Market", 1),
    ],
    "urban-bites-lahore": [
        ("Baghbanwala Poultry Farm", 1),
        ("Gulberg Bakery Supplies", 2),
    ],
    "daily-mart-lahore": [
        ("Shahdara Grocery Depot", 3),
        ("Ichhra Cold Storage", 2),
    ],
}


def meta(slug, sku):
    if (slug, sku) in EXISTING_META:
        popularity, tag = EXISTING_META[(slug, sku)]
        return popularity, tag
    for product in NEW_PRODUCTS.get(slug, []):
        if product.sku == sku:
            return product.popularity, product.tag
    return 4, "general"


def validate():
    ingredient_skus = set()
    for item in INGREDIENTS:
        if item.sku in ingredient_skus:
            raise ValueError("Duplicate ingredient " + item.sku)
        ingredient_skus.add(item.sku)
    known = set(EXISTING_META)
    for slug, products in NEW_PRODUCTS.items():
        seen = set()
        for product in products:
            if product.sku in seen:
                raise ValueError("Duplicate sku " + product.sku)
            seen.add(product.sku)
            known.add((slug, product.sku))
            if product.price <= product.cost:
                raise ValueError("Demo price should exceed demo cost for " + product.sku)
            if product.popularity < 0:
                raise ValueError("Bad popularity " + product.sku)
    for slug, recipes in RECIPES.items():
        for product_sku, lines in recipes.items():
            if (slug, product_sku) not in known:
                raise ValueError(f"Recipe product missing: {slug} {product_sku}")
            used = set()
            for ingredient_sku, _qty in lines:
                if ingredient_sku not in ingredient_skus:
                    raise ValueError("Unknown ingredient " + ingredient_sku)
                if ingredient_sku in used:
                    raise ValueError("Repeated ingredient on " + product_sku)
                used.add(ingredient_sku)
    if len(INGREDIENTS) < 60:
        raise ValueError("Ingredient master is thinner than the coursework target")


validate()
