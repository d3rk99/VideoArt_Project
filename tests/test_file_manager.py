from pathlib import Path

from app.storage.file_manager import FileManager


def test_output_path_resolution(tmp_path: Path) -> None:
    fm = FileManager(
        live_capture_dir=tmp_path / "live",
        comfy_input_dir=tmp_path / "comfy",
        output_latest_dir=tmp_path / "latest",
        output_archive_dir=tmp_path / "archive",
    )
    session_id = "abc"
    assert fm.session_raw_path(session_id) == tmp_path / "live" / "abc_raw.jpg"
    assert fm.session_comfy_input_path(session_id) == tmp_path / "comfy" / "abc_input.jpg"
