"""Hosting configuration must preserve accounts and refuse ambiguous origins."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rebirth_platform_entry', ROOT/'deploy/platform.py')
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)


class PlatformConfigTest(unittest.TestCase):
    def test_render_uses_platform_https_address_and_persistent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            config, port = platform.configuration({'RENDER_EXTERNAL_URL':'https://test.onrender.com',
                'REBIRTH_DATA_DIR':directory, 'REBIRTH_REGISTRATION_OPEN':'true'})
            self.assertEqual(config['origin'], 'https://test.onrender.com')
            self.assertEqual(config['data_dir'], directory)
            self.assertTrue(config['registration_open'])
            self.assertTrue(config['demo_only'])
            self.assertEqual(port, 8080)

    def test_missing_origin_or_disk_configuration_refused(self):
        for env in ({}, {'RENDER_EXTERNAL_URL':'https://test.onrender.com'},
                    {'RENDER_EXTERNAL_URL':'https://test.onrender.com','REBIRTH_DATA_DIR':'relative'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                platform.configuration(env)

    def test_registration_stays_closed_without_explicit_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            config, _ = platform.configuration({'REBIRTH_PUBLIC_ORIGIN':'https://test.example.com',
                'REBIRTH_DATA_DIR':directory})
            self.assertFalse(config['registration_open'])

    def test_invalid_port_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                platform.configuration({'REBIRTH_PUBLIC_ORIGIN':'https://test.example.com',
                    'REBIRTH_DATA_DIR':directory,'PORT':'70000'})


if __name__ == '__main__': unittest.main()
