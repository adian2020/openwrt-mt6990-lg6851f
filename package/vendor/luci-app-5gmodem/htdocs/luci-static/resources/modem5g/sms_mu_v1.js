'use strict';
'require baseclass';
'require rpc';
'require ui';
'require modem5g.mu_v1 as U';
// MU300 presentation adapter. LG6851F remains single-SIM and uses qlril/atcid.
var call=function(method,params){return rpc.declare({object:'luci.modem5g',method:method,params:params||[],nobatch:true,expect:{'':{}}});};
var get=call('get_forward_config'),set=call('set_forward_config',['values']),status=call('get_forward_status'),job=call('sms_pool_job');
function publicStatus(s){return Object.assign({},s,{power_supported:false,last_result:s.state,history:s.history||[]});}
function getForward(){return get().then(function(r){
 if(!r.values)return {error:r.error||'读取配置失败'};
 var c=r.values;
 return {profile:'shared',mode:'shared',sim_slots:1,status:publicStatus(r.status||{}),config:Object.assign({},c,{
  channel_webhook:!!c.webhook,channel_smtp:!!c.smtp,channel_sms:!!c.sms,
  webhook_url:c.url,webhook_body:c.body,webhook_expect:c.webhook_expect||({wecom:'errcode=0',dingtalk:'errcode=0',telegram:'ok=true',bark:'code=200',pushplus:'code=200'})[c.provider]||'',
  sms_to_phone:c.phone,blacklist_phone:(c.blocked||'').split(',').join('\n'),
  dingtalk_secret_configured:c.dingtalk_secret_set,
  smtp:{host:c.host,port:String(c.port),username:c.username,to:c.to,password_configured:c.password_set},power_forward_enabled:false
 })};
});}
function setForward(payload){
 var p=JSON.parse(payload),v={enabled:!!p.enabled,webhook:!!p.channel_webhook,smtp:!!p.channel_smtp,sms:!!p.channel_sms,
  url:p.webhook_url,body:p.webhook_body||'{"from":"{from}","text":"{text}","time":"{time}","device":"{device}"}',provider:'json',
  phone:p.sms_to_phone,blocked:p.blacklist_phone.split('\n').join(','),
  host:p.smtp_host,port:+p.smtp_port,username:p.smtp_username,from:p.smtp_from||p.smtp_username,to:p.smtp_to,password:p.smtp_password,
  tls:p.smtp_port==='587'?'starttls':'tls',clear_password:!!p.clear_smtp_password};
 ['method','webhook_kind','template_language','webhook_method','webhook_content_type','webhook_timeout','webhook_headers','webhook_expect',
  'dingtalk_webhook','dingtalk_secret','clear_dingtalk_secret','dingtalk_forward_device_info','smtp_forward_device_info','sms_forward_device_info','blacklist_keywords','nickname','interval','keyword'].forEach(function(k){if(p[k]!=null)v[k]=p[k];});
 return set(v).then(function(r){return {ok:r.code===0,error:r.error};});
}
function choiceBox(title,text,choices){return new Promise(function(resolve){
 var done=false,finish=function(value){if(done)return;done=true;document.removeEventListener('keydown',escape);ui.hideModal();resolve(value);},escape=function(e){if(e.key==='Escape')finish(null);};
 document.addEventListener('keydown',escape);
 ui.showModal(title,[E('p',{},text),E('div',{'class':'right'},choices.map(function(c){return E('button',{'class':'btn'+(c.danger?' cbi-button-negative':''),click:function(){finish(c.value);}},c.label);}))]);
});}
var del=call('sms_pool_delete',['id','sim']);
function deleteMessage(id,sim){return del(id,!!sim).then(function(r){
 if(!r.ok||!r.job)return r;
 var started=Date.now();return new Promise(function(resolve,reject){
  function tick(){job().then(function(j){if(j.id!==r.job)return resolve({ok:false,error:'任务已变化，请刷新核对'});if(!j.running)return resolve(j);if(Date.now()-started>650000)return resolve({ok:false,error:'任务超时，请刷新核对'});setTimeout(tick,1000);},reject);}tick();
 });
});}
return baseclass.extend({
 injectCss:U.injectCss,esc:U.esc,confirmBox:U.confirmBox,toast:U.toast,busy:U.busy,choiceBox:choiceBox,
 translate:function(s){return s;},localize:function(){},localizeMenu:function(){},simSelector:function(){},selectedSlot:function(){return 0;},watchSms:function(){},uiLanguage:function(){return 'zh';},
 callSmsList:call('sms_pool_list',['page']),callSmsShow:call('sms_pool_show',['id']),callSmsSend:call('sms_pool_send',['number','text']),callSmsJob:job,callSmsSync:call('sms_pool_sync'),callSmsDel:deleteMessage,
 callForwardGet:getForward,callForwardSet:setForward,callForwardStatus:function(){return status().then(function(s){return {status:publicStatus(s)};});},
 callForwardTest:function(){return call('test_forward')().then(function(r){return {ok:r.code===0,error:r.error};});},
 callForwardClear:function(){return call('clear_forward_history')().then(function(r){return {ok:r.code===0,error:r.error};});},
 callForwardRetry:function(){return call('retry_forward')().then(function(r){return {ok:r.code===0,error:r.error};});}
});
