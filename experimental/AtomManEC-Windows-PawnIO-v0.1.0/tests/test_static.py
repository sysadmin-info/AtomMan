"""No I/O tests of source structure, portable to Linux/macOS CI."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModuleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pawn = (ROOT / 'AtomManEC.p').read_text(encoding='utf-8')
        cls.python = (ROOT / 'atomman_ec_windows.py').read_text(encoding='utf-8')

    def test_python_parses(self):
        ast.parse(self.python)

    def test_hardware_addresses(self):
        self.assertIn('const EC_CMD_PORT = 0x6C;', self.pawn)
        self.assertIn('const EC_DATA_PORT = 0x68;', self.pawn)
        self.assertIn('const EC_READ_COMMAND = 0xD5;', self.pawn)
        self.assertIn('const EC_LOW_RPM = 0x18;', self.pawn)
        self.assertIn('const EC_HIGH_RPM = 0x19;', self.pawn)

    def test_single_ioctl_and_bounded_wait(self):
        self.assertEqual(len(re.findall(r'DEFINE_IOCTL_SIZED\(', self.pawn)), 1)
        self.assertIn('EC_WAIT_TRIES = 500', self.pawn)
        self.assertIn('return STATUS_IO_TIMEOUT;', self.pawn)
        self.assertIn('EC_MAX_RPM = 4000', self.pawn)
        self.assertNotIn('ioctl_pio_write', self.pawn)

    def test_explicit_opt_in(self):
        self.assertIn('args.read_once', self.python)
        self.assertIn('verify_hardware()', self.python)
        self.assertIn('aida64_running()', self.python)
        self.assertIn('read_once(', self.python)


if __name__ == '__main__':
    unittest.main()
