"""真实 ubusd + 固定 ucode 的隔离测试，只读写临时假网卡和账本。"""
import pwd,json,os,pathlib,subprocess,tempfile,time,unittest,shutil
ROOT=pathlib.Path(__file__).resolve().parents[2]
UCODE=os.environ.get('UCODE') or shutil.which('ucode')
UBUS=os.environ.get('LG6851F_TEST_UBUS')
UBUSD=os.environ.get('LG6851F_TEST_UBUSD')
@unittest.skipUnless(UCODE and UBUS and UBUSD,'需要本机隔离 ubus/ubusd')
class TrafficServiceTest(unittest.TestCase):
 def test_persistence_clear_failure_and_counter_recreation(self):
  with tempfile.TemporaryDirectory(prefix='lg6851f-traffic-test-') as name:
   root=pathlib.Path(name);disk=root/'disk';ram=root/'ram';net=root/'net';disk.mkdir();ram.mkdir();(net/'fake0/statistics').mkdir(parents=True)
   def counter(rx,tx,idx=31):
    for file,val in [('statistics/rx_bytes',rx),('statistics/tx_bytes',tx),('ifindex',idx)]: (net/'fake0'/file).write_text(str(val))
   counter(1000,500)
   seed={'version':1,'revision':0,'config':{'plan_name':'测试套餐','monthly_gb':100,'daily_gb':1,'reset_day':15,'count_mode':'total','device':'fake0'},'started_at':int(time.time()),'last':None,'days':{},'months':{},'pending_rx':0,'pending_tx':0,'adjustment':None,'totals':{'rx':0,'tx':0}}
   (disk/'state.json').write_text(json.dumps(seed))
   socket=str(root/'ubus.sock');env=dict(os.environ,LG6851F_TRAFFIC_DIR=str(disk),LG6851F_TRAFFIC_RUN=str(ram),LG6851F_TRAFFIC_SYS=str(net),LG6851F_TRAFFIC_SOCKET=socket,LG6851F_TRAFFIC_BUS='lg6851f.traffic.test')
   acl=root/'acl';acl.mkdir();(acl/'test.json').write_text(json.dumps({'user':pwd.getpwuid(os.getuid()).pw_name,'publish':['lg6851f.traffic.test'],'access':{'lg6851f.traffic.test':{'methods':['*']}}}))
   log=open(root/'service.log','w+');bus=subprocess.Popen([UBUSD,'-A',str(acl),'-s',socket],env=env,stdout=log,stderr=log);worker=None
   def call(method,args=None):
    r=subprocess.run([UBUS,'-s',socket,'-t','2','call','lg6851f.traffic.test',method,json.dumps(args or {})],env=env,capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr);return json.loads(r.stdout)
   def start():
    args=[UCODE,'-L',os.environ['UCODE_LIBRARY'],'-L',str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/share/ucode'),str(ROOT/'package/vendor/luci-app-5gmodem/root/usr/libexec/lg6851f-traffic.uc')]
    p=subprocess.Popen(args,env=env,stdout=log,stderr=log)
    for _ in range(100):
     r=subprocess.run([UBUS,'-s',socket,'list','lg6851f.traffic.test'],env=env,capture_output=True,text=True)
     if 'lg6851f.traffic.test' in r.stdout:return p
     if p.poll() is not None:log.flush();self.fail((root/'service.log').read_text())
     time.sleep(.03)
    p.terminate();p.wait(5);self.fail('隔离服务注册超时')
   try:
    for _ in range(100):
     if pathlib.Path(socket).exists():break
     time.sleep(.02)
    worker=start();self.assertEqual(call('get')['status']['totals'],{'rx':0,'tx':0})
    counter(1100,550);call('flush');self.assertEqual(call('get')['status']['totals'],{'rx':100,'tx':50})
    old=(disk/'state.json').read_bytes();self.assertEqual(call('clear')['error'],'confirmation_required');self.assertEqual((disk/'state.json').read_bytes(),old)
    (disk/'state.json.new').mkdir();self.assertEqual(call('clear',{'confirm':True})['error'],'storage_failed');self.assertEqual(call('get')['status']['totals']['rx'],100);self.assertEqual((disk/'state.json').read_bytes(),old);(disk/'state.json.new').rmdir()
    (ram/'state.json.new').mkdir();self.assertTrue(call('clear',{'confirm':True})['ok']);self.assertTrue(call('get')['status']['storage_error']);self.assertEqual(call('get')['config']['plan_name'],'测试套餐')
    worker.terminate();worker.wait(5);worker=None;(ram/'state.json.new').rmdir();worker=start()
    self.assertEqual(call('get')['status']['totals']['rx'],0)
    counter(1150,570);call('flush');self.assertEqual(call('get')['status']['totals'],{'rx':50,'tx':20})
    worker.terminate();worker.wait(5);worker=None;worker=start();self.assertEqual(call('get')['status']['totals'],{'rx':50,'tx':20})
    counter(7,3,32);call('flush');self.assertEqual(call('get')['status']['totals'],{'rx':57,'tx':23})
    self.assertEqual(json.loads((ram/'view.json').read_text())['totals'],call('get')['status']['totals'])
    self.assertEqual(call('get',{'slot':1})['error'],'invalid_sim')
   finally:
    if worker and worker.poll() is None:worker.terminate();worker.wait(5)
    bus.terminate();bus.wait(5);log.close()
if __name__=='__main__':unittest.main()
