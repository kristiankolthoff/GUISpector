from gui_spector.processor.requirements_processor import RequirementsProcessor
from gui_spector.models.requirements import RequirementsPriority


def main():
    sample_requirements = (
        "User Registration & Login – Allow customers to sign up and log in securely via email, phone, or social accounts.\n\n"
        "Product Catalog – Display products with images, descriptions, prices, and availability.\n\n"
        "Search & Filters – Enable keyword search and filters (category, price, brand, rating).\n\n"
        "Shopping Cart – Let users add, edit, and remove products before checkout.\n\n"
        "Wishlist – Allow saving favorite items for later purchase.\n\n"
        "Secure Checkout – Provide multiple payment options (credit card, UPI, wallet, COD).\n\n"
        "Order Tracking – Show live order status and delivery updates.\n\n"
        "Ratings & Reviews – Let customers rate products and share feedback.\n\n"
        "Push Notifications – Send alerts about offers, order updates, and promotions.\n\n"
        "User Profile & Order History – Store delivery addresses, payment preferences, and past purchases."
    )

    processor = RequirementsProcessor()
    requirements = processor.process_text(
        input_text=sample_requirements,
        allow_guess=True,
        default_priority=RequirementsPriority.MEDIUM,
        source="spec_list",
    )

    print("=== PARSED REQUIREMENTS ===")
    for r in requirements:
        print("--------------------------------")
        print(r)
        print("--------------------------------")


if __name__ == "__main__":
    main()


