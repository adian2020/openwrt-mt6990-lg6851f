#!/usr/bin/ucode
'use strict';
import { open, readfile, mkdtemp, rename, unlink, rmdir } from 'fs';
import { collect } from 'lg6851f.dashboard-collect';
let board=trim(readfile('/tmp/sysinfo/board_name')||'');
if(index(['fiberhome,lg6851f','fiberhome_lg6851f'],board)<0)exit(95);
let previous=null;try{previous=json(readfile('/tmp/lg6851f-dashboard-v2.json')||'null');}catch(e){}
let boot=trim(readfile('/proc/sys/kernel/random/boot_id')||'');
if(previous?.boot_id!=boot)previous=null;
function publish(data,phase){
 // 每个中间帧都保留尚未采集的上一组数据，避免轮询读到半成品。
 let merged={...(previous||{}),...data};
 for(let k in ['wireless','clients','leases','storage','network','lan','ipv6_global'])if(data[k]==null && previous?.[k]!=null)merged[k]=previous[k];
 data=merged;
 let directory=mkdtemp('/tmp/lg6851f-dashboard.XXXXXX');
 if(!directory)die('Cannot create dashboard cache');
 let path=directory+'/frame', file=open(path,'wx',0o600);
 let output=sprintf('%J',{...data,boot_id:boot,collected_at:time(),collector_phase:phase});
 let ok=file&&file.write(output)==length(output)&&file.close()&&rename(path,'/tmp/lg6851f-dashboard-v2.json');
 unlink(path);rmdir(directory);
 if(!ok)die('Cannot publish dashboard cache');
}
collect(publish);
