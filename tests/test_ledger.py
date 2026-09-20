import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import connect, ingest, search, summary


LAW = {'jurisdiction_id':'babylon','civilization_name':'Babylon','era':'Antiquity','kind':'LAW','title':'Sample law','text':'A documented example about property','source_url':'https://example.org/law','source_license':'TEST ONLY','as_of':'2026-09-20'}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'ledger.sqlite3'
        self.db = connect(self.path)
        self.addCleanup(self.db.close)

    def test_law_roundtrip_and_deduplication(self):
        self.assertTrue(ingest(self.db, LAW)['inserted'])
        self.assertFalse(ingest(self.db, LAW)['inserted'])
        self.assertEqual(summary(self.db), {'LAW':1,'CENSUS':0})
        self.assertEqual(search(self.db,'property')[0]['source_license'],'TEST ONLY')

    def test_census_preserves_year_and_population(self):
        census = dict(LAW,kind='CENSUS',target_year=-100,population=1200)
        self.assertTrue(ingest(self.db,census)['inserted'])
        self.assertEqual(search(self.db,'documented')[0]['target_year'],-100)
        self.assertEqual(search(self.db,'documented')[0]['population'],1200)

    def test_rejects_missing_provenance_and_invalid_population(self):
        with self.assertRaises(ValueError): ingest(self.db,dict(LAW,source_license=''))
        with self.assertRaises(ValueError): ingest(self.db,dict(LAW,source_url='http://example.org'))
        with self.assertRaises(ValueError): ingest(self.db,dict(LAW,kind='CENSUS',target_year=2020,population=-1))
        self.assertEqual(summary(self.db)['LAW'],0)

    def test_cli_end_to_end(self):
        source = Path(self.temp.name) / 'sample.json'
        source.write_text(json.dumps(LAW),encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        cmd = [sys.executable,str(root/'ledger.py'),'--db',str(self.path)]
        result = subprocess.run(cmd+['ingest',str(source)],capture_output=True,text=True,check=True)
        self.assertTrue(json.loads(result.stdout)['inserted'])
        result = subprocess.run(cmd+['search','property'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)[0]['title'],'Sample law')


if __name__ == '__main__': unittest.main()
