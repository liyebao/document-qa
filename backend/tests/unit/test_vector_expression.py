from app.services.retrieval.vector import _distance_and_dimension_filter


def test_supported_dimension_uses_cast_and_dimension_filter() -> None:
    distance, dimension_filter = _distance_and_dimension_filter([0.1] * 1024)
    sql = str(distance.compile(compile_kwargs={"literal_binds": False}))
    assert "VECTOR(1024)" in sql.upper()
    assert dimension_filter is not None


def test_large_dimension_uses_halfvec_expression() -> None:
    distance, dimension_filter = _distance_and_dimension_filter([0.1] * 3072)
    sql = str(distance.compile(compile_kwargs={"literal_binds": False}))
    assert "HALFVEC(3072)" in sql.upper()
    assert dimension_filter is not None


def test_unindexed_dimension_falls_back_to_exact_search() -> None:
    distance, dimension_filter = _distance_and_dimension_filter([0.1] * 4)
    assert dimension_filter is None
    assert "CAST" not in str(distance.compile()).upper()
