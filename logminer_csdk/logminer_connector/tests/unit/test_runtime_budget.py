from runtime_budget import RuntimeBudget


def test_runtime_budget_is_finite():
    budget = RuntimeBudget(started_at=0.0, maximum_seconds=30, safety_seconds=15)
    assert budget.nearly_exhausted()
