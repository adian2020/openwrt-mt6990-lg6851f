'use strict';
'require view';
'require ui';
'require modem5g.cpe_v1 as C';

return view.extend({
 load(){return C.getApn();},
 render(data){
  this.busy=false;
  const fields=[['apn','APN','text'],['iptype','IP 协议','select'],['auth','认证方式','select'],['username','用户名','text'],['password','新密码（留空保留）','password'],['mtu','MTU','number'],['auto_conf','SIM 自动配置 APN','select']];
  this.inputs={};const form=[];
  for(const[key,label,type]of fields){
   let input;
   if(type==='select'){
    const options=key==='iptype'?[[1,'IPv4'],[2,'IPv6'],[3,'IPv4/IPv6']]:key==='auth'?[[0,'无认证'],[1,'PAP'],[2,'CHAP'],[3,'PAP/CHAP']]:[[0,'关闭，使用手动 APN'],[1,'开启，允许 SIM 配置覆盖']];
    input=E('select',{},options.map(([value,text])=>E('option',{value,selected:+data[key]===value},text)));
   }else input=E('input',{type,value:key==='password'?'':data[key]??'',autocomplete:key==='password'?'new-password':'off',...(key==='mtu'?{min:576,max:1500}:{})});
   this.inputs[key]=input;form.push(E('label',{},label),input);
  }
  this.clearPassword=E('input',{type:'checkbox'});form.push(E('label',{},'清除已保存的密码'),this.clearPassword);
  const submit=async apply=>{
   if(this.busy)return;
   const values={};for(const[key,input]of Object.entries(this.inputs))values[key]=input.value;
   values.auto_conf=+values.auto_conf===1;values.clear_password=this.clearPassword.checked;
   const operation=async()=>{this.busy=true;try{return await C.saveApn(values,apply);}finally{this.busy=false;}};
   return C.action(apply?'保存并应用 APN':'仅保存 APN',apply?'会重建蜂窝数据连接，依赖蜂窝网络的客户端可能暂时断网。':'只保存配置，不立即重建数据连接。',operation);
  };
  return E('div',{'class':'cpe'},[C.style(),E('h2',{},'接入点 APN'),C.card('当前 MT6990 数据接口',C.rows([['协议',data.proto],['密码',data.password_set?'已设置（不回传）':'未设置']])),
   C.card('APN 配置',E('div',{'class':'cpe-form'},form)),E('div',{'class':'cpe-actions'},[
    E('button',{'class':'btn',disabled:data.proto!=='ql_datacall',click:()=>submit(false)},'仅保存'),
    E('button',{'class':'btn cbi-button-action',disabled:data.proto!=='ql_datacall',click:()=>submit(true)},'保存并应用')]),
   C.unavailable('本页写入现有 network.modem5g，不创建第二个蜂窝接口。开启 SIM 自动配置时，SIM/APN 数据库可能覆盖手动值。多配置及按 ICCID 绑定暂未接入，不显示无效切换按钮。')]);
 },handleSaveApply:null,handleSave:null,handleReset:null
});
