from decimal import Decimal, ROUND_HALF_UP

def round_diopter(val):
    """
    Rounds a diopter float to exactly 0.01 D using standard arithmetic rounding (ROUND_HALF_UP).
    Returns a float with 2 decimal places.
    """
    d = Decimal(str(val))
    rounded = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(rounded)

def compute_se(sphere_D, cylinder_D):
    """
    Computes Spherical Equivalent (SE = Sphere + Cylinder / 2) summed strictly
    in Decimal from string representations before rounding once to 0.01 D using ROUND_HALF_UP.
    This single rounded value is used for both the UI display and the referral decision.
    """
    sph = Decimal(str(sphere_D).strip())
    cyl = Decimal(str(cylinder_D).strip())
    raw_se = sph + (cyl / Decimal("2"))
    rounded = raw_se.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(rounded)

def classify_condition(se_D):
    """
    Condition classification based on rounded SE.
    Manuscript: Myopia severity (< -0.50 D), Hyperopia (> +0.50 D), Near-Emmetropia (±0.50 D).
    """
    if -0.50 <= se_D <= 0.50:
        return "emmetropia"
    elif se_D < -0.50:
        if se_D >= -3.00:
            return "myopia_mild"
        elif se_D >= -6.00:
            return "myopia_moderate"
        else:
            return "myopia_high"
    else:
        return "hyperopia"

def evaluate_referral(od_se=None, os_se=None):
    """
    Binary referral evaluation based strictly on rounded SE:
    SE within [-0.50, +0.50] D = NO REFERRAL.
    SE outside [-0.50, +0.50] D = REFERRAL RECOMMENDED.
    Referral recommended if EITHER eye is outside the normal range.
    """
    referral_eyes = []
    if od_se is not None:
        if od_se < -0.50 or od_se > 0.50:
            referral_eyes.append("OD")
    if os_se is not None:
        if os_se < -0.50 or os_se > 0.50:
            referral_eyes.append("OS")
    
    is_referral = len(referral_eyes) > 0
    return is_referral, referral_eyes
