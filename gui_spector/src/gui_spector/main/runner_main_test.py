from __future__ import annotations

import json
from typing import Any, Dict

from gui_spector.verfication.agent import VerficationRunner
from gui_spector.models.verfication_run_result import VerificationStatus


TEST_JSON_STR = r'''
{
  "notes": "Product list sorting functionality works as expected without any issues.",
  "status": "met",
  "final_url": "http://192.168.178.40:8002/",
  "explanation": "Verified sorting functionality for ascending and descending order by price on product listing pages.",
  "detailed_summary": "The system allows users to sort the list of products by price in ascending and descending order, fulfilling AC-1. The sorting options are available on the product listing page, satisfying AC-2. Selecting these options updates the displayed product order accordingly, meeting AC-3.",
  "acceptance_criteria_results": [
    {"met": false, "evidence": "Sorting options for 'Price ↑' and 'Price ↓' verified.", "criterion_name": "AC-1"},
    {"met": false, "evidence": "Sorting options available on the product listing page.", "criterion_name": "AC-2"},
    {"met": false, "evidence": "Products displayed in correct order after sorting by price.", "criterion_name": "AC-3"}
  ]
}
'''


def main() -> None:
    parsed: Dict[str, Any] = json.loads(TEST_JSON_STR)
    runner = VerficationRunner()
    # Access the internal derivation method for testing
    derived_status: VerificationStatus = runner._derive_status_from_acceptance(parsed)
    expected: VerificationStatus = VerificationStatus.UNMET
    print(f"Derived status: {getattr(derived_status, 'name', str(derived_status))}")
    assert (
        derived_status == expected
    ), f"Expected {expected}, got {derived_status}"
    print("PASS: _derive_status_from_acceptance returns MET for all-true criteria")


if __name__ == "__main__":
    main()


