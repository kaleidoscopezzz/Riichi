"""Real HTTP/Session/CSRF workflow against isolated QA service (stdlib only)."""
import http.cookiejar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request
from datetime import datetime, timezone


def main():
    base='http://127.0.0.1:8016/api/v1'
    credentials=json.loads((Path(__file__).resolve().parents[1]/'.verification/f0-06/credentials.json').read_text())
    jar=http.cookiejar.CookieJar();client=build_opener(HTTPCookieProcessor(jar));count=0
    def call(path, method='GET',body=None,expected=200,csrf=True):
        nonlocal count
        headers={'Content-Type':'application/json'}
        if method!='GET' and csrf:
            token=call('/auth/csrf/')['csrf_token'];headers['X-CSRFToken']=token
        req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers=headers)
        try:
            with client.open(req) as r:status=r.status;data=json.load(r)
        except HTTPError as e:status=e.code;data=json.load(e)
        assert status==expected,(path,status,data.get('error',{}))
        count+=1
        return data.get('data',data)
    call('/health/')
    call('/auth/login/','POST',credentials,expected=403,csrf=False)
    call('/auth/login/','POST',credentials)
    players=call('/players/?eligible=true')['results'];ids=[p['id'] for p in players if p['username'].startswith('f006_player')][:16]
    assert len(ids)==16
    machines=call('/machine-resources/')['results'];selected=[m['machine_id'] for m in machines if m['assignable']][:4];assert len(selected)==4
    t=call('/tournaments/','POST',{'name':'HTTP 验收 · 16人6轮','round_count':6,'participant_ids':ids},201)
    pk=t['id'];call(f'/tournaments/{pk}/start/','POST',{})
    call(f'/tournaments/{pk}/rounds/','POST',{'round_number':1},400)
    round=call(f'/tournaments/{pk}/rounds/','POST',{'round_number':1,'machine_ids':selected},201)
    first_seats=[(s['participant_id'],s['seat_wind']) for tb in round['tables'] for s in tb['seats']]
    for number in range(1,7):
        if number>1:round=call(f'/tournaments/{pk}/rounds/','POST',{'round_number':number},201)
        assert [tb['machine_snapshot']['machine_id'] for tb in round['tables']]==selected
        for tb in round['tables']:
            # Includes negative and zero; cyclic decimal pattern also covered.
            raw=[-1000,0,51000,50000] if number==1 else [30000,30000,30000,10000]
            points=[{'participant_id':s['participant_id'],'raw_points':v} for s,v in zip(tb['seats'],raw)]
            saved=call(f'/round-tables/{tb["id"]}/result/','PUT',{'version':0,'points':points})
            confirmed=call(f'/round-tables/{tb["id"]}/result/confirm/','POST',{'version':saved['version']})
            assert confirmed['status']=='confirmed'
            call(f'/round-tables/{tb["id"]}/result/confirm/','POST',{'version':confirmed['version']},409)
        call(f'/tournaments/{pk}/rounds/','POST',{'round_number':number},409)
    workspace=call(f'/tournaments/{pk}/workspace/')
    for members in workspace['unresolved_groups']:
        lottery=call(f'/tournaments/{pk}/lotteries/','POST',{'source_versions':workspace['source_versions'],'members':members,'order':members[::-1],'method':'现场签条（独立QA）','description':'HTTP验收公开抽签流程','drawn_at':datetime.now(timezone.utc).isoformat()},201)
        call(f'/tournaments/{pk}/lotteries/{lottery["id"]}/confirm/','POST',{'confirmed':True})
    workspace=call(f'/tournaments/{pk}/workspace/');assert workspace['ready']
    result=call(f'/tournaments/{pk}/complete/','POST',{'source_versions':workspace['source_versions'],'confirmed':True})
    assert len(result['standings'])==16 and len([r for r in result['standings'] if r['rank']==1])==1
    refreshed=call(f'/tournaments/{pk}/workspace/');assert refreshed['champion_id']==result['champion_id']
    first=call(f'/tournaments/{pk}/rounds/1/');assert [(s['participant_id'],s['seat_wind']) for tb in first['tables'] for s in tb['seats']]==first_seats
    resources=call('/machine-resources/')['results'];assert all(m['assignable'] for m in resources if m['machine_id'] in selected)
    call('/auth/logout/','POST',{})
    call(f'/tournaments/{pk}/workspace/',expected=403)
    print(json.dumps({'result':'PASS','requests_including_csrf':count,'tournament_id':pk,'players':16,'rounds':6,'confirmed_tables':24,'negative_zero_points':True,'first_round_unchanged':True,'frozen_tables_persisted':True,'unique_champion':result['champion_id'],'resources_released':True,'unauthenticated_and_csrf_denied':True},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
