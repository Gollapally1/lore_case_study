"""
Tests for contract-as-API enforcement: schema validation and quality gates.

These are the proof that contracts are load-bearing, not decorative —
a contract violation must produce a clear, actionable failure.
"""


def test_schema_enforcement_missing_column(spark):
    from run_pipeline import enforce_schema

    df = spark.createDataFrame([("e1", "user_001")], ["event_id", "user_id"])
    contract = {
        "schema": [
            {"name": "event_id", "type": "string", "nullable": False},
            {"name": "user_id", "type": "string", "nullable": False},
            {"name": "partner_id", "type": "string", "nullable": False},  # missing!
        ]
    }
    violations = enforce_schema(df, contract)
    assert any("partner_id" in v and "missing" in v for v in violations)


def test_schema_enforcement_passes_when_optional_missing(spark):
    from run_pipeline import enforce_schema

    df = spark.createDataFrame([("e1",)], ["event_id"])
    contract = {
        "schema": [
            {"name": "event_id", "type": "string", "nullable": False},
            {"name": "session_id", "type": "string", "nullable": True},  # ok to be absent
        ]
    }
    assert enforce_schema(df, contract) == []


def test_schema_enforcement_allowed_values(spark):
    from run_pipeline import enforce_schema

    df = spark.createDataFrame(
        [("e1", "ios"), ("e2", "android"), ("e3", "blackberry")],
        ["event_id", "device_platform"],
    )
    contract = {
        "schema": [
            {"name": "event_id", "type": "string", "nullable": False},
            {"name": "device_platform", "type": "string", "nullable": False,
             "allowed_values": ["ios", "android", "web"]},
        ]
    }
    violations = enforce_schema(df, contract)
    assert any("device_platform" in v and "blackberry" not in v and "allowed_values" in v
               for v in violations), f"expected device_platform violation, got: {violations}"


def test_quality_uniqueness_catches_duplicates(spark):
    from run_pipeline import run_quality_checks

    df = spark.createDataFrame(
        [("e1",), ("e1",), ("e2",)],  # duplicate event_id
        ["event_id"],
    )
    contract = {
        "quality": {
            "uniqueness": [{"columns": ["event_id"], "threshold": 1.0}],
        }
    }
    violations = run_quality_checks(df, contract)
    assert any("uniqueness" in v for v in violations)


def test_quality_completeness_catches_nulls(spark):
    from run_pipeline import run_quality_checks

    df = spark.createDataFrame(
        [("e1", "user_001"), ("e2", None), ("e3", "user_003")],
        ["event_id", "user_id"],
    )
    contract = {
        "quality": {
            "completeness": [
                {"column": "user_id", "check": "not_null", "threshold": 1.0},
            ],
        }
    }
    violations = run_quality_checks(df, contract)
    assert any("user_id" in v for v in violations)


def test_quality_completeness_passes_within_threshold(spark):
    from run_pipeline import run_quality_checks

    # 99% complete; threshold 0.99 should pass.
    rows = [("e%d" % i, "u") for i in range(99)] + [("e99", None)]
    df = spark.createDataFrame(rows, ["event_id", "user_id"])
    contract = {
        "quality": {
            "completeness": [
                {"column": "user_id", "check": "not_null", "threshold": 0.99},
            ],
        }
    }
    assert run_quality_checks(df, contract) == []


def test_contract_loads_real_yaml():
    """Smoke-test: every shipped contract parses without surprises."""
    from pathlib import Path
    from run_pipeline import load_contract

    configs = Path(__file__).parent.parent / "configs"
    for path in sorted(configs.glob("*.yaml")):
        contract = load_contract(str(path))
        assert "contract" in contract
        assert "schema" in contract
        assert contract["contract"].get("name"), f"{path}: missing contract.name"
        assert contract["contract"].get("version"), f"{path}: missing contract.version"
