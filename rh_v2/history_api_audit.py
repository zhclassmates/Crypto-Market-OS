"""Append-only request accounting for the existing GMGN transport, no secrets."""
import json
import os
import time
import uuid
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'.grok/history-api-events.jsonl'


def event(request_id,route,outcome):
    PATH.parent.mkdir(exist_ok=True)
    data=(json.dumps({'id':request_id,'route':route,'outcome':outcome,'at':int(time.time())})+'\n').encode()
    fd=os.open(PATH,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:os.write(fd,data)
    finally:os.close(fd)


def start(args):
    ident=uuid.uuid4().hex
    route=' '.join(args[:2])
    event(ident,route,'started')
    return ident,route


def metrics(now):
    day=now-now%86400;requests={};done={}
    if PATH.exists():
        with PATH.open() as stream:
            for line in stream:
                try:r=json.loads(line)
                except ValueError:continue
                if r['at']<day:continue
                if r['outcome']=='started':requests[r['id']]=r['route']
                else:done[r['id']]=r['outcome']
    routes={}
    for ident,route in requests.items():
        row=routes.setdefault(route,{'requests':0,'failed':0,'pending':0})
        row['requests']+=1
        status=done.get(ident)
        row['pending']+=int(status is None)
        row['failed']+=int(status is not None and status!='success')
    for row in routes.values():row['failure_rate']=row['failed']/row['requests']
    return {'since_activation_only':True,'requests':len(requests),'routes':routes}
