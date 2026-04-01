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


def test_write_workflow_outputs_and_latest(tmp_path: Path) -> None:
    fm = FileManager(
        live_capture_dir=tmp_path / "live",
        comfy_input_dir=tmp_path / "comfy",
        output_latest_dir=tmp_path / "latest",
        output_archive_dir=tmp_path / "archive",
    )

    outputs = fm.write_workflow_outputs(
        session_id="session_1",
        workflow_name="mona_lisa",
        outputs=[("foo.png", b"abc"), ("bar.jpg", b"def")],
    )
    latest = fm.copy_to_latest(outputs)

    assert len(outputs) == 2
    assert outputs[0].exists()
    assert len(latest) == 2
    assert latest[0].name == "latest_1.png"


def test_clear_comfy_input_images(tmp_path: Path) -> None:
    fm = FileManager(
        live_capture_dir=tmp_path / "live",
        comfy_input_dir=tmp_path / "comfy",
        output_latest_dir=tmp_path / "latest",
        output_archive_dir=tmp_path / "archive",
    )
    a = fm.comfy_input_dir / "a.jpg"
    b = fm.comfy_input_dir / "b.png"
    a.write_bytes(b"x")
    b.write_bytes(b"y")

    fm.clear_comfy_input_images()

    assert not a.exists()
    assert not b.exists()
