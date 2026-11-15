'use strict';
'require baseclass';
'require ui';

const preferenceKey='lg6851f-slot-guide-read-v1';
const toolUrl='https://v6.gh-proxy.org/https://raw.githubusercontent.com/adian2020/openwrt-mt6990-lg6851f/1292a359d4a4f7312a5ab9cc9775d6d89cf46746/target/linux/mediatek/mt6990/base-files/usr/sbin/lg6851f-slotctl';
const toolHash='6f924a63b88564bb811e54f77da872ac85b9dca90bee1d7971020d8ef26c99cc';

function commands(current) {
 if(!['a','b'].includes(current))throw new Error('当前槽位必须为 A 或 B');
 const target=current==='a'?'b':'a';
 return `(
  set -e
  wget -O /tmp/lg6851f-slotctl.sh '${toolUrl}'
  [ "$(sha256sum /tmp/lg6851f-slotctl.sh | cut -d ' ' -f 1)" = '${toolHash}' ] || { echo '工具校验失败，未切槽'; exit 5; }
  slot_state="$(sh /tmp/lg6851f-slotctl.sh show)"
  printf '%s\\n' "$slot_state"
  [ "$(printf '%s' "$slot_state" | jsonfilter -e '@.current')" = '${current}' ] || { echo '当前不是 ${current.toUpperCase()} 槽，请选择正确的说明'; exit 95; }
  slot_token="$(printf '%s' "$slot_state" | jsonfilter -e '@.control')"
  sh /tmp/lg6851f-slotctl.sh select ${target} --expect "$slot_token" --confirm
  sh /tmp/lg6851f-slotctl.sh show
)
# 读回 code:0、current:"${current}"、next:"${target}" 后，再单独执行 reboot。`;
}

function injectCss() {
 if(document.getElementById('lg6851f-slot-guide-style'))return;
 const style=E('style',{id:'lg6851f-slot-guide-style'});
 style.textContent=`
.lg6851f-slot-guide-modal{width:900px!important;max-width:calc(100vw - 24px)!important}
.lg6851f-slot-guide-modal>h4,.lg6851f-slot-guide-warning{color:#e53935!important;font-size:22px!important;font-weight:700!important}
.lg6851f-slot-guide{min-width:0;line-height:1.65}
.lg6851f-slot-guide-section{margin:16px 0;padding:12px;border:1px solid var(--hairline,var(--border-color-low,#ccd2d8));border-radius:8px;min-width:0}
.lg6851f-slot-guide-section>h3{margin:0 0 8px;font-size:16px}
.lg6851f-slot-guide-code{margin:10px 0;padding:12px;max-width:100%;max-height:260px;overflow:auto;white-space:pre;background:var(--surface-sunken,var(--background-color-low,#f1f4f7));color:var(--text,var(--text-color-high,#263442));border-radius:6px;font-size:12px;line-height:1.6}
.lg6851f-slot-guide-copy-status{min-height:1.6em;margin:6px 0 0;overflow-wrap:anywhere}
.lg6851f-slot-guide-read{display:flex;align-items:center;gap:8px;margin:14px 0}
.lg6851f-slot-guide-read>input{flex:none;margin:0}
.lg6851f-slot-guide-footer{display:flex;justify-content:flex-end;margin-top:12px}
`;
 document.head.appendChild(style);
}

function shouldShow() {
 try{return localStorage.getItem(preferenceKey)!=='1';}catch(e){return true;}
}

async function copyCode(text,button,feedback) {
 button.disabled=true;
 let copied=false;
 try{
  if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(text);copied=true;}catch(e){}}
  // HTTP router pages usually lack Clipboard API. Keep the fallback inside
  // the current dialog so its focus management cannot steal the selection.
  if(!copied){
   const field=E('textarea',{'aria-label':'待复制的 SSH 命令',readonly:'readonly',style:'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;font-size:16px'});
   field.value=text;(button.closest('.lg6851f-slot-guide')||document.body).appendChild(field);
   try{field.focus();field.select();copied=!!document.execCommand('copy');}catch(e){}finally{field.remove();button.focus();}
  }
  button.textContent=copied?'已复制':'复制代码';
  feedback.textContent=copied?'命令已复制，请在对应原厂系统的 SSH 中粘贴执行。':'浏览器未允许复制，请长按或选中上方代码手动复制。';
 }finally{button.disabled=false;}
}

function content(withWarning) {
 injectCss();
 const root=E('div',{'class':'lg6851f-slot-guide'});
 if(withWarning)root.appendChild(E('h3',{'class':'lg6851f-slot-guide-warning'},'注意！！！'));
 root.appendChild(E('p',{},'适用于一个槽位使用 OpenWrt 固件、另一个槽位使用原厂固件，方便来回切换。本说明位于自编译固件中。切入原厂前，请保存必要备份和对应的 SSH 命令；进入原厂后，在 SSH 中执行对应命令，返回目标槽现有系统。'));
 root.appendChild(E('p',{},'根据原厂系统当前实际运行的槽位，选择对应的一组命令。代码只设置下次启动槽位，保留原厂失败保护；成功读回后，再单独执行 reboot。遇到报错先保留输出，不要直接重启。'));
 for(const current of ['a','b']){
  const target=current==='a'?'b':'a',text=commands(current),heading='原厂 '+current.toUpperCase()+' 槽 → 自编译 '+target.toUpperCase()+' 槽';
  const code=E('code');code.textContent=text;
  const feedback=E('p',{'class':'lg6851f-slot-guide-copy-status',role:'status','aria-live':'polite'});
  const button=E('button',{type:'button','class':'cbi-button cbi-button-action','aria-label':'复制'+heading+'命令'},'复制代码');
  button.addEventListener('click',()=>copyCode(text,button,feedback));
  root.appendChild(E('section',{'class':'lg6851f-slot-guide-section','data-current':current},[
   E('h3',{},heading),E('pre',{'class':'lg6851f-slot-guide-code'},code),button,feedback,
   E('p',{},'成功应显示 current:"'+current+'"、next:"'+target+'"。确认后在 SSH 中单独输入 reboot；重启后核对目标槽及固件。')
  ]));
 }
 return root;
}

function show() {
 const read=E('input',{type:'checkbox'});read.checked=!shouldShow();
 const close=()=>{
  let saved=true;
  try{if(read.checked)localStorage.setItem(preferenceKey,'1');else localStorage.removeItem(preferenceKey);}catch(e){saved=false;}
  ui.hideModal();
  if(!saved)ui.addNotification(null,E('p',{},'浏览器未能保存“不再显示”选项，下次可能仍会提示。'),'warning');
 };
 ui.showModal('注意！！！',[
  content(false),E('label',{'class':'lg6851f-slot-guide-read'},[read,' 已读，不再显示弹窗']),
  E('p',{},'此选择保存在当前浏览器；以后仍可点击“原厂固件切换说明”查看。'),
  E('div',{'class':'right lg6851f-slot-guide-footer'},E('button',{type:'button','class':'cbi-button cbi-button-action',click:close},'我已了解，关闭'))
 ],'lg6851f-slot-guide-modal');
}

return baseclass.extend({commands,content,show,shouldShow,preferenceKey});
