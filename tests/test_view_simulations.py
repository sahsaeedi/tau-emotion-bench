from tau_emotion.scripts.view_simulations import get_available_simulations


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    return path


def test_finds_results_at_any_depth(tmp_path):
    default_run = _touch(tmp_path / "airline" / "gpt-4.1" / "results.json")
    save_to_run = _touch(tmp_path / "my_run" / "results.json")
    # A directory-format run keeps its simulations next to results.json.
    dir_run = _touch(tmp_path / "bank" / "gpt-4.1_train" / "results.json")
    _touch(tmp_path / "bank" / "gpt-4.1_train" / "simulations" / "abc.json")

    assert get_available_simulations(tmp_path) == sorted(
        [default_run, save_to_run, dir_run]
    )


def test_prefers_reviewed_results(tmp_path):
    run_dir = tmp_path / "retail" / "gpt-4.1"
    _touch(run_dir / "results.json")
    reviewed = _touch(run_dir / "results_reviewed.json")

    assert get_available_simulations(tmp_path) == [reviewed]


def test_missing_dir(tmp_path):
    assert get_available_simulations(tmp_path / "nope") == []
