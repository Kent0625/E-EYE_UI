import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from app.clinical import round_diopter, compute_se, classify_condition, evaluate_referral

class TestClinicalLogic(unittest.TestCase):
    def test_single_rounding_001D(self):
        # Mandatory rounding test cases from Phase 1.1 feedback
        self.assertEqual(round_diopter("-0.504"), -0.50)
        self.assertEqual(round_diopter("-0.505"), -0.51)
        self.assertEqual(round_diopter("0.504"), 0.50)
        self.assertEqual(round_diopter("0.505"), 0.51)
        self.assertEqual(round_diopter("-0.50"), -0.50)
        self.assertEqual(round_diopter("0.50"), 0.50)

    def test_referral_decisions_from_rounded_se(self):
        # Case 1: -0.504 rounds to -0.50 -> Emmetropic (NO REFERRAL)
        se_neg_504 = round_diopter("-0.504")
        is_ref, eyes = evaluate_referral(se_neg_504)
        self.assertFalse(is_ref, f"Expected no referral for {se_neg_504}")
        self.assertEqual(eyes, [])

        # Case 2: -0.505 rounds to -0.51 -> Outside range (REFERRAL RECOMMENDED)
        se_neg_505 = round_diopter("-0.505")
        is_ref, eyes = evaluate_referral(se_neg_505)
        self.assertTrue(is_ref, f"Expected referral for {se_neg_505}")
        self.assertEqual(eyes, ["OD"])

        # Case 3: +0.504 rounds to +0.50 -> Emmetropic (NO REFERRAL)
        se_pos_504 = round_diopter("0.504")
        is_ref, eyes = evaluate_referral(se_pos_504)
        self.assertFalse(is_ref, f"Expected no referral for {se_pos_504}")
        self.assertEqual(eyes, [])

        # Case 4: +0.505 rounds to +0.51 -> Outside range (REFERRAL RECOMMENDED)
        se_pos_505 = round_diopter("0.505")
        is_ref, eyes = evaluate_referral(se_pos_505)
        self.assertTrue(is_ref, f"Expected referral for {se_pos_505}")
        self.assertEqual(eyes, ["OD"])

        # Case 5: Exactly -0.50 -> Emmetropic boundary (NO REFERRAL)
        se_exact_neg = round_diopter("-0.50")
        is_ref, eyes = evaluate_referral(se_exact_neg)
        self.assertFalse(is_ref, f"Expected no referral for {se_exact_neg}")
        self.assertEqual(eyes, [])

        # Case 6: Exactly +0.50 -> Emmetropic boundary (NO REFERRAL)
        se_exact_pos = round_diopter("0.50")
        is_ref, eyes = evaluate_referral(se_exact_pos)
        self.assertFalse(is_ref, f"Expected no referral for {se_exact_pos}")
        self.assertEqual(eyes, [])

    def test_spherical_equivalent_formula(self):
        # SE = sphere + cylinder / 2 rounded to 0.01 D
        self.assertEqual(compute_se(-1.50, -0.50), -1.75)
        self.assertEqual(compute_se(-1.25, -0.24), -1.37)
        self.assertEqual(compute_se(0.50, -0.50), 0.25)
        self.assertEqual(compute_se(0.00, -1.01), -0.51)

    def test_decimal_summation_from_strings(self):
        # Explicit test confirming Decimal summation from string representations before rounding
        # Case A: sphere = "-0.25", cylinder = "-0.51"
        # Decimal calculation: -0.25 + (-0.51 / 2) = -0.25 - 0.255 = -0.505
        # Round half up to 0.01 D -> -0.51 D
        self.assertEqual(compute_se("-0.25", "-0.51"), -0.51)

        # Case B: sphere = "-0.25", cylinder = "-0.508"
        # -0.25 + (-0.508 / 2) = -0.25 - 0.254 = -0.504 -> rounds to -0.50 D
        self.assertEqual(compute_se("-0.25", "-0.508"), -0.50)

        # Case C: sphere = "+0.25", cylinder = "+0.51"
        # +0.25 + (+0.51 / 2) = +0.25 + 0.255 = +0.505 -> rounds to +0.51 D
        self.assertEqual(compute_se("+0.25", "+0.51"), 0.51)

    def test_condition_labels(self):
        self.assertEqual(classify_condition(0.00), "emmetropia")
        self.assertEqual(classify_condition(-0.50), "emmetropia")
        self.assertEqual(classify_condition(0.50), "emmetropia")
        self.assertEqual(classify_condition(-1.75), "myopia_mild")
        self.assertEqual(classify_condition(-3.00), "myopia_mild")
        self.assertEqual(classify_condition(-3.50), "myopia_moderate")
        self.assertEqual(classify_condition(-6.00), "myopia_moderate")
        self.assertEqual(classify_condition(-6.50), "myopia_high")
        self.assertEqual(classify_condition(1.25), "hyperopia")

if __name__ == "__main__":
    unittest.main()
