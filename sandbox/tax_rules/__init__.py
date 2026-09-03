from sandbox.tax_rules.y2026 import RULES_2026, TaxRuleSet


TAX_RULES = {RULES_2026.year: RULES_2026}


def get_tax_rules(year=2026) -> TaxRuleSet:
    return TAX_RULES[year]
