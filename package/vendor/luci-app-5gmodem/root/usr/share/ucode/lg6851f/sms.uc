'use strict';
import { sha256 } from 'digest';

// Pure framing and identifiers. The actual modem is still owned by atcid/qlril.
export function number(value) { return type(value)=='string' && !!match(value,/^\+?[0-9]{3,20}$/); }
export function id(sim,message) { return 'm-'+sha256(sprintf('%J',[sim,message.dir||'mt',message.from,message.time,message.text])); }
export function valid_id(value) { return type(value)=='string'&&!!match(value,/^m-[0-9a-f]{64}$/); }
export function display_time(value) {
 let m=match(value||'',/^([0-9]{2})\/([0-9]{2})\/([0-9]{2}),([0-9:]{8})/);
 return m?'20'+m[1]+'-'+m[2]+'-'+m[3]+' '+m[4]:value;
}
export function preview(value) {
 let text=replace(value||'',/[\r\n\t]+/g,' '),end=min(132,length(text));
 while(end>0 && end<length(text) && (ord(text,end)&0xc0)==0x80)end--;
 return substr(text,0,end);
}
export function utf16(value) {
 if(type(value)!='string'||length(value)>8192)return null;
 let units=[];
 for(let i=0;i<length(value);i++){
  let c=ord(value,i),n=c<128?0:c>=0xc2&&c<=0xdf?1:c>=0xe0&&c<=0xef?2:c>=0xf0&&c<=0xf4?3:-1;
  if(n<0||i+n>=length(value))return null;
  let code=n==0?c:c&((1<<(6-n))-1);
  for(let j=1;j<=n;j++){let b=ord(value,i+j);if(b<128||b>191)return null;code=code*64+(b&63);}
  if(code==0||(n==1&&code<128)||(n==2&&code<2048)||(n==3&&code<65536)||code>0x10ffff||(code>=0xd800&&code<=0xdfff))return null;
  i+=n;push(units,code>0xffff?sprintf('%04X%04X',0xd800+((code-0x10000)>>10),0xdc00+((code-0x10000)&1023)):sprintf('%04X',code));
 }
 return units;
}
export function outgoing(value) {
 if(type(value)!='string'||!length(value))return {error:'短信内容不能为空'};
 if(length(value)<=160&&match(value,/^[ -~]+$/))return {encoding:'ascii',parts:[value]};
 let units=utf16(value);if(!units)return {error:'短信编码无效或内容过长'};
 let all=join('',units);if(length(all)<=280)return {encoding:'ucs2',parts:[all]};
 let parts=[],part='';
 for(let unit in units){if(length(part)+length(unit)>240){push(parts,part);part='';}part+=unit;}
 if(length(part))push(parts,part);
 if(length(parts)>20)return {error:'短信超过20段，请缩短内容'};
 for(let i=0;i<length(parts);i++){
  let label='['+(i+1)+'/'+length(parts)+'] ',prefix='';
  for(let j=0;j<length(label);j++)prefix+=sprintf('%04X',ord(label,j));
  parts[i]=prefix+parts[i];
 }
 return {encoding:'ucs2',parts};
}

function unhex(value) {
 let out='';for(let i=0;i<length(value);i+=2)out+=chr(int(substr(value,i,2),16));return out;
}
export function hmac256(key,message) {
 if(length(key)>64)key=unhex(sha256(key));
 let inner='',outer='';
 for(let i=0;i<64;i++){let b=i<length(key)?ord(key,i):0;inner+=chr(b^0x36);outer+=chr(b^0x5c);}
 return unhex(sha256(outer+unhex(sha256(inner+message))));
}
export function urlencode(value) {
 let out='';for(let i=0;i<length(value);i++){let c=substr(value,i,1);out+=match(c,/[A-Za-z0-9_.~-]/)?c:sprintf('%%%02X',ord(value,i));}return out;
}
