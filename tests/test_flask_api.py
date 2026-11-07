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

if __name__=='__main__':unittest.main()
