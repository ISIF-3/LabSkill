"""Regression checks for the app coexisting with other loopback tools."""
import contextlib
import errno
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

RUNTIME = Path(__file__).resolve().parents[2] / 'labskill-catalog'
sys.path.insert(0, str(RUNTIME))
import app
import desktop


class LauncherTests(unittest.TestCase):
    def test_cli_starts_on_app_port_without_probing_shared_tool_port(self):
        controller, server = Mock(), Mock()
        with patch.object(app, 'AppController', return_value=controller), \
                patch.object(app, 'is_existing_app', return_value=False) as existing, \
                patch.object(app, 'create_server', return_value=server) as create, \
                contextlib.redirect_stdout(io.StringIO()):
            result = app.main(['--no-open', '--no-collect'])
        self.assertEqual(result, 0)
        existing.assert_called_once_with(18765)
        create.assert_called_once_with(controller, 18765)
        controller.refresh.assert_not_called()
        server.serve_forever.assert_called_once()
        server.server_close.assert_called_once()

    def test_real_port_conflict_has_its_own_exit_status(self):
        controller = Mock()
        with patch.object(app, 'AppController', return_value=controller), \
                patch.object(app, 'is_existing_app', return_value=False), \
                patch.object(app, 'create_server', side_effect=OSError(errno.EADDRINUSE, 'Address already in use')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            result = app.main(['--no-open', '--no-collect'])
        self.assertEqual(result, 98)
        self.assertIn('18765', output.getvalue())
        self.assertNotIn('Python', output.getvalue())
        controller.close.assert_called_once()

    def test_windows_uses_the_same_app_port(self):
        self.assertEqual(desktop.PORT, 18765)
        self.assertEqual(desktop.URL, 'http://127.0.0.1:18765/')


if __name__ == '__main__':
    unittest.main()
