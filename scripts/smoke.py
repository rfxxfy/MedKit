"""Explicit integration smoke on a disposable demo installation.
Run inside the app container after seed-demo:
  python /tmp/smoke.py
Creates an isolated demo kit, completes it, checks OCR/PDF and archives it.
Uses only stdlib plus the application's Pillow dependency.
"""
import http.cookiejar
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFont

origin = os.environ.get('BASE_URL', 'http://localhost:8010')
base = 'http://127.0.0.1:8000'
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ''


def request(path, method='GET', body=None, content_type=None):
    headers = {'Origin': origin, 'X-CSRF-Token': csrf}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        content_type = 'application/json'
    if content_type:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(base+path, data=body, headers=headers, method=method)
    try:
        with client.open(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'{method} {path}: {exc.code}: {exc.read().decode()}') from exc


session = request('/api/v1/auth/login', 'POST', {'email':'admin@medkit.demo','password':'MedkitDemo2026!'})
csrf = session['csrf_token']
template = request('/api/v1/templates')[0]
kit = request('/api/v1/kits', 'POST', {'name':'SMOKE · интеграционная проверка','location':'Искусственные данные','template_id':template['id'],'interval_days':30})
draft = request(f"/api/v1/kits/{kit['id']}/inspections",'POST')
# Synthetic OCR label: this verifies the pipeline, not the OCR-01 quality target.
image = Image.new('RGB',(1100,250),'white')
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',64)
ImageDraw.Draw(image).text((35,70),'EXP 31.12.2028',font=font,fill='black')
photo = io.BytesIO()
image.save(photo,format='PNG')
boundary='medkit-smoke-boundary'
multipart = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="label.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+photo.getvalue()+f'\r\n--{boundary}--\r\n'.encode())
ocr = request(f"/api/v1/inspections/{draft['id']}/items/{draft['items'][0]['id']}/ocr",'POST',multipart,f'multipart/form-data; boundary={boundary}')
assert ocr['status']=='CANDIDATE',ocr
assert ocr['candidate']['normalized_date']=='2028-12-31',ocr
unchanged = request(f"/api/v1/inspections/{draft['id']}")
assert unchanged==draft,'OCR must not modify facts'
for index,item in enumerate(draft['items']):
    actual = item['required_qty']
    groups=[]
    if index==0:
        actual=3
        groups=[{'qty':1,'expiry_state':'KNOWN','input_value':'2000-01-01','confirmed':True}, {'qty':1,'expiry_state':'UNKNOWN','unknown_reason':'UNREADABLE'}, {'qty':1,'expiry_state':'KNOWN','input_value':'2099-12-31','confirmed':True}]
    elif item['requires_expiry'] and actual:
        groups=[{'qty':actual,'expiry_state':'KNOWN','input_value':'2099-12-31','confirmed':True}]
    draft = request(f"/api/v1/inspections/{draft['id']}/items/{item['id']}",'PUT',{'expected_revision':draft['revision'],'actual_qty':actual,'confirmed':True,'groups':groups})
result = request(f"/api/v1/inspections/{draft['id']}/complete",'POST',{'expected_revision':draft['revision']})
assert result['result']=='PROBLEM'
assert result['items'][0]['replenish_qty']==3
assert result['items'][0]['reasons']==['SHORTAGE','EXPIRED','EXPIRY_UNKNOWN']
assert request(f"/api/v1/inspections/{draft['id']}/complete",'POST',{'expected_revision':1})==result
pdf=request(f"/api/v1/inspections/{draft['id']}/report.pdf")
assert pdf.startswith(b'%PDF-')
assert request(f"/api/v1/kits/{kit['id']}/qr").startswith(b'\x89PNG')
request(f"/api/v1/kits/{kit['id']}/archive",'POST')
print(json.dumps({'status':'passed','kit_id':kit['id'],'inspection_id':result['id'],'ocr_status':ocr['status'],'ocr_date':ocr['candidate']['normalized_date'],'pdf_bytes':len(pdf),'result':result['result']},ensure_ascii=False))
