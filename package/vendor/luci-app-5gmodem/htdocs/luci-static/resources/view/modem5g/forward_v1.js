'use strict';
'require view';
'require rpc';
'require ui';
'require poll';
'require modem5g.cpe_v1 as C';

const getConfig=rpc.declare({object:'luci.modem5g',method:'get_forward_config',expect:{}});
const getStatus=rpc.declare({object:'luci.modem5g',method:'get_forward_status',expect:{}});
const saveConfig=rpc.declare({object:'luci.modem5g',method:'set_forward_config',params:['values'],expect:{}});
const testForward=rpc.declare({object:'luci.modem5g',method:'test_forward',expect:{}});
const retryForward=rpc.declare({object:'luci.modem5g',method:'retry_forward',expect:{}});
const states={idle:'等待服务启动',ready:'等待新增短信',disabled:'已关闭',sent:'已确认提交',retry:'等待重试',failed:'投递失败',uncertain:'结果未确认',inflight:'发送中',blocked:'已拦截',source_unavailable:'短信读取暂不可用',waiting_sim:'等待SIM就绪',invalid_config:'配置无效',storage_failed:'状态保存失败',storage_full:'去重记录已满'};
const presets={
 json:['https://example.com/sms',{from:'{from}',text:'{text}',time:'{time}',device:'{device}'}],
 wecom:['https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY',{msgtype:'text',text:{content:'短信来自 {from}\n{text}\n{time} · {device}'}}],
 dingtalk:['https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN',{msgtype:'text',text:{content:'短信来自 {from}\n{text}\n{time} · {device}'}}],
 telegram:['https://api.telegram.org/botYOUR_TOKEN/sendMessage',{chat_id:'YOUR_CHAT_ID',text:'短信来自 {from}\n{text}\n{time} · {device}'}],
 bark:['https://api.day.app/push',{device_key:'YOUR_KEY',title:'短信来自 {from}',body:'{text}\n{time} · {device}',group:'LG6851F'}],
 pushplus:['https://www.pushplus.plus/send',{token:'YOUR_TOKEN',title:'短信来自 {from}',content:'{text}\n{time} · {device}',template:'txt'}]
};
return view.extend({
 load(){return getConfig();},
 render(data){
  if(data.code)throw Error(data.error||'无法读取短信转发配置');
  const values=data.values||{},fields={};
  const input=(name,type='text')=>fields[name]=E('input',{id:'fwd-'+name,type,value:values[name]??'',...(type==='password'?{autocomplete:'new-password'}:{})});
  const toggle=name=>fields[name]=E('input',{id:'fwd-'+name,type:'checkbox',checked:!!values[name]});
  const select=(name,choices)=>fields[name]=E('select',{id:'fwd-'+name},choices.map(([value,label])=>E('option',{value,selected:value===values[name]},label)));
  const field=(label,element)=>[E('label',{for:element.id},label),element];
  const textarea=(name,rows)=>fields[name]=E('textarea',{id:'fwd-'+name,rows,value:values[name]||'',style:'width:100%;max-width:100%;min-width:0;font-family:monospace'},values[name]||'');
  const card=(title,rows)=>C.card(title,E('div',{class:'cpe-form'},rows.flat()));
  const status=E('div',{id:'fwd-status'});
  const paint=result=>{
   status.replaceChildren(C.rows([['服务',result.enabled===false?'已关闭':states[result.state]||result.state||'等待启动'],['最近说明',result.message||'暂无投递'],['最近投递',result.last_at?new Date(result.last_at*1000).toLocaleString():'暂无']]));
   const names={webhook:'Webhook',smtp:'邮件',sms:'手机短信'};
   if(result.results)status.append(C.table(['渠道','结果','时间'],Object.entries(result.results).map(([key,item])=>[names[key]||key,states[item.state]||item.state,item.at?new Date(item.at*1000).toLocaleString():'—'])));
  };
  paint({...data.status,enabled:values.enabled});
  poll.add(async()=>paint(await getStatus()),10);
  const provider=select('provider',[['json','通用JSON Webhook'],['wecom','企业微信机器人'],['dingtalk','钉钉机器人'],['telegram','Telegram'],['bark','Bark'],['pushplus','PushPlus']]);
  const applyPreset=E('button',{class:'btn',click:()=>{const preset=presets[provider.value];fields.url.value=preset[0];fields.body.value=JSON.stringify(preset[1],null,2);}},'填入模板');
  const collect=()=>Object.fromEntries(Object.entries(fields).map(([key,node])=>[key,node.type==='checkbox'?node.checked:node.value]));
  const execute=async(button,action)=>{button.disabled=true;try{const result=await action();if(result.code)throw Error(result.error||result.output||'操作失败');ui.addNotification(null,E('p',{},result.output),'info');paint(await getStatus());}catch(error){ui.addNotification(null,E('p',{},error.message),'error');}finally{button.disabled=false;}};
  const save=E('button',{class:'btn cbi-button-positive',click:event=>execute(event.currentTarget,async()=>{const previous=L.env.rpctimeout;try{L.env.rpctimeout=90;return await saveConfig(collect());}finally{L.env.rpctimeout=previous;}})},'保存并应用');
  const test=E('button',{class:'btn cbi-button-action',click:event=>execute(event.currentTarget,testForward)},'发送测试（使用已保存配置）');
  const retry=E('button',{class:'btn',click:()=>C.action('重试失败或未确认的投递','将重新投递失败或结果未确认的短信。请先核对接收端，避免重复收到。',retryForward,async()=>paint(await getStatus()))},'重试失败投递');
  return E('div',{class:'cpe'},[C.style(),E('h2',{},'短信转发'),
   C.unavailable('可同时启用多种渠道。首次启用或保存配置后，以已有短信建立基线，仅转发之后新增的完整短信；不自动删除收件箱短信。'),
   card('服务与过滤',[field('启用自动转发',toggle('enabled')),field('采集间隔（30–600秒）',input('interval','number')),field('号码黑名单（英文逗号分隔）',input('blocked')),field('仅转发包含关键词（留空为全部）',input('keyword'))]),
   card('Webhook',[field('启用Webhook',toggle('webhook')),field('推送类型',provider),field('预设',applyPreset),field('目标URL',input('url','url')),field('JSON消息模板',textarea('body',8))]),
   C.unavailable('模板字段：{from} 发件人、{text} 正文、{time} 时间、{device} 设备名。模板中的 YOUR_KEY、YOUR_TOKEN 和 YOUR_CHAT_ID 需替换为你的值。钉钉当前支持不启用加签的机器人接口。'),
   card('邮件 SMTP',[field('启用邮件',toggle('smtp')),field('服务器',input('host')),field('端口',input('port','number')),field('加密方式',select('tls',[['tls','TLS（通常465）'],['starttls','STARTTLS（通常587）']])),field('登录用户名',input('username')),field(values.password_set?'密码／授权码（留空保留）':'密码／授权码',input('password','password')),field('清除已保存密码',toggle('clear_password')),field('发件邮箱',input('from','email')),field('收件邮箱',input('to','email'))]),
   card('转发到另一部手机',[field('启用手机短信',toggle('sms')),field('目标手机号',input('phone','tel'))]),
   C.unavailable('手机渠道通过当前SIM发送，按运营商规则计费。中文按UTF-16编码发送，长内容拆分为带序号的独立短信，每条原短信最多20段；不会转发回原发件人。'),
   E('div',{class:'cpe-actions'},[save,test,retry]),
   C.unavailable('测试会向所有已保存且启用的渠道实际投递，并在下一个采集周期执行。网络连接失败最多自动重试5次；结果不确定时等待人工核对，不自动重复发送。'),
   C.card('投递状态',status)
  ]);
 },handleSaveApply:null,handleSave:null,handleReset:null
});
