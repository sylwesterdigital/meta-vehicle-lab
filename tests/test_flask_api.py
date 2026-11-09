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

    def test_generation_endpoint_auth_schema_and_mocked_openai(self):
        import base64, io, json
        from unittest.mock import patch
        profile=self.client.post('/api/identity/guest',json={'name':'Creative Tester'}).json
        headers={'Authorization':'Bearer '+profile['token'],'X-Provider-Key':'sample-key-1234567890'}
        request_data={'provider':'openai','prompt':'Clean isolated wheel hub assembly in studio lighting'}
        self.assertEqual(self.client.post('/api/vehicle/generate-image',json=request_data).status_code,401)
        self.assertEqual(self.client.post('/api/vehicle/generate-image',headers=headers,
            json={**request_data,'provider':'other'}).status_code,422)
        class Upstream(io.BytesIO):
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        fake=base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'valid-image-byte-placeholder').decode()
        def provider_response(req,timeout=0):
            self.assertEqual(req.full_url,'https://api.openai.com/v1/images/generations')
            self.assertEqual(json.loads(req.data)['model'],'gpt-image-2.5-flare')
            return Upstream(json.dumps({'data':[{'b64_json':fake}]}).encode())
        with patch('backend.app.urllib.request.urlopen',provider_response):
            result=self.client.post('/api/vehicle/generate-image',headers=headers,json=request_data)
            self.assertEqual(result.status_code,200,result.json)
            self.assertTrue(result.json['image'].startswith('data:image/png;base64,'))

    def test_meta_muse_image_generation_and_edit_route(self):
        import base64, io, json
        from unittest.mock import patch
        identity=self.client.post('/api/identity/guest',json={'name':'Muse Creator'}).json
        headers={'Authorization':'Bearer '+identity['token'],'X-Provider-Key':'meta-test-1234567890'}
        png=base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'fake-png-payload').decode()
        calls=[]
        class Upstream(io.BytesIO):
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        def upstream(req,timeout=0):
            data=json.loads(req.data)
            calls.append((req.full_url,data))
            self.assertEqual(data['model'],'muse-image-1.0')
            self.assertEqual(req.get_header('Authorization'),'Bearer meta-test-1234567890')
            return Upstream(json.dumps({'data':[{'b64_json':png}]}).encode())
        with patch('backend.app.urllib.request.urlopen',upstream):
            first=self.client.post('/api/vehicle/generate-image',json={'provider':'meta',
                'prompt':'Isolated automotive chassis body shell in studio'},headers=headers)
            self.assertEqual(first.status_code,200,first.json)
            self.assertTrue(first.json['image'].startswith('data:image/png;base64,'))
            # Bypass rate limit only for the deliberately isolated second call.
            with patch('backend.app.time.monotonic',return_value=1e10):
                second=self.client.post('/api/vehicle/generate-image',json={'provider':'meta',
                    'prompt':'Give the body a lower front windscreen',
                    'reference_image':'data:image/png;base64,'+png},headers=headers)
            self.assertEqual(second.status_code,200,second.json)
        self.assertEqual(calls[0][0],'https://api.meta.ai/v1/images/generations')
        self.assertEqual(calls[1][0],'https://api.meta.ai/v1/images/edits')
        self.assertTrue(calls[1][1]['images'][0]['image_url'].startswith('data:image/png;base64,'))

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

    def test_wheel_component_uses_isolated_glb_prompt(self):
        from unittest.mock import patch
        import json
        captured=[]
        def fake(req,timeout):
            captured.append(json.loads(req.data))
            return _FakeLuxResponse({'c':'0','d':8787878})
        with patch('backend.app.urllib.request.urlopen',side_effect=fake):
            result=self.client.post('/api/providers/lux3d/create',headers=self.headers,json={
                'key':'wheel-test-secret','region':'international',
                'prompt':'A forged performance alloy wheel with deep offset and mesh spokes',
                'component':'wheel','style':'photorealistic','version':'G1-Turbo','spend_ack':True})
        self.assertEqual(result.status_code,202,result.json)
        self.assertIn('isolated automotive wheel',captured[0]['prompt'])
        self.assertIn('without any car chassis',captured[0]['prompt'])

    def test_wrong_region_and_missing_profile_are_rejected(self):
        bad=self.client.post('/api/providers/lux3d/test',headers=self.headers,
            json={'key':'very-secret-test-key','region':'http://internal.invalid'})
        self.assertEqual(bad.status_code,400)
        unauth=self.client.post('/api/providers/lux3d/test',json={'key':'very-secret-test-key'})
        self.assertEqual(unauth.status_code,401)

