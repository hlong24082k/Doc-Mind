import pytest

from app.core.retrieval.fusion import ReciprocalRankFusion

from .conftest import scored


def test_rrf_formula():
    dense = [scored(1, "dense"), scored(2, "dense")]
    sparse = [scored(2, "sparse"), scored(1, "sparse")]
    out = ReciprocalRankFusion(k=60).fuse({"dense": dense, "sparse": sparse}, k=10)
    expected = 1 / 61 + 1 / 62
    assert out[0].scores["rrf"] == pytest.approx(expected)
    assert out[1].scores["rrf"] == pytest.approx(expected)
    assert out[0].ranks == {"dense": 1, "sparse": 2}


def test_single_branch_chunk_is_kept():
    out = ReciprocalRankFusion(k=60).fuse(
        {"dense": [scored(1, "dense")], "sparse": [scored(2, "sparse")]},
        k=10,
    )
    assert {o.chunk.chunk_id for o in out} == {1, 2}
    only_dense = next(o for o in out if o.chunk.chunk_id == 1)
    assert only_dense.scores["rrf"] == pytest.approx(1 / 61)
    assert "sparse" not in only_dense.scores


def test_weights_change_order():
    ranked = {
        "dense": [scored(1, "dense")],
        "sparse": [scored(2, "sparse")],
    }
    out = ReciprocalRankFusion(k=60, weights={"dense": 1.0, "sparse": 3.0}).fuse(
        ranked, k=10
    )
    assert [o.chunk.chunk_id for o in out] == [2, 1]


def test_tie_broken_by_chunk_id_and_cut():
    ranked = {
        "dense": [scored(5, "dense")],
        "sparse": [scored(3, "sparse")],
    }
    out = ReciprocalRankFusion(k=60).fuse(ranked, k=10)
    assert [o.chunk.chunk_id for o in out] == [3, 5]
    assert len(ReciprocalRankFusion(k=60).fuse(ranked, k=1)) == 1
