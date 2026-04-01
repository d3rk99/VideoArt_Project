import importlib
import sys
import types


def _load_camera_manager_with_fake_cv2(fake_capture_factory):
    fake_cv2 = types.SimpleNamespace(
        CAP_DSHOW=700,
        CAP_MSMF=1400,
        CAP_ANY=0,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_FPS=5,
        CAP_PROP_BUFFERSIZE=38,
        VideoCapture=fake_capture_factory,
        imshow=lambda *args, **kwargs: None,
        waitKey=lambda *args, **kwargs: 0,
        destroyAllWindows=lambda: None,
    )
    sys.modules["cv2"] = fake_cv2
    sys.modules["numpy"] = types.SimpleNamespace(ndarray=object)
    if "app.camera.camera_manager" in sys.modules:
        del sys.modules["app.camera.camera_manager"]
    mod = importlib.import_module("app.camera.camera_manager")
    return mod


class _FakeCapture:
    def __init__(self, frames):
        self._frames = list(frames)
        self.released = False
        self.props = {}
        self.opened = True

    def isOpened(self):
        return self.opened and not self.released

    def set(self, key, value):
        self.props[key] = value
        return True

    def get(self, key):
        return self.props.get(key, 0)

    def read(self):
        if not self._frames:
            return False, None
        return self._frames.pop(0)

    def release(self):
        self.released = True


def test_windows_auto_backend_uses_dshow(monkeypatch):
    captures = []

    def factory(index, backend):
        cap = _FakeCapture(frames=[(True, object())])
        captures.append((index, backend, cap))
        return cap

    mod = _load_camera_manager_with_fake_cv2(factory)
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")

    cfg = mod.CameraConfig(index=0, width=1280, height=720, fps=30, reconnect_attempts=1, reconnect_delay_seconds=0.0, preview_enabled=False)
    cam = mod.CameraManager(cfg)
    assert cam.connect() is True
    assert captures[0][1] == mod.cv2.CAP_DSHOW


def test_reconnect_after_failure_threshold(monkeypatch):
    first = _FakeCapture(frames=[(False, None), (False, None), (False, None), (False, None), (False, None)])
    second = _FakeCapture(frames=[(True, object())])
    instances = [first, second]

    def factory(index, backend):
        return instances.pop(0)

    mod = _load_camera_manager_with_fake_cv2(factory)
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(mod.time, "sleep", lambda *_args, **_kwargs: None)

    cfg = mod.CameraConfig(
        index=0,
        width=1280,
        height=720,
        fps=30,
        reconnect_attempts=1,
        reconnect_delay_seconds=0.0,
        preview_enabled=False,
        reconnect_fail_threshold=5,
    )
    cam = mod.CameraManager(cfg)
    assert cam.connect() is True

    for _ in range(5):
        assert cam.read_frame() is None

    frame = cam.read_frame()
    assert frame is not None


def test_failure_counter_resets_after_success(monkeypatch):
    cap = _FakeCapture(frames=[(False, None), (True, object())])

    def factory(index, backend):
        return cap

    mod = _load_camera_manager_with_fake_cv2(factory)
    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")

    cfg = mod.CameraConfig(index=0, width=1280, height=720, fps=30, reconnect_attempts=1, reconnect_delay_seconds=0.0, preview_enabled=False, reconnect_fail_threshold=5)
    cam = mod.CameraManager(cfg)
    assert cam.connect() is True
    assert cam.read_frame() is None
    assert cam._failed_reads == 1
    assert cam.read_frame() is not None
    assert cam._failed_reads == 0
