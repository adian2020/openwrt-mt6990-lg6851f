'use strict';
'require view';
'require rpc';
'require ui';
'require modem5g.slot_guide_v1 as G';

const getSlots = rpc.declare({object:'luci.lg6851fslots',method:'get_boot_slots',nobatch:true,reject:true,expect:{}});
const selectSlot = rpc.declare({object:'luci.lg6851fslots',method:'select_boot_slot',params:['target','expected','confirm','allow_vendor_recovery'],nobatch:true,reject:true,expect:{}});
const reboot = rpc.declare({object:'system',method:'reboot',nobatch:true,reject:true});
function label(slot) { return slot==='a'?'A 槽':slot==='b'?'B 槽':'未确认'; }

return view.extend({
 handleSaveApply:null, handleSave:null, handleReset:null,
 load:function(){this.guidePrompted=false;return getSlots();},
 render:function(data){
  this.data=data;
  const content=E('div',{'class':'cbi-map','id':'lg6851f-slots'},[
   E('div',{style:'display:flex;align-items:center;gap:10px;flex-wrap:wrap'},[
    E('h2',{},'启动槽位'),E('button',{type:'button','class':'cbi-button',click:()=>G.show()},'原厂固件切换说明')
   ]),
   E('p',{},'设置默认启动槽，启动失败时仍保留原厂回退。此操作不刷写或复制系统镜像。')
  ]);
  if(!this.guidePrompted){
   this.guidePrompted=true;
   if(G.shouldShow())requestAnimationFrame(()=>{if(content.isConnected)G.show();});
  }
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
  const confirm=E('input',{'type':'checkbox'}),typed=E('input',{'type':'text','class':'cbi-input-text','placeholder':'请输入字母 '+target.toUpperCase(),'autocomplete':'off','autocapitalize':'characters'});
  const feedback=E('p',{'role':'status','aria-live':'polite','class':'lg6851f-slot-feedback','style':'min-height:1.6em;white-space:pre-wrap;overflow-wrap:anywhere'});
  const message=(text,error)=>{feedback.textContent=text;feedback.style.color=error?'var(--danger,#bd2838)':'var(--text,currentColor)';};
  let buttons=[],cancel,uncertain=false;
  const ready=()=>confirm.checked&&typed.value.trim().normalize('NFKC').toLowerCase()===target;
  const update=()=>{
   const valid=ready(),busy=!!this.selecting;
   buttons.forEach(button=>button.disabled=busy||uncertain||!valid);
   confirm.disabled=typed.disabled=busy;if(cancel)cancel.disabled=busy;
   if(!busy)message(uncertain?'上次请求结果未确认，请取消弹窗并刷新核对槽位。':!confirm.checked?'请先勾选备份与恢复风险确认。':!valid?'请在输入框填写目标槽字母 '+target.toUpperCase()+'。':'确认条件已满足，请选择“仅设置”或“设置并重启”。',uncertain);
  };
  confirm.addEventListener('change',update);typed.addEventListener('input',update);
  const run=async doReboot=>{
   if(this.selecting||uncertain)return;
   if(!ready()){update();return;}
   this.selecting=true;update();message('正在备份并设置目标槽位，请等待，勿重复提交。',false);
   try{
    // The server budgets 45s for backup/sync. Set the transport budget only
    // while dispatching this unbatched call, without extending other RPCs.
    const previous=L.env.rpctimeout;
    let request;
    try{L.env.rpctimeout=60;request=selectSlot(target,data.control,true,risk);}
    finally{L.env.rpctimeout=previous;}
    const result=await request;
    if(result.code){message('槽位设置未完成：'+(result.error||'错误码 '+result.code),true);return;}
    if(!/^[0-9a-f]{64}$/.test(result.control||'')||!result.backup){uncertain=true;message('槽位响应不完整，结果未确认；请取消弹窗后刷新核对，勿重复提交。',true);return;}
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
   }catch(e){uncertain=true;message('设置槽位请求未确认：'+(e.message||String(e))+'；请取消弹窗后刷新核对，勿重复提交。',true);}
   finally{this.selecting=false;buttons.forEach(button=>button.disabled=uncertain||!ready());confirm.disabled=typed.disabled=false;cancel.disabled=false;}
  };
  cancel=E('button',{'type':'button','class':'cbi-button','click':()=>ui.hideModal()},'取消');
  buttons=[E('button',{'type':'button','class':'cbi-button cbi-button-action','click':()=>run(false)},'仅设置'),E('button',{'type':'button','class':'cbi-button cbi-button-negative','click':()=>run(true)},'设置并重启')];
  update();
  ui.showModal('确认选择 '+label(target),[
   E('p',{},'当前 '+label(data.current)+' → 目标 '+label(target)),
   E('p',{},'设置后默认从该槽启动。该槽真实启动结果仍由引导器和系统决定，失败保护继续有效。'),
   E('p',{'class':'alert-message warning'},risk?'当前字段已满足原厂可能恢复另一槽的条件，进入原厂后可能覆盖另一槽镜像。':'目标原厂系统仍可能依据启动状态同步另一槽，建议保存两槽镜像。'),
   E('label',{'class':'cbi-value'},[confirm,' 我已保存必要备份，并理解原厂恢复可能覆盖另一槽']),
   E('p',{},'输入目标槽字母 '+target.toUpperCase()+'：'),typed,feedback,
   E('div',{'class':'right'},[cancel,...buttons])
  ]);
 }
});
