"""Write version metadata for a container build."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gateway'))
from version import build_info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',default=None)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    info=build_info(args.revision or None)
    if not info['revision']:
        parser.error('Git metadata is unavailable; pass --revision with the source commit SHA')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
