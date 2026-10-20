#!/usr/bin/env python3
"""Dispatch candidate preparation or promotion; never relay runtime payloads."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent/'build'))
from public_releases import prepare, promote, verify_file
from runtime_distribution import resolve_index, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Exact verified internal producer selection')
    parser.add_argument('--check', action='store_true',
                        help='Prepare immutable candidates on runners, without changing public latest')
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    receipt = json.loads((archive.parent/'download-receipt.json').read_text())
    verify_file(archive, receipt['files'][archive.name])
    record = archive.parent/'github-component.json'
    verify_file(record, receipt['files'][record.name])
    component = json.loads(record.read_text())
    if component['stage'] != 'wine-product' or component['identity'] != receipt['reference']['identity']:
        raise ValueError('Expected the verified final Wine product')
    resolve_index(archive)
    print('Validated publication input SHA-256:', sha(archive), flush=True)
    (prepare if args.check else promote)(archive)


if __name__ == '__main__':
    main()
