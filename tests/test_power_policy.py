from pathlib import Path
import shutil
import subprocess
import pytest


def test_shutdown_policy_only_authorizes_admin_to_start_the_fixed_service():
    node = shutil.which('node')
    if not node: pytest.skip('Node is needed to evaluate the polkit rule')
    rule = Path(__file__).resolve().parents[1]/'deploy/49-eeye-shutdown.rules'
    script = '''
const vm=require('node:vm'),fs=require('node:fs');
let authorize;
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{
 polkit:{addRule:rule=>authorize=rule,Result:{YES:'yes'}}
});
function check(user,id,unit,verb){
 return authorize({id,lookup:key=>({unit,verb})[key]},{user});
}
const action='org.freedesktop.systemd1.manage-units',unit='eeye-shutdown.service';
if(check('admin',action,unit,'start')!=='yes')throw Error('Expected fixed shutdown permission');
for(const values of [
 ['other',action,unit,'start'],['admin',action,'sshd.service','start'],
 ['admin',action,unit,'stop'],['admin','org.freedesktop.systemd1.manage-unit-files',unit,'start']
])if(check(...values)==='yes')throw Error('Unexpected privilege granted');
'''
    subprocess.run([node, '-e', script, str(rule)], check=True, capture_output=True, timeout=10)
