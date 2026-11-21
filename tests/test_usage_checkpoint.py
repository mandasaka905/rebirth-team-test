import json
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from rebirth.control import RunControl,LimitExceeded


class UsageCheckpointTests(unittest.TestCase):
    def test_last_reserved_request_survives_without_any_response(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json'
            c=RunControl(journal_path=path)
            c.reserve(123)
            value=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['calls'],1)
            self.assertEqual(value['input_bytes'],123)
            self.assertEqual(value['event'],'reserved_before_send')
            self.assertGreater(value['owner_pid'],0)
            with self.assertRaises(FileExistsError):RunControl(journal_path=path)

    def test_output_over_limit_is_saved_before_stopping(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json'
            c=RunControl(journal_path=path,max_output_bytes=10)
            with self.assertRaises(LimitExceeded):c.receive(11)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['output_bytes'],11)

    def test_parallel_reservations_never_overwrite_a_newer_count(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json'
            c=RunControl(journal_path=path)
            with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(c.reserve,[10]*20))
            value=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(value['calls'],20)
            self.assertEqual(value['input_bytes'],200)
            self.assertFalse(path.with_suffix('.json.tmp').exists())


if __name__=='__main__':unittest.main()
