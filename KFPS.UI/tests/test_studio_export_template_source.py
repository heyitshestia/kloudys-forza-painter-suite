"""Export templates must come from a stable artwork/header snapshot."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_studio_offline_save_codec import NAMES, template_bytes
from kfps_livery_lab.export_service import ExportService
from tools.livery.fh6_save_installer import build_destination_header


class ExportTemplateSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.art = self.root/'C_livery'
        self.header = self.root/'header'
        self.art.write_bytes(template_bytes())
        self.header.write_bytes(build_destination_header(title='Fixture',creator_tag=b'TEST0001',
            creator_name='Fixture',car_id=4267,placement_count=11,now=datetime.now(timezone.utc)))
        self.vehicle = {'car_id':4267,'model_code':'test'}

    @contextmanager
    def mutate_after_read(self, watched, changed):
        original = Path.open
        class Reader:
            def __init__(self,stream): self.stream=stream
            def __enter__(self): self.stream.__enter__(); return self
            def __exit__(self,*args): return self.stream.__exit__(*args)
            def fileno(self): return self.stream.fileno()
            def read(self,*args):
                body=self.stream.read(*args)
                info=changed.stat()
                os.utime(changed,ns=(info.st_atime_ns,info.st_mtime_ns+1_000_000_000))
                return body
        def opened(path,mode='r',*args,**kwargs):
            stream=original(path,mode,*args,**kwargs)
            return Reader(stream) if path==watched and mode=='rb' else stream
        with patch.object(Path,'open',opened): yield

    def test_each_template_sibling_is_stable_across_both_reads(self):
        for watched,changed in ((self.art,self.header),(self.header,self.art)):
            with self.subTest(watched=watched.name), self.mutate_after_read(watched,changed):
                with self.assertRaisesRegex(ValueError,'changed'):
                    ExportService(self.art,self.vehicle,NAMES)

    def test_package_change_during_read_is_rejected(self):
        package=self.root/'fixture.kfpslivery'
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('source/fh6/C_livery',self.art.read_bytes())
            archive.writestr('source/fh6/header',self.header.read_bytes())
        with self.mutate_after_read(package,package):
            with self.assertRaisesRegex(ValueError,'changed'):
                ExportService(package,self.vehicle,NAMES)


if __name__=='__main__': unittest.main()
