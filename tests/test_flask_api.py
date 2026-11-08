import tempfile
import unittest
import uuid
import importlib.util
# Only skip when Flask itself is not installed (local stdlib-only validation).
# An actual backend import failure must surface as a test error on the server.
if importlib.util.find_spec('flask') is None:
    create_app=None
else:
    from backend.app import create_app

@unittest.skipIf(create_app is None,'Flask must be installed for API tests')
class FlaskAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'API_TOKEN':'test-token'})
        self.client=self.app.test_client()
        self.headers={'Authorization':'Bearer test-token'}

    def test_security_and_lifecycle(self):
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertEqual(self.client.get('/api/layouts').status_code,401)
        self.assertEqual(self.client.get('/api/layouts',headers=self.headers).status_code,200)
        data={'id':str(uuid.uuid4()),'name':'City Car','blueprint':{
            'schema':'procedural-vehicle/v3','vehicle':{'name':'City Car'},'modules':{'front':{}},'occupants':2}}
        created=self.client.post('/api/layouts',json=data,headers=self.headers)
        self.assertEqual(created.status_code,201)
        record=self.client.get('/api/layouts/'+data['id'],headers=self.headers).json['layout']
        self.assertEqual(record['revision'],1)
        data['revision']=1
        modified=self.client.put('/api/layouts/'+data['id'],json=data,headers=self.headers)
        self.assertEqual(modified.json['layout']['revision'],2)
        stale=self.client.put('/api/layouts/'+data['id'],json=data,headers=self.headers)
        self.assertEqual(stale.status_code,409)
        bad_origin=self.client.post('/api/layouts',json=data,headers={**self.headers,'Origin':'https://other.example'})
        self.assertEqual(bad_origin.status_code,403)
        deleted=self.client.delete('/api/layouts/'+data['id'],json={'revision':2},headers=self.headers)
        self.assertEqual(deleted.status_code,204)

    def test_guest_identity_ownership_gallery_and_admin_logs(self):
        guest=self.client.post('/api/identity/guest',json={'name':'Guest One'})
        self.assertEqual(guest.status_code,201,guest.json)
        first=guest.json;token=first['token']
        member_headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.get('/api/identity/me',headers=member_headers).status_code,200)
        self.assertEqual(self.client.get('/api/me/layouts').status_code,401)
        second=self.client.post('/api/identity/guest',json={'name':'Guest Two'}).json
        second_headers={'Authorization':'Bearer '+second['token']}
        id=str(uuid.uuid4());data={'id':id,'name':'My custom car',
            'blueprint':{'schema':'procedural-vehicle/v3','vehicle':{'name':'City Car'},
                         'modules':{'front':{}},'occupants':0,
                         'metadata':{'category':'Urban','images':[{'label':'Hero','data':'data:image/jpeg;base64,QQAA'}]}}}
        response=self.client.post('/api/me/layouts',headers=member_headers,json=data)
        self.assertEqual(response.status_code,201,response.json)
        self.assertEqual(self.client.get('/api/me/layouts/'+id,headers=second_headers).status_code,404)
        self.assertEqual(self.client.get('/api/gallery').json['layouts'],[])
        data['visibility']='public';data['revision']=1
        self.assertEqual(self.client.put('/api/me/layouts/'+id,headers=member_headers,json=data).status_code,200)
        self.assertEqual(len(self.client.get('/api/gallery').json['layouts']),1)
        self.assertEqual(self.client.get('/api/gallery').json['layouts'][0]['category'],'Urban')
        self.assertTrue(self.client.get('/api/gallery').json['layouts'][0]['preview'].startswith('data:image/jpeg;'))
        self.assertEqual(self.client.get('/api/gallery/'+id).json['layout']['name'],'My custom car')
        self.assertEqual(self.client.get('/api/admin/logs',headers=member_headers).status_code,401)
        self.assertEqual(self.client.get('/api/admin/logs',headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/me/layouts',headers={**member_headers,
            'Origin':'https://attacker.invalid'},json=data).status_code,403)
        self.assertEqual(self.client.post('/api/providers/test',headers=member_headers,
            json={'provider':'tripo','key':'some-secret'}).status_code,422)

