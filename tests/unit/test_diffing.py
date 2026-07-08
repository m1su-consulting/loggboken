from app.diffing import compute_environment_diff


def test_same_artifact_same_version_is_same() -> None:
    items = compute_environment_diff(
        [("nginx", "1.25", "proj1", "cluster-a")], [("nginx", "1.25", "proj2", "cluster-b")]
    )

    assert items == [
        {
            "artifact_name": "nginx",
            "left": [{"environment_name": "proj1", "version": "1.25", "host_or_cluster": "cluster-a"}],
            "right": [{"environment_name": "proj2", "version": "1.25", "host_or_cluster": "cluster-b"}],
            "status": "same",
        }
    ]


def test_same_artifact_different_version_is_different() -> None:
    items = compute_environment_diff(
        [("nginx", "1.25", "proj1", "cluster-a")], [("nginx", "1.24", "proj2", "cluster-a")]
    )

    assert items[0]["status"] == "different"
    assert items[0]["left"] == [
        {"environment_name": "proj1", "version": "1.25", "host_or_cluster": "cluster-a"}
    ]
    assert items[0]["right"] == [
        {"environment_name": "proj2", "version": "1.24", "host_or_cluster": "cluster-a"}
    ]


def test_artifact_only_on_left() -> None:
    items = compute_environment_diff([("redis", "7.0", "proj1", "cluster-a")], [])

    assert items == [
        {
            "artifact_name": "redis",
            "left": [{"environment_name": "proj1", "version": "7.0", "host_or_cluster": "cluster-a"}],
            "right": [],
            "status": "left_only",
        }
    ]


def test_artifact_only_on_right() -> None:
    items = compute_environment_diff([], [("redis", "7.0", "proj2", "cluster-a")])

    assert items == [
        {
            "artifact_name": "redis",
            "left": [],
            "right": [{"environment_name": "proj2", "version": "7.0", "host_or_cluster": "cluster-a"}],
            "status": "right_only",
        }
    ]


def test_host_or_cluster_can_be_none() -> None:
    items = compute_environment_diff([("openssl", "3.0", "proj1", None)], [])

    assert items[0]["left"] == [
        {"environment_name": "proj1", "version": "3.0", "host_or_cluster": None}
    ]


def test_multiple_namespaces_within_one_side_are_kept_separate() -> None:
    items = compute_environment_diff(
        [
            ("nginx", "1.25", "proj1-a", "cluster-a"),
            ("nginx", "1.26", "proj1-b", "cluster-a"),
        ],
        [("nginx", "1.25", "proj2-a", "cluster-b")],
    )

    assert items[0]["left"] == [
        {"environment_name": "proj1-a", "version": "1.25", "host_or_cluster": "cluster-a"},
        {"environment_name": "proj1-b", "version": "1.26", "host_or_cluster": "cluster-a"},
    ]
    assert items[0]["status"] == "different"


def test_same_version_across_multiple_namespaces_on_one_side_is_same() -> None:
    items = compute_environment_diff(
        [
            ("nginx", "1.25", "proj1-a", "cluster-a"),
            ("nginx", "1.25", "proj1-b", "cluster-a"),
        ],
        [("nginx", "1.25", "proj2-a", "cluster-b")],
    )

    assert items[0]["status"] == "same"
    assert len(items[0]["left"]) == 2


def test_results_sorted_by_artifact_name() -> None:
    items = compute_environment_diff(
        [("zeta", "1.0", "proj1", "cluster-a"), ("alpha", "1.0", "proj1", "cluster-a")],
        [("alpha", "1.0", "proj2", "cluster-b")],
    )

    names = [item["artifact_name"] for item in items]
    assert names == ["alpha", "zeta"]


def test_left_entries_sorted_by_environment_name() -> None:
    items = compute_environment_diff(
        [("nginx", "1.0", "proj1-b", "cluster-a"), ("nginx", "1.0", "proj1-a", "cluster-a")], []
    )

    envs = [entry["environment_name"] for entry in items[0]["left"]]
    assert envs == ["proj1-a", "proj1-b"]


def test_empty_both_sides() -> None:
    assert compute_environment_diff([], []) == []
