"""Validate every supported VLESS transport against the image's real Xray binary."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway'),str(ROOT/'scripts'),str(ROOT/'tests')]
from controller import configuration
from render import parse_vless
from test_vless_transports import transport_cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='xray-gateway:transport-check')
    args=parser.parse_args()
    payload=[]
    for label,source in transport_cases():
        profile={'id':'test','slot':1,'node':parse_vless(source)}
        payload.append((label,configuration([profile])))
    code='''import json,pathlib,subprocess,sys,tempfile
cases=json.load(sys.stdin)
with tempfile.TemporaryDirectory() as folder:
 path=pathlib.Path(folder)/'config.json'
 for label,config in cases:
  path.write_text(json.dumps(config))
  result=subprocess.run(['/usr/local/bin/xray','run','-test','-c',str(path)],capture_output=True,text=True)
  if result.returncode:raise RuntimeError(label+'\\n'+result.stdout+result.stderr)
  print(label+' PASS')
print(str(len(cases))+' XRAY TRANSPORT CONFIGURATIONS PASS')
'''
    subprocess.run(['docker','run','--rm','-i','--network','none','--entrypoint','python3',args.image,'-c',code],
                   input=json.dumps(payload),text=True,check=True)


if __name__=='__main__':main()
