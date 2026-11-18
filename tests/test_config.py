import os
import unittest
from unittest.mock import patch

from app import create_app


class ApplicationConfigTestCase(unittest.TestCase):
    def test_production_requires_private_secret(self):
        for secret in ('', 'placeholder', 'replace-with-a-random-secret-before-running'):
            with self.subTest(secret=secret), patch.dict(os.environ, {'SECRET_KEY': secret}):
                with self.assertRaisesRegex(RuntimeError, 'Set SECRET_KEY'):
                    create_app('production')

    def test_production_uses_secret_and_disables_debug(self):
        secret = 'x' * 64
        with patch.dict(os.environ, {'SECRET_KEY': secret}):
            app = create_app('production')

        self.assertEqual(app.config['SECRET_KEY'], secret)
        self.assertFalse(app.config['DEBUG'])
