from app.cases.mapping_evaluator import (
    MappingEvidence,
    MappingRuleSet,
    ModuleSnapshot,
    RuleSnapshot,
    evaluate_mapping,
    normalize_path,
    preflight_rule,
)


def rule_set(*rules: RuleSnapshot) -> MappingRuleSet:
    return MappingRuleSet(
        modules=(
            ModuleSnapshot(id="payment", name="Payment", slug="payment", code="PAY"),
            ModuleSnapshot(id="checkout", name="Checkout", slug="checkout", code="CHK"),
        ),
        rules=rules,
    )


def test_code_change_path_globs_exclusions_and_case_defaults() -> None:
    rules = rule_set(
        RuleSnapshot(
            id="r1",
            module_id="payment",
            rule_type="directory",
            pattern="src/payment/**\n!src/payment/generated/**",
            confidence=90,
        )
    )

    matched = evaluate_mapping(MappingEvidence(kind="code_change", path=normalize_path(r"src\payment\checkout.py")), rules)
    excluded = evaluate_mapping(MappingEvidence(kind="code_change", path="src/payment/generated/client.py"), rules)
    wrong_case = evaluate_mapping(MappingEvidence(kind="code_change", path="SRC/PAYMENT/checkout.py"), rules)

    assert matched.best_match is not None
    assert matched.best_match.rule.id == "r1"
    assert excluded.best_match is None
    assert wrong_case.best_match is None


def test_relationship_status_weighting_and_specificity_tie_breaks() -> None:
    rules = rule_set(
        RuleSnapshot(id="broad", module_id="payment", rule_type="directory", pattern="src/payment/**", confidence=90),
        RuleSnapshot(id="exact", module_id="checkout", rule_type="file", pattern="src/payment/checkout.py", confidence=90),
        RuleSnapshot(id="stale", module_id="payment", rule_type="keyword", pattern="refund", confidence=100, status="stale"),
        RuleSnapshot(id="evidence", module_id="checkout", rule_type="keyword", pattern="refund", confidence=100, relationship="evidence"),
    )

    result = evaluate_mapping(
        MappingEvidence(kind="code_change", path="src/payment/checkout.py", content="refund"),
        rules,
    )

    assert result.best_match is not None
    assert result.best_match.rule.id == "exact"
    assert result.best_match.score == 90
    assert any(match.rule.id == "stale" and match.score == 50 for match in result.matches)
    assert any(match.rule.id == "evidence" and match.score == 0 for match in result.matches)
    assert any(issue.code == "stale_rule_match" for issue in result.warnings)
    assert any(issue.code == "primary_conflict" for issue in result.primary_conflicts)


def test_case_text_uses_text_rules_but_not_file_or_directory_rules() -> None:
    rules = rule_set(
        RuleSnapshot(id="directory", module_id="payment", rule_type="directory", pattern="refund"),
        RuleSnapshot(id="file", module_id="payment", rule_type="file", pattern="refund"),
        RuleSnapshot(id="keyword", module_id="checkout", rule_type="keyword", pattern="refund"),
    )

    result = evaluate_mapping(MappingEvidence(kind="case_text", text="Refund after payment succeeds"), rules)

    assert result.best_match is not None
    assert result.best_match.rule.id == "keyword"
    assert {match.rule.id for match in result.matches} == {"keyword"}


def test_preflight_reports_blockers_and_inventory_warnings() -> None:
    rules = rule_set(
        RuleSnapshot(id="existing", module_id="payment", rule_type="directory", pattern="src/payment/**"),
        RuleSnapshot(id="other", module_id="checkout", rule_type="directory", pattern="src/**"),
    )

    duplicate = preflight_rule(
        RuleSnapshot(module_id="payment", rule_type="directory", pattern="src/payment/**"),
        rules,
        sample_inventory=["src/payment/checkout.py"],
    )
    risky = preflight_rule(
        RuleSnapshot(module_id="payment", rule_type="directory", pattern="src/**", relationship="primary", status="stale"),
        rules,
        sample_inventory=[
            "src/payment/checkout.py",
            "src/payment/generated/client.py",
            "src/payment/tests/test_checkout.py",
            "src/vendor/payment/client.py",
            "src/checkout/cart.py",
        ],
    )

    assert duplicate.passed is False
    assert any(issue.code == "duplicate_rule" for issue in duplicate.issues)
    assert risky.passed is True
    assert {issue.code for issue in risky.issues} >= {
        "stale_reason_missing",
        "unscoped_path_rule",
        "primary_overlap",
        "generated_path_match",
        "test_file_primary_match",
        "vendor_path_match",
        "primary_sample_conflict",
    }
