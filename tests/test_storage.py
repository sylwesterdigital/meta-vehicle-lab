"""SQLite regressions run without downloading any Python dependencies."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from backend.storage import InvalidLayout, StaleLayout, Storage


def blueprint():
    return {'schema':'procedural-vehicle/v3','vehicle':{'name':'City Car'},'modules':{'front':{},'cabin':{},'rear':{}},'occupants':2}

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Storage(self.tmp.name)

    def test_create_read_update_and_delete(self):
        ident=str(uuid.uuid4())
        result=self.store.save_layout(identifier=ident,name='  Commuter  ',blueprint=blueprint())
        self.assertEqual(result['name'],'Commuter')
        self.assertEqual(result['revision'],1)
        self.assertEqual(self.store.get_layout(ident)['blueprint']['occupants'],2)
        self.assertEqual(len(self.store.list_layouts()),1)
        updated=blueprint();updated['occupants']=3
        changed=self.store.save_layout(identifier=ident,name='Commuter',blueprint=updated,revision=1)
        self.assertEqual(changed['revision'],2)
        self.assertEqual(self.store.get_layout(ident)['blueprint']['occupants'],3)
        with self.assertRaises(StaleLayout):
            self.store.save_layout(identifier=ident,name='Bad',blueprint=blueprint(),revision=1)
        with self.assertRaises(StaleLayout):self.store.delete_layout(ident,1)
        self.assertTrue(self.store.delete_layout(ident,2))
        self.assertIsNone(self.store.get_layout(ident))

    def test_block_credentials_and_bad_blueprints(self):
        data=blueprint()
        data['vehicle']['api_key']='SHOULD_NOT_STORE'
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier=str(uuid.uuid4()),name='x',blueprint=data)
        data=blueprint();data['vehicle']['key']={'nested':float('nan')}
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier=str(uuid.uuid4()),name='x',blueprint=data)
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier='../oops',name='x',blueprint=blueprint())

    def test_preview_gallery_privacy_and_size_limits(self):
        profile,secret=self.store.create_guest('Preview Maker')
        image='data:image/jpeg;base64,'+'QQAA'*150
        data=blueprint()
        data['metadata']={'category':'Urban','description':'One-of-a-kind electric car',
                          'images':[{'label':'Hero','data':image}]}
        ident=str(uuid.uuid4())
        self.store.user_save_layout(profile['id'],ident,'Hidden',data,visibility='private')
        self.assertEqual(self.store.gallery(),[])
        self.store.user_save_layout(profile['id'],ident,'Shared',data,visibility='public',revision=1)
        item=self.store.gallery()[0]
        self.assertEqual(item['preview'],image)
        self.assertEqual(item['category'],'Urban')
        self.assertNotIn('blueprint',item)
        self.assertNotIn('profile_id',item)
        self.assertNotIn(secret,str(item))
        invalid=blueprint();invalid['metadata']={'images':[{'data':'a'*280000}]}
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier=str(uuid.uuid4()),name='Oversize',blueprint=invalid)

    def test_custom_course_and_transparent_preview_roundtrip(self):
        data=blueprint()
        data['vehicle'].update({'frontRake':0.75,'rearRake':0.35,'roofWidth':0.73,
             'doorStyle':'gullwing','courseObjects':[{'kind':'jump','x':2.0,'z':14.0,
             'w':5.0,'d':7.0,'h':2.5}]})
        transparent='data:image/png;base64,'+'AAAABBBB'*60
        data['metadata']={'category':'Urban','images':[{'label':'Hero','data':transparent}]}
        profile,_=self.store.create_guest('Studio Preview')
        ident=str(uuid.uuid4())
        self.store.user_save_layout(profile['id'],ident,'Aerodynamic Concept',data,visibility='public')
        restored=self.store.gallery_layout(ident)
        self.assertEqual(restored['blueprint']['vehicle']['doorStyle'],'gullwing')
        self.assertEqual(restored['blueprint']['vehicle']['courseObjects'][0]['kind'],'jump')
        self.assertEqual(self.store.gallery()[0]['preview'],transparent)

    def test_no_asset_outside_store(self):
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier=str(uuid.uuid4()),name='x',blueprint=blueprint(),asset_id=str(uuid.uuid4()))

    def test_guest_profiles_and_private_public_gallery(self):
        import uuid
        store=self.store
        profile,secret=store.create_guest('Build Tester')
        self.assertNotIn(secret,str(profile))
        self.assertEqual(store.identity(secret)['id'],profile['id'])
        self.assertIsNone(store.identity(secret+'x'))
        other,other_secret=store.create_guest('Another Visitor')
        profile=store.update_profile(profile['id'],{'name':'Builder','bio':'3D work',
            'links':{'website':'https://example.com'},'email':'someone@example.com','phone':''})
        self.assertEqual(profile['name'],'Builder')
        ident=str(uuid.uuid4())
        payload={'schema':'procedural-vehicle/v3','vehicle':{'name':'City Car'},
                 'modules':{'front':{}},'occupants':1}
        entry=store.user_save_layout(profile['id'],ident,'Private car',payload)
        self.assertEqual(entry['visibility'],'private')
        self.assertFalse(store.gallery())
        self.assertIsNone(store.own_layout(other['id'],ident))
        with self.assertRaises(Exception):
            store.user_save_layout(other['id'],ident,'Hijack',payload,revision=1)
        public=store.user_save_layout(profile['id'],ident,'Public car',payload,
                                      visibility='public',revision=1)
        self.assertEqual(public['revision'],2)
        self.assertEqual(store.gallery()[0]['creator_name'],'Builder')
        self.assertNotIn('someone@example.com',str(store.gallery()))
        self.assertTrue(store.gallery_layout(ident))
        with self.assertRaises(StaleLayout):
            store.user_save_layout(profile['id'],ident,'Stale',payload,revision=1)
        self.assertTrue(store.user_delete_layout(profile['id'],ident,2))
        self.assertFalse(store.gallery())

if __name__=='__main__':unittest.main()

# Direct image normalization tests run without Flask; Pillow is pinned in the
# production requirements and exercised by this release's deployment gate.
class Lux3dReferenceImageTests(unittest.TestCase):
    @staticmethod
    def data_url(image, fmt):
        import base64, io
        buffer=io.BytesIO()
        image.save(buffer,format=fmt)
        mime={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[fmt]
        return 'data:'+mime+';base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')

    def test_small_image_is_not_changed(self):
        from PIL import Image
        from backend.storage import prepare_lux_reference
        original=self.data_url(Image.new('RGB',(150,90),'#acc4dd'),'PNG')
        result,info=prepare_lux_reference(original)
        self.assertEqual(result,original)
        self.assertFalse(info['optimized'])
        self.assertEqual((info['width'],info['height']),(150,90))

    def test_generated_large_png_optimizes_under_provider_limit(self):
        import base64,io,random
        from PIL import Image
        from backend.storage import prepare_lux_reference
        rng=random.Random(17)
        raw=rng.randbytes(1400*1200*3)
        original=self.data_url(Image.frombytes('RGB',(1400,1200),raw),'PNG')
        self.assertGreater(len(original),2*1024*1024)
        result,info=prepare_lux_reference(original)
        self.assertTrue(info['optimized'])
        self.assertLessEqual(len(result),2*1024*1024-4096)
        mime,encoded=result.split(',',1)
        decoded=Image.open(io.BytesIO(base64.b64decode(encoded)))
        self.assertEqual(decoded.format,'JPEG')
        self.assertLessEqual(decoded.width,1400)
        self.assertLessEqual(decoded.height,1200)

    def test_large_transparent_png_preserves_alpha_if_webp_available(self):
        import random
        from PIL import Image,features
        from backend.storage import prepare_lux_reference
        if not features.check('webp'):self.skipTest('WebP not installed in Pillow')
        rng=random.Random(25)
        original=self.data_url(Image.frombytes('RGBA',(1300,1000),rng.randbytes(1300*1000*4)),'PNG')
        self.assertGreater(len(original),2*1024*1024)
        result,info=prepare_lux_reference(original)
        self.assertTrue(info['optimized'])
        self.assertEqual(info['format'],'image/webp')
        self.assertLess(len(result),2*1024*1024)

    def test_bad_mime_and_untrusted_base64_rejected(self):
        from PIL import Image
        from backend.storage import prepare_lux_reference
        png=self.data_url(Image.new('RGB',(3,3)),'PNG')
        with self.assertRaisesRegex(ValueError,'MIME'):
            prepare_lux_reference(png.replace('data:image/png','data:image/jpeg'))
        with self.assertRaisesRegex(ValueError,'base64'):
            prepare_lux_reference('data:image/png;base64,!notimage')
        with self.assertRaisesRegex(ValueError,'maximum 20 MiB'):
            prepare_lux_reference('data:image/png;base64,'+'A'*(21*1024*1024))

class UserMediaTests(unittest.TestCase):
    """Private maps/images must never leak across profile identities."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Storage(self.tmp.name)
        self.first,self.first_token=self.store.create_guest('World Builder')
        self.second,self.second_token=self.store.create_guest('Observer')

    def test_private_map_roundtrip_and_owner_isolation(self):
        import json
        doc={'schema':'vehiclelab-testmap/v3','name':'Nine cells',
             'edge':'cells','worldCells':{'0,0':{'elevation':2},'1,0':{'elevation':5}},
             'objects':[{'kind':'bridge','x':1,'z':8,'w':6,'h':2,'d':9}]}
        item=self.store.save_media(self.first['id'],'map','Nine-cell Playground',
                                   json.dumps(doc).encode(),'application/json')
        self.assertEqual(len(self.store.own_media_list(self.first['id'],'map')),1)
        self.assertEqual(self.store.own_media_list(self.second['id']),[])
        self.assertIsNone(self.store.own_media(self.second['id'],item['id']))
        stored=self.store.own_media(self.first['id'],item['id'])
        self.assertEqual(json.loads(stored['payload'])['worldCells']['1,0']['elevation'],5)
        self.assertFalse(self.store.delete_media(self.second['id'],item['id']))
        self.assertTrue(self.store.delete_media(self.first['id'],item['id']))
        self.assertIsNone(self.store.own_media(self.first['id'],item['id']))

    def test_media_limits_and_invalid_schema(self):
        with self.assertRaises(InvalidLayout):
            self.store.save_media(self.first['id'],'map','Invalid',b'{"schema":"wrong","objects":[]}',
                                  'application/json')
        with self.assertRaises(InvalidLayout):
            self.store.save_media(self.first['id'],'image','Big picture',b'0'*(2*1024*1024+1),'image/jpeg')
        record=self.store.save_media(self.first['id'],'image','Mock JPEG',b'JPEG test bytes','image/jpeg')
        self.assertEqual(self.store.own_media(self.first['id'],record['id'])['mime'],'image/jpeg')
        self.assertIsNone(self.store.own_media(self.second['id'],record['id']))
