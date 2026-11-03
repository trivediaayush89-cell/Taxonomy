"""Tests for category alias DAG validation and cycle detection."""

import pytest
from taxonomy.dag import CategoryDAG, CyclicDependencyError


def test_valid_dag_topological_sort():
    dag = CategoryDAG()
    dag.add_alias("qa", "verification.qa")
    dag.add_alias("tests", "verification.qa")
    dag.add_alias("audit", "security.audit")

    order = dag.validate_acyclic()
    assert len(order) == 5
    assert dag.resolve_alias_chain("qa") == "verification.qa"


def test_circular_dependency_detected():
    dag = CategoryDAG()
    dag.add_alias("cat-a", "cat-b")
    dag.add_alias("cat-b", "cat-c")
    dag.add_alias("cat-c", "cat-a")  # Cycle!

    with pytest.raises(CyclicDependencyError) as exc:
        dag.validate_acyclic()
    assert "Circular category loop detected" in str(exc.value)


def test_self_loop_detected():
    dag = CategoryDAG()
    dag.add_alias("loop", "loop")

    with pytest.raises(CyclicDependencyError):
        dag.validate_acyclic()
