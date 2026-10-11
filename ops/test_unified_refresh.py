import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('refresh',Path(__file__).parents[1]/'scripts/unified-market-refresh.py')
refresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(refresh)
class RefreshTests(unittest.TestCase):
 def test_local_snapshot_refresh_commits_existing_database(self):
  with tempfile.TemporaryDirectory() as folder:
   core=Path(folder);(core/'data').mkdir()
   dbfile=core/'data/world_model_market.sqlite'
   with sqlite3.connect(dbfile) as c:c.execute('CREATE TABLE preserved(value TEXT)');c.execute("INSERT INTO preserved VALUES('old')")
   def sync(c,rh_db):
    self.assertEqual(rh_db,'local-input.sqlite');c.execute("INSERT INTO preserved VALUES('new')");return {'recomputed_assets':1}
   self.assertEqual(refresh.refresh(core,Path('local-input.sqlite'),sync)['recomputed_assets'],1)
   with sqlite3.connect(dbfile) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM preserved').fetchone()[0],2)
 def test_failed_refresh_rolls_back_and_retains_published_data(self):
  with tempfile.TemporaryDirectory() as folder:
   core=Path(folder);(core/'data').mkdir();dbfile=core/'data/world_model_market.sqlite'
   with sqlite3.connect(dbfile) as c:c.execute('CREATE TABLE preserved(value TEXT)');c.execute("INSERT INTO preserved VALUES('old')")
   def failed(c,rh_db):c.execute("INSERT INTO preserved VALUES('failed')");raise RuntimeError('source unavailable')
   with self.assertRaises(RuntimeError):refresh.refresh(core,Path('missing.sqlite'),failed)
   with sqlite3.connect(dbfile) as c:self.assertEqual(c.execute('SELECT value FROM preserved').fetchall(),[('old',)])
