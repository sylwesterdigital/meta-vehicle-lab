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
                         'modules':{'front':{}},'occupants':0}}
        response=self.client.post('/api/me/layouts',headers=member_headers,json=data)
        self.assertEqual(response.status_code,201,response.json)
        self.assertEqual(self.client.get('/api/me/layouts/'+id,headers=second_headers).status_code,404)
        self.assertEqual(self.client.get('/api/gallery').json['layouts'],[])
        data['visibility']='public';data['revision']=1
        self.assertEqual(self.client.put('/api/me/layouts/'+id,headers=member_headers,json=data).status_code,200)
        self.assertEqual(len(self.client.get('/api/gallery').json['layouts']),1)
        self.assertEqual(self.client.get('/api/gallery/'+id).json['layout']['name'],'My custom car')
        self.assertEqual(self.client.get('/api/admin/logs',headers=member_headers).status_code,401)
        self.assertEqual(self.client.get('/api/admin/logs',headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/me/layouts',headers={**member_headers,
            'Origin':'https://attacker.invalid'},json=data).status_code,403)
        self.assertEqual(self.client.post('/api/providers/test',headers=member_headers,
            json={'provider':'tripo','key':'some-secret'}).status_code,422)

if __name__=='__main__':unittest.main()