if __name__=='__main__':unittest.main()

# AHOLO Lux3D integration: all credential probes must stay read-only.
class _FakeLuxResponse(__import__('io').BytesIO):
    def __init__(self, value):
        import json
        super().__init__(json.dumps(value).encode('utf-8'))
        self.headers = {}

@unittest.skipIf(create_app is None,'Flask must be installed for API tests')
class Lux3DTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'API_TOKEN':'admin-test'}).test_client()
        identity=self.client.post('/api/identity/guest',json={'name':'Lux test'}).json
        self.headers={'Authorization':'Bearer '+identity['token']}

    def test_probe_is_read_only_and_no_credit_balance_is_fabricated(self):
        from unittest.mock import patch
        captured=[]
        def fake_urlopen(req,timeout):
            captured.append(req)
            return _FakeLuxResponse({'c':'0','d':{'items':[],'total':0}})
        with patch('backend.app.urllib.request.urlopen',side_effect=fake_urlopen):
            response=self.client.post('/api/providers/lux3d/test',headers=self.headers,
                json={'key':'very-secret-test-key','region':'international'})
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(response.json['authenticated'])
        self.assertIsNone(response.json['balance'])
        self.assertFalse(response.json['balance_available'])
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0].get_method(),'GET')
        self.assertEqual(captured[0].get_header('Authorization'),'very-secret-test-key')
        self.assertIn('/global/lux3d/v1/generate/task/list?',captured[0].full_url)
        self.assertNotIn('very-secret-test-key',str(response.json))

    def test_generation_requires_explicit_spend_permission(self):
        from unittest.mock import patch
        with patch('backend.app.urllib.request.urlopen') as request_mock:
            response=self.client.post('/api/providers/lux3d/create',headers=self.headers,
                json={'key':'very-secret-test-key','region':'international','prompt':'Compact electric car'})
        self.assertEqual(response.status_code,400)
        request_mock.assert_not_called()

    def test_generation_body_shell_and_status_are_separate_endpoints(self):
        from unittest.mock import patch
        import json
        captured=[]
        def fake_urlopen(req,timeout):
            captured.append(req)
            if '/task/get?' in req.full_url:
                return _FakeLuxResponse({'c':'0','d':{'status':3,'outputs':[{'content':'https://example.com/render.glb'}]}})
            return _FakeLuxResponse({'c':'0','d':1234567})
        with patch('backend.app.urllib.request.urlopen',side_effect=fake_urlopen):
            creation=self.client.post('/api/providers/lux3d/create',headers=self.headers,json={
                'key':'very-secret-test-key','region':'international','prompt':'Modern hatchback car with a low nose',
                'component':'chassis','version':'G1','style':'photorealistic','spend_ack':True})
            status=self.client.post('/api/providers/lux3d/status',headers=self.headers,
                json={'key':'very-secret-test-key','region':'international','task_id':1234567})
        self.assertEqual(creation.status_code,202,creation.json)
        self.assertEqual(status.status_code,200,status.json)
        self.assertEqual(status.json['state'],'success')
        self.assertEqual(len(captured),2)
        body=json.loads(captured[0].data)
        self.assertIn('No wheels, tyres',body['prompt'])
        self.assertEqual(body['outputFormat'],['glb','zip'])
        self.assertEqual(captured[0].get_method(),'POST')
        self.assertEqual(captured[1].get_method(),'GET')

    def test_wrong_region_and_missing_profile_are_rejected(self):
        bad=self.client.post('/api/providers/lux3d/test',headers=self.headers,
            json={'key':'very-secret-test-key','region':'http://internal.invalid'})
        self.assertEqual(bad.status_code,400)
        unauth=self.client.post('/api/providers/lux3d/test',json={'key':'very-secret-test-key'})
        self.assertEqual(unauth.status_code,401)
