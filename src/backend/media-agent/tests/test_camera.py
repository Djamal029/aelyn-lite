"""Tests pour aelyn_media.camera.

Aucune vraie caméra requise : `cv2` est entièrement mocké, donc ces
tests passent sans webcam ni Iriun Webcam branchés. Ce qu'on vérifie
concrètement : la résolution nom -> index configuré (le vrai risque
d'échec en usage réel, cf. le module) et que `cv2.VideoCapture` est bien
appelé avec CET index précis, pas le comportement visuel du flux.
"""

from unittest.mock import MagicMock, patch

import aelyn_media.camera as camera_mod


class TestCameraIndex:
    def test_entree_resolves_to_configured_index(self, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 3)
        assert camera_mod.camera_index("entree") == 3

    def test_salon_resolves_to_configured_index(self, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_salon_index", 7)
        assert camera_mod.camera_index("salon") == 7

    def test_unknown_name_returns_none(self):
        assert camera_mod.camera_index("cuisine") is None


def _mock_capture(*, opened: bool = True, frame_ok: bool = True):
    capture = MagicMock()
    capture.isOpened.return_value = opened
    capture.read.return_value = (frame_ok, "un_faux_frame")
    return capture


class TestShowCamera:
    @patch("aelyn_media.camera.cv2")
    def test_uses_configured_index_for_entree(self, mock_cv2, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 3)
        monkeypatch.setattr(camera_mod.settings, "camera_salon_index", 9)
        capture = _mock_capture()
        mock_cv2.VideoCapture.return_value = capture
        mock_cv2.waitKey.return_value = ord("q")  # ferme dès la 1ère frame
        mock_cv2.getWindowProperty.return_value = 1

        code = camera_mod.show_camera("entree")

        mock_cv2.VideoCapture.assert_called_once_with(3)
        assert code == 0

    @patch("aelyn_media.camera.cv2")
    def test_uses_configured_index_for_salon(self, mock_cv2, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 3)
        monkeypatch.setattr(camera_mod.settings, "camera_salon_index", 9)
        capture = _mock_capture()
        mock_cv2.VideoCapture.return_value = capture
        mock_cv2.waitKey.return_value = ord("q")
        mock_cv2.getWindowProperty.return_value = 1

        code = camera_mod.show_camera("salon")

        mock_cv2.VideoCapture.assert_called_once_with(9)
        assert code == 0

    @patch("aelyn_media.camera.cv2")
    def test_unknown_camera_name_never_opens_a_device(self, mock_cv2):
        code = camera_mod.show_camera("cuisine")

        mock_cv2.VideoCapture.assert_not_called()
        assert code == 1

    @patch("aelyn_media.camera.cv2")
    def test_device_that_fails_to_open_returns_error_code(self, mock_cv2, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 0)
        capture = _mock_capture(opened=False)
        mock_cv2.VideoCapture.return_value = capture

        code = camera_mod.show_camera("entree")

        assert code == 1
        capture.release.assert_called_once()
        # Une caméra qui ne s'ouvre pas ne doit jamais entrer dans la
        # boucle d'affichage.
        mock_cv2.imshow.assert_not_called()

    @patch("aelyn_media.camera.cv2")
    def test_interrupted_stream_returns_error_code(self, mock_cv2, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 0)
        capture = _mock_capture(frame_ok=False)
        mock_cv2.VideoCapture.return_value = capture

        code = camera_mod.show_camera("entree")

        assert code == 1
        capture.release.assert_called_once()

    @patch("aelyn_media.camera.cv2")
    def test_releases_capture_and_destroys_window_on_success(self, mock_cv2, monkeypatch):
        monkeypatch.setattr(camera_mod.settings, "camera_entree_index", 0)
        capture = _mock_capture()
        mock_cv2.VideoCapture.return_value = capture
        mock_cv2.waitKey.return_value = ord("q")
        mock_cv2.getWindowProperty.return_value = 1

        camera_mod.show_camera("entree")

        capture.release.assert_called_once()
        mock_cv2.destroyWindow.assert_called_once()
