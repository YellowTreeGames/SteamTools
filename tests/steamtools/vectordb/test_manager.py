"""Tests for steamtools.vectordb.manager."""

import numpy as np
import pytest

from steamtools.vectordb.manager import VectorManager


@pytest.fixture
def vm(tmp_path):
    return VectorManager(path=tmp_path / "chroma")


def test_get_or_create_collection(vm):
    col = vm.get_or_create_collection("test_col")
    assert col is not None


def test_upsert_and_count(vm):
    vm.upsert(
        "test_col",
        ids=["a", "b"],
        documents=["doc one", "doc two"],
        metadatas=[{"x": 1}, {"x": 2}],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )
    assert vm.count("test_col") == 2


def test_get_all_embeddings(vm):
    vm.upsert(
        "test_col",
        ids=["a"],
        documents=["doc"],
        metadatas=[{"x": 1}],
        embeddings=[[1.0, 0.0]],
    )
    ids, embeddings = vm.get_all_embeddings("test_col")
    assert len(ids) == 1
    assert embeddings.shape == (1, 2)
    assert embeddings.dtype == np.float32


def test_query_by_vector(vm):
    vm.upsert(
        "test_col",
        ids=["a", "b"],
        documents=["first", "second"],
        metadatas=[{}, {}],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )
    results = vm.query_by_vector("test_col", [1.0, 0.0], n_results=1)
    assert len(results) == 1
    assert results[0]["document"] == "first"


def test_list_collections(vm):
    vm.get_or_create_collection("col_a")
    vm.get_or_create_collection("col_b")
    names = vm.list_collections()
    assert "col_a" in names
    assert "col_b" in names
