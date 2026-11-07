#!/usr/bin/ucode
import {cursor} from 'uci';
import * as apn from 'lg6851f.apn';
let c=cursor(),identity={iccid:getenv('LG6851F_APN_ICCID'),imsi:getenv('LG6851F_APN_IMSI')};
let count=0;c.foreach('lg6851f_apn','selection',s=>{count++;});
if(!count){printf('%J',{ok:1,source:'network'});exit(0);}
if(!apn.valid_identity(identity)){printf('%J',{ok:0,error:'apn_identity'});exit(1);}
let base=apn.from_network(c.get_all('network','modem5g') || {}),r=apn.resolve(c,identity,base);
if(r.ok && r.source!='network')r.settings={apn:r.settings.apn,iptype:r.settings.pdptype=='IP'?1:3,
 roamingtype:r.settings.roaming=='IP'?1:3,auth:index(['none','pap','chap','papchap'],r.settings.auth),
 username:r.settings.username,password:r.settings.password,attach:r.settings.attach};
printf('%J',r);exit(r.ok?0:1);
