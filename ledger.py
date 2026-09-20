"""Dependency-free, local-first legal/census ingestion and retrieval foundation.

No historical documents are bundled or claimed to be verified. Only ingest material
whose rights, provenance, and publication permissions have been checked.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jurisdictions (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, era TEXT NOT NULL,
 start_year INTEGER, end_year INTEGER,
 CHECK(end_year IS NULL OR start_year IS NULL OR end_year >= start_year)
);
CREATE TABLE IF NOT EXISTS records (
 id INTEGER PRIMARY KEY, jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
 kind TEXT NOT NULL CHECK(kind IN ('LAW','CENSUS')),
 title TEXT NOT NULL, text TEXT NOT NULL, source_url TEXT NOT NULL,
 source_license TEXT NOT NULL, as_of TEXT NOT NULL,
 target_year INTEGER, population INTEGER CHECK(population IS NULL OR population >= 0),
 sha256 TEXT NOT NULL, UNIQUE(jurisdiction_id,kind,source_url,sha256),
 CHECK(kind != 'CENSUS' OR target_year IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS records_kind_year ON records(kind,target_year);
"""


def connect(path):
    db = sqlite3.connect(str(path))
    db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    return db


def ingest(db, item):
    required = ('jurisdiction_id','civilization_name','era','kind','title','text','source_url','source_license','as_of')
    if any(not isinstance(item.get(k), str) or not item[k].strip() for k in required):
        raise ValueError('missing or invalid required provenance field')
    if item['kind'] not in ('LAW','CENSUS'):
        raise ValueError('kind must be LAW or CENSUS')
    if not item['source_url'].startswith('https://'):
        raise ValueError('source_url must use HTTPS')
    year = item.get('target_year')
    pop = item.get('population')
    if item['kind'] == 'CENSUS' and (type(year) is not int or type(pop) not in (int,type(None))):
        raise ValueError('census requires integer target_year and optional integer population')
    if pop is not None and (type(pop) is not int or pop < 0):
        raise ValueError('population must be nonnegative integer or null')
    raw = item['text'].encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    with db:
        db.execute('INSERT OR IGNORE INTO jurisdictions(id,name,era,start_year,end_year) VALUES(?,?,?,?,?)',
                   (item['jurisdiction_id'],item['civilization_name'],item['era'],item.get('start_year'),item.get('end_year')))
        cursor = db.execute('INSERT OR IGNORE INTO records(jurisdiction_id,kind,title,text,source_url,source_license,as_of,target_year,population,sha256) VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (item['jurisdiction_id'],item['kind'],item['title'],item['text'],item['source_url'],item['source_license'],item['as_of'],year,pop,digest))
    return {'inserted': cursor.rowcount == 1, 'sha256': digest}


def search(db, query, limit=20):
    if not isinstance(query,str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('query required; limit must be 1..100')
    return [dict(row) for row in db.execute('SELECT r.kind,r.title,r.text,r.source_url,r.source_license,r.as_of,r.target_year,r.population,r.sha256,j.name AS civilization_name FROM records r JOIN jurisdictions j ON j.id=r.jurisdiction_id WHERE r.title LIKE ? OR r.text LIKE ? ORDER BY r.id LIMIT ?', ('%'+query+'%','%'+query+'%',limit))]


def summary(db):
    return {kind: db.execute('SELECT COUNT(*) FROM records WHERE kind=?',(kind,)).fetchone()[0] for kind in ('LAW','CENSUS')}


def main():
    parser = argparse.ArgumentParser(description='Local provenance-aware legal/census ledger')
    parser.add_argument('--db', default='ledger.sqlite3')
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('ingest'); p.add_argument('json_file')
    p = sub.add_parser('search'); p.add_argument('query')
    sub.add_parser('summary')
    args = parser.parse_args()
    with connect(Path(args.db)) as db:
        if args.command == 'ingest':
            result = ingest(db,json.loads(Path(args.json_file).read_text(encoding='utf-8')))
        elif args.command == 'search':
            result = search(db,args.query)
        else:
            result = summary(db)
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
