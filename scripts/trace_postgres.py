"""TRACE-01 against the running demo server. Synthetic records, archived test kit.
Execute in app container, then restart app/db and execute with --verify.
"""
import http.cookiejar
import json
import os
import sys
import urllib.request

base = 'http://127.0.0.1:8000/api/v1'
origin = os.environ.get('BASE_URL', 'http://localhost:8010')
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf = ''


def request(path, method='GET', data=None):
    payload = json.dumps(data).encode() if data is not None else None
    headers = {'Origin':origin, 'X-CSRF-Token':csrf, 'Content-Type':'application/json'}
    with client.open(urllib.request.Request(base+path, data=payload, headers=headers, method=method),timeout=30) as response:
        return json.load(response)


csrf = request('/auth/login','POST',{'email':'admin@medkit.demo','password':'MedkitDemo2026!'})['csrf_token']
name = 'TRACE-100 · автоматическая проверка'
if '--verify' not in sys.argv:
    template = request('/templates','POST',{'name':'TRACE-100 · учебный шаблон','items':[{'name':'Учебный предмет','unit':'шт.','required_qty':1,'requires_expiry':False}]})
    kit = request('/kits','POST',{'name':name,'location':'Искусственные данные TRACE-01','template_id':template['id'],'interval_days':30})
    for n in range(100):
        draft = request(f"/kits/{kit['id']}/inspections",'POST')
        draft = request(f"/inspections/{draft['id']}/items/1",'PUT',{'expected_revision':draft['revision'],'actual_qty':n%2,'confirmed':True,'groups':[]})
        result = request(f"/inspections/{draft['id']}/complete",'POST',{'expected_revision':draft['revision']})
        assert result['result']==('OK' if n%2 else 'PROBLEM')
    request(f"/kits/{kit['id']}/archive",'POST')
else:
    kit = next(k for k in reversed(request('/kits')) if k['name']==name)
records = []
for page in range(1,6):
    records += request(f"/kits/{kit['id']}/inspections?page={page}")['items']
assert len(records)==100
for record in records:
    assert all(record[k] is not None for k in ['id','owner_id','started_at','completed_at','inspection_date','result','snapshot','items'])
    s=record['snapshot']
    assert all(k in s for k in ['organization_name','kit_name','location','inspector_name','timezone','interval_days','template_id','template_name','template_version'])
    assert all(k in record['items'][0] for k in ['groups','checked_at','shortage_qty','expired_qty','unknown_qty','eligible_qty','replenish_qty','reasons'])
print(json.dumps({'test':'TRACE-01 PostgreSQL','count':len(records),'complete_records':100,'phase':'after_restart' if '--verify' in sys.argv else 'created','kit_id':kit['id']}))
