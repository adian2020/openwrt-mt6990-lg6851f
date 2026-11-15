'use strict';
'require view';
'require rpc';
'require ui';

const getSlots = rpc.declare({object:'luci.modem5g',method:'get_boot_slots',expect:{}});
const selectSlot = rpc.declare({object:'luci.modem5g',method:'select_boot_slot',params:['target','expected','confirm','allow_vendor_recovery'],expect:{}});
const reboot = rpc.declare({object:'system',method:'reboot'});
function label(slot) { return slot==='a'?'A 槽':slot==='b'?'B 槽':'未确认'; }

return view.extend({
 handleSaveApply:null, handleSave:null, handleReset:null,
 load:function(){return getSlots();},
 render:function(data){
  this.data=data;
  const content=E('div',{'class':'cbi-map','id':'lg6851f-slots'},[
   E('h2',{},'启动槽位'),
   E('p',{},'设置默认启动槽，启动失败时仍保留原厂回退。此操作不刷写或复制系统镜像。')
  ]);
  if(data.code || !data.slots){content.appendChild(E('p',{'class':'alert-message error'},data.error||'无法读取槽位'));return content;}
  content.appendChild(E('p',{},'当前实际启动：'+label(data.current)+'；下次启动偏好：'+label(data.next)));
  const table=E('table',{'class':'table'},[
   E('tr',{'class':'tr table-titles'},['槽位','优先级','重试计数','成功字段','升级状态','镜像头'].map(t=>E('th',{'class':'th'},t)))
  ]);
  ['a','b'].forEach(slot=>{
   const s=data.slots[slot];
   table.appendChild(E('tr',{'class':'tr'},[label(slot),s.priority,s.retry,s.success,s.upgrade,s.image_headers_ok?'已识别':'无效或无法读取'].map(t=>E('td',{'class':'td'},String(t)))));
  });
  content.appendChild(table);
  content.appendChild(E('p',{},'成功字段是原厂持久记录，不代表本次启动已经通过健康检查。'));
  content.appendChild(E('p',{'class':'alert-message warning'},'镜像头检查不能证明签名有效、boot/rootfs 配套或系统一定能启动。进入原厂系统后，原厂服务可能恢复并覆盖另一槽。请先保存两槽镜像备份。'));
  const buttons=E('div',{'class':'cbi-page-actions'});
  const target=data.current==='a'?'b':data.current==='b'?'a':null;
  const denied=!L.hasViewPermission(),invalid=!target||!data.slots[target]?.image_headers_ok;
  // LuCI E() calls setAttribute(): even disabled="false" disables a button.
  buttons.appendChild(E('button',{'type':'button','class':'cbi-button cbi-button-action','disabled':denied||invalid?true:null,'click':ui.createHandlerFn(this,()=>this.confirmSlot(target))},target?'切换到 '+label(target):'当前槽位未确认'));
  if(denied||invalid)content.appendChild(E('p',{'class':'alert-message warning'},denied?'当前会话没有启动槽位写权限，请使用有权限的账户重新登录。':'实际槽位或目标镜像头未确认，暂不允许切换。'));
  content.appendChild(E('p',{},'按实际运行槽位选择另一槽：A → B、B → A；不假定哪个槽运行原厂或 6.18。普通重启保留默认槽，原厂在线升级的交替写入是另一条流程。'));
  buttons.appendChild(E('button',{'type':'button','class':'cbi-button','click':ui.createHandlerFn(this,()=>this.refresh(true))},'刷新状态'));
  content.appendChild(buttons);
  content.appendChild(E('h3',{},'保护机制说明'));
  content.appendChild(E('p',{},'本机前级先检查旧计数：当前槽大于 3、另一槽不大于 3 且异常检查允许时回退；特定复位路径随后才递增。原厂 Linux 还可能复制恢复另一槽，这与切槽是不同阶段。重试计数不是内核错误码。'));
  return content;
 },
 refresh:async function(notify){
  try{
   const data=await getSlots();
   if(data.code||!data.slots)throw new Error(data.error||'无法读取槽位');
   const node=this.render(data);document.querySelector('#lg6851f-slots').replaceWith(node);
   if(notify)ui.addNotification(null,E('p',{},'槽位状态已刷新；当前实际启动：'+label(data.current)+'，下次启动偏好：'+label(data.next)),'info');
  }catch(e){ui.addNotification(null,E('p',{},'刷新槽位失败：'+(e.message||String(e))),'error');}
 },
 confirmSlot:function(target){
  const data=this.data;
  if(!L.hasViewPermission()){ui.addNotification(null,E('p',{},'当前会话没有启动槽位写权限'),'warning');return;}
  if(!['a','b'].includes(data.current)||!['a','b'].includes(target)||target===data.current){ui.addNotification(null,E('p',{},'请先确认实际运行槽位，再选择另一槽'),'warning');return;}
  const s=data.slots[target],other=data.slots[data.current];
  if(!s?.image_headers_ok){ui.addNotification(null,E('p',{},'目标镜像头未确认，未设置槽位'),'warning');return;}
  const risk=other.retry>3||s.success!==1;
  const confirm=E('input',{'type':'checkbox'}),typed=E('input',{'type':'text','class':'cbi-input-text','placeholder':target.toUpperCase()});
  const run=async doReboot=>{
   if(this.selecting)return;
   if(!confirm.checked||typed.value.trim().toLowerCase()!==target){ui.addNotification(null,E('p',{},'请确认备份与恢复风险，并输入目标槽字母'),'warning');return;}
   this.selecting=true;
   try{
    const result=await selectSlot(target,data.control,true,risk);
    if(result.code){ui.addNotification(null,E('p',{},result.error||'槽位设置失败'),'error');return;}
    ui.hideModal();
    if(doReboot){
     ui.showModal('正在重启',[E('p',{'class':'spinning'},'目标已设置为 '+label(target)+'，正在重启…')]);
     try {
      const check=await getSlots();
      if(check.code||check.control!==result.control||check.next!==target){ui.hideModal();ui.addNotification(null,E('p',{},'启动记录已再次变化，未发送重启，请刷新后核查'),'warning');return;}
      await reboot();ui.awaitReconnect(window.location.host);
     } catch(e) {ui.hideModal();ui.addNotification(null,E('p',{},'槽位已设置，但重启请求未确认，请检查设备状态'),'warning');}
    }else{
     ui.addNotification(null,E('p',{},'已设置 '+label(target)+'，未重启。控制记录备份：'+result.backup),'info');await this.refresh();
    }
   }catch(e){ui.addNotification(null,E('p',{},'设置槽位请求未确认：'+(e.message||String(e))+'；请先刷新核对槽位状态。'),'error');}
   finally{this.selecting=false;}
  };
  ui.showModal('确认选择 '+label(target),[
   E('p',{},'当前 '+label(data.current)+' → 目标 '+label(target)),
   E('p',{},'设置后默认从该槽启动。该槽真实启动结果仍由引导器和系统决定，失败保护继续有效。'),
   E('p',{'class':'alert-message warning'},risk?'当前字段已满足原厂可能恢复另一槽的条件，进入原厂后可能覆盖另一槽镜像。':'目标原厂系统仍可能依据启动状态同步另一槽，建议保存两槽镜像。'),
   E('label',{'class':'cbi-value'},[confirm,' 我已保存必要备份，并理解原厂恢复可能覆盖另一槽']),
   E('p',{},'输入目标槽字母 '+target.toUpperCase()+'：'),typed,
   E('div',{'class':'right'},[
    E('button',{'type':'button','class':'cbi-button','click':()=>ui.hideModal()},'取消'),
    E('button',{'type':'button','class':'cbi-button cbi-button-action','click':ui.createHandlerFn(this,()=>run(false))},'仅设置'),
    E('button',{'type':'button','class':'cbi-button cbi-button-negative','click':ui.createHandlerFn(this,()=>run(true))},'设置并重启')
   ])
  ]);
 }
});
