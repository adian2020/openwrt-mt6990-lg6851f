#!/usr/bin/ucode
'use strict';
import { open, readfile, mkdtemp, rename, unlink, rmdir } from 'fs';
import { collect } from 'lg6851f.dashboard-collect';
let board=trim(readfile('/tmp/sysinfo/board_name')||'');
if(index(['fiberhome,lg6851f','fiberhome_lg6851f'],board)<0)exit(95);
let boot=trim(readfile('/proc/sys/kernel/random/boot_id')||'');
function publish(data,phase){
 let directory=mkdtemp('/tmp/lg6851f-dashboard.XXXXXX');
 if(!directory)die('Cannot create dashboard cache');
 let path=directory+'/frame', file=open(path,'wx',0o600);
 let output=sprintf('%J',{...data,boot_id:boot,collected_at:time(),collector_phase:phase});
 let ok=file&&file.write(output)==length(output)&&file.close()&&rename(path,'/tmp/lg6851f-dashboard-v2.json');
 unlink(path);rmdir(directory);
 if(!ok)die('Cannot publish dashboard cache');
}
collect(publish);
