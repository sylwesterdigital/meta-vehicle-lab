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
