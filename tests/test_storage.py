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

    def test_no_asset_outside_store(self):
        with self.assertRaises(InvalidLayout):
            self.store.save_layout(identifier=str(uuid.uuid4()),name='x',blueprint=blueprint(),asset_id=str(uuid.uuid4()))

if __name__=='__main__':unittest.main()