# A read-only provider task may return a GLB or a ZIP containing one. A distinct,
# authenticated import action transfers the resulting model without the user
# downloading and re-uploading it. Tests never contact or bill Lux3D.
@unittest.skipIf(create_app is None,'Flask must be installed for API tests')
class LuxImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'API_TOKEN':'admin-test'}).test_client()
        identity=self.client.post('/api/identity/guest',json={'name':'Import test'}).json
        self.headers={'Authorization':'Bearer '+identity['token']}
        self.body={'key':'test-key-with-8-chars','region':'international','task_id':'123'}

    def test_import_requires_owner_and_completed_task(self):
        from unittest.mock import patch
        response=self.client.post('/api/providers/lux3d/import',json=self.body)
        self.assertEqual(response.status_code,401)
        with patch('backend.app.urllib.request.urlopen',return_value=_FakeLuxResponse(
                {'c':'0','d':{'status':1,'outputs':[]}})) as upstream:
            response=self.client.post('/api/providers/lux3d/import',headers=self.headers,json=self.body)
        self.assertEqual(response.status_code,409)
        upstream.assert_called_once()

    def test_completed_glb_streamed_as_same_origin_without_browser_cors(self):
        from unittest.mock import patch
        glb=b'glTF'+(2).to_bytes(4,'little')+(20).to_bytes(4,'little')+b'abcdefgh'
        with patch('backend.app.urllib.request.urlopen',return_value=_FakeLuxResponse(
                {'c':'0','d':{'status':3,'outputs':[{'content':'https://assets.aholo.ai/123.glb'}]}})),\
             patch('backend.app._download_lux_glb',return_value=glb) as download:
            response=self.client.post('/api/providers/lux3d/import',headers=self.headers,json=self.body)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True) if response.status_code!=200 else '')
        self.assertEqual(response.data,glb)
        self.assertEqual(response.mimetype,'model/gltf-binary')
        download.assert_called_once_with('https://assets.aholo.ai/123.glb')

    def test_unknown_task_cannot_forward_to_arbitrary_network(self):
        from unittest.mock import patch
        with patch('backend.app.urllib.request.urlopen',return_value=_FakeLuxResponse(
                {'c':'0','d':{'status':3,'outputs':[]}})),\
             patch('backend.app._download_lux_glb') as download:
            response=self.client.post('/api/providers/lux3d/import',headers=self.headers,json=self.body)
        self.assertEqual(response.status_code,404)
        download.assert_not_called()

    def test_zip_glb_extraction_and_forbidden_result_urls(self):
        from backend.app import _extract_lux_glb,_validate_lux_asset_url
        import io, zipfile
        glb=b'glTF'+(2).to_bytes(4,'little')+(20).to_bytes(4,'little')+b'abcdefgh'
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as z:z.writestr('safe/model.glb',glb)
        self.assertEqual(_extract_lux_glb(glb),glb)
        self.assertEqual(_extract_lux_glb(content.getvalue()),glb)
        with self.assertRaises(ValueError):_validate_lux_asset_url('https://127.0.0.1/internal.glb')
        with self.assertRaises(ValueError):_validate_lux_asset_url('https://not-approved.example/test.glb')
