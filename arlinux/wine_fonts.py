#!/usr/bin/env python3
"""Copy the builder's Windows Latin and CJK fallback fonts into Bionic Wine."""
import hashlib
import json
import os
from pathlib import Path
import shutil

FILES = ('arial.ttf', 'arialbd.ttf', 'ariali.ttf', 'arialbi.ttf', 'msyh.ttc')


def source_directory():
    if os.name == 'nt':
        return Path(os.environ.get('ARLINUX_WINDOWS_FONTS', os.environ.get('WINDIR', 'C:/Windows') + '/Fonts'))
    return Path(os.environ['ARLINUX_WINDOWS_FONTS'])


def install(destination):
    source = source_directory()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in FILES:
        shutil.copyfile(source/name, destination/name)
        hashes[name] = hashlib.sha256((destination/name).read_bytes()).hexdigest()
    (destination/'arlinux-fonts.json').write_text(json.dumps(dict(
        families=['Arial', 'Microsoft YaHei', 'Microsoft YaHei UI'],
        source='Windows build host', modified=False, files=hashes), indent=2)+'\n')


if __name__ == '__main__':
    import sys
    install(sys.argv[1])
