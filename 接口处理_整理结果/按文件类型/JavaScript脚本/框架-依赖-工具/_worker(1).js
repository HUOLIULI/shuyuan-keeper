// _worker.js  —  ysp-live · Cloudflare Pages 版
// 央视频全频道 M3U 直播 + 置顶固定分组 + 动态 302 重定向
// 路径: /live.m3u   /play/{slug}

const DOMAIN = "https://jsnz.pages.dev";                 // 你的 Pages 域名
const LOGO   = "https://jsnz.pages.dev/f/5ab7e916.gif";  // 分组图标

// ------------------------------------------------------------------
// 1. 频道表 (slug, 显示名, sid, pid, defn, 分组)
// ------------------------------------------------------------------
const CHANNELS = [
  // ---- 央视 ----
  ["cctv1","CCTV-1","2024078201","600001859","fhd","cctv"],
  ["cctv2","CCTV-2","2024075401","600001800","fhd","cctv"],
  ["cctv3","CCTV-3","2024068501","600001801","fhd","cctv"],
  ["cctv4","CCTV-4","2029797101","600001814","fhd","cctv"],
  ["cctv5","CCTV-5","2024078401","600001818","fhd","cctv"],
  ["cctv5p","CCTV-5+","2024078001","600001817","fhd","cctv"],
  ["cctv6","CCTV-6","2013693901","600108442","fhd","cctv"],
  ["cctv7","CCTV-7","2024072001","600004092","fhd","cctv"],
  ["cctv8","CCTV-8","2029793001","600001803","fhd","cctv"],
  ["cctv9","CCTV-9","2024078601","600004078","fhd","cctv"],
  ["cctv10","CCTV-10","2024078701","600001805","fhd","cctv"],
  ["cctv11","CCTV-11","2027248701","600001806","fhd","cctv"],
  ["cctv12","CCTV-12","2027248801","600001807","fhd","cctv"],
  ["cctv13","CCTV-13","2029797201","600001811","fhd","cctv"],
  ["cctv14","CCTV-14","2027248901","600001809","fhd","cctv"],
  ["cctv15","CCTV-15","2027249001","600001815","fhd","cctv"],
  ["cctv16","CCTV-16","2027249101","600098637","fhd","cctv"],
  ["cctv164k","CCTV-16 4K","2027249301","600099502","fhd","4k"],
  ["cctv17","CCTV-17","2027249401","600001810","fhd","cctv"],
  ["cctv4k","CCTV-4K","2029810301","600002264","fhd","4k"],
  ["cctv8k","CCTV-8K","2026774101","600156816","fhd","4k"],
  // ---- CGTN ----
  ["cgtn","CGTN","2024181701","600014550","fhd","cgtn"],
  ["cgtnfr","CGTN法语","2024181801","600084704","fhd","cgtn"],
  ["cgtnru","CGTN俄语","2024181901","600084758","fhd","cgtn"],
  ["cgtnar","CGTN阿拉伯语","2024182001","600084782","fhd","cgtn"],
  ["cgtnes","CGTN西班牙语","2024182101","600084744","fhd","cgtn"],
  ["cgtndoc","CGTN 纪录","2024182301","600084781","fhd","cgtn"],
  // ---- 付费剧场 ----
  ["cctvfyjc","CCTV 风云剧场","2025637103","600099658","shd","premium"],
  ["cctvdyjc","CCTV 第一剧场","2026874203","600099655","shd","premium"],
  ["cctvhjjc","CCTV 怀旧剧场","2026874303","600099620","shd","premium"],
  // ---- 卫视 ----
  ["bjws","北京卫视","2024052703","600002309","fhd","satellite"],
  ["jsws","江苏卫视","2024171103","600002521","fhd","satellite"],
  ["dfws","东方卫视","2024054503","600002483","fhd","satellite"],
  ["zjws","浙江卫视","2024054703","600002520","fhd","satellite"],
  ["hnws","湖南卫视","2024054803","600002475","fhd","satellite"],
  ["hbws","湖北卫视","2024171203","600002508","fhd","satellite"],
  ["gdws","广东卫视","2024060903","600002485","fhd","satellite"],
  ["gxws","广西卫视","2024060703","600002509","fhd","satellite"],
  ["hljws","黑龙江卫视","2029797003","600002498","fhd","satellite"],
  ["hainanws","海南卫视","2024055603","600002506","fhd","satellite"],
  ["cqws","重庆卫视","2024061103","600002531","fhd","satellite"],
  ["szws","深圳卫视","2024061303","600002481","fhd","satellite"],
  ["scws","四川卫视","2024061403","600002516","fhd","satellite"],
  ["henanws","河南卫视","2029797303","600002525","fhd","satellite"],
  ["dnws","东南卫视","2024061503","600002484","fhd","satellite"],
  ["gzws","贵州卫视","2024061603","600002490","fhd","satellite"],
  ["jxws","江西卫视","2024061703","600002503","fhd","satellite"],
  ["lnws","辽宁卫视","2024171303","600002505","fhd","satellite"],
  ["ahws","安徽卫视","2024171403","600002532","fhd","satellite"],
  ["hebws","河北卫视","2024171503","600002493","fhd","satellite"],
  ["sdws","山东卫视","2029787903","600002513","fhd","satellite"],
  ["tjws","天津卫视","2019927003","600152137","fhd","satellite"],
  ["jlws","吉林卫视","2025561503","600190405","fhd","satellite"],
  ["saxws","陕西卫视","2029795103","600190400","fhd","satellite"],
  ["nxws","宁夏卫视","2025608503","600190737","fhd","satellite"],
  ["nmgws","内蒙古卫视","2025561203","600190401","fhd","satellite"],
  ["ynws","云南卫视","2025561303","600190402","fhd","satellite"],
  ["shanxiws","山西卫视","2025560803","600190407","fhd","satellite"],
  ["qhws","青海卫视","2025559103","600190406","fhd","satellite"],
  ["xizangws","西藏卫视","2025558003","600190403","fhd","satellite"],
  ["xjws","新疆卫视","2019927403","600152138","fhd","satellite"],
  ["cetv1","CETV-1","2022823801","600171827","fhd","satellite"],
  // ---- 其他 ----
  ["guoxue","国学频道","2029360403","600213139","fhd","other"],
];

// 分组定义（顺序即 M3U 中分组出现顺序）
const GROUPS = [
  { id:"top",       name:"✈️TG频道@stymei", logo:LOGO },
  { id:"cctv",      name:"央视频道",        logo:LOGO },
  { id:"satellite", name:"卫视频道",        logo:LOGO },
  { id:"cgtn",      name:"CGTN",           logo:LOGO },
  { id:"4k",        name:"4K超清",          logo:LOGO },
  { id:"premium",   name:"付费剧场",        logo:LOGO },
  { id:"other",     name:"其他",            logo:LOGO },
];

// 置顶固定分组内容
const TOP_CHANNEL = {
  name: "☁️官网地址jsnzkpg.com",
  url:  "https://tymov2.a.kwimgs.com/upic/2026/08/15/09/BMjAyNjA4MTUwOTE2MzRfNDI0MDI5NTBfMjA1NjA5Mjg4OTg3XzFfMw==_b_B664d90218f70be73e07dd3cf02d473f1.mp4",
};

// 已知 JCE 坏域名频道 → 直接走 bkliveinfo
const FORCE_BK = new Set([
  "cctv11","cctv12","cctv14","cctv15","cctv16","cctv164k",
  "cctv17","cctv4k","cctvfyjc","cctvdyjc","cctvhjjc",
]);

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";

// ------------------------------------------------------------------
// 2. JCE 二进制协议 (精简移植)
// ------------------------------------------------------------------
const VER_NAME="3.2.7.26212", VER_CODE="302070";
const APP_ID="1200013", QMF_APP_ID=10012, QMF_PLATFORM=1, BIZ_ID=0;
const CHAN_ID="10070";
let GUID = randHex(32);
const WINDOW = 300;

function randHex(n){
  const c="0123456789abcdef"; let s="";
  for(let i=0;i<n;i++) s+=c[Math.floor(Math.random()*16)];
  return s;
}

class W {
  constructor(){ this.b=[]; }
  _head(t,tag){
    if(tag<15) this.b.push(((tag&0xf)<<4)|(t&0xf));
    else { this.b.push(0xf0|(t&0xf)); this.b.push(tag); }
  }
  byte(v,tag){ v=int32(v); if(v===0) this._head(12,tag); else { this._head(0,tag); this.b.push(v&0xff); } }
  short(v,tag){ v=int32(v); if(v>=-128&&v<=127) this.byte(v,tag); else { this._head(1,tag); this._push16(v); } }
  int(v,tag){ v=int32(v); if(v>=-32768&&v<=32767) this.short(v,tag); else { this._head(2,tag); this._push32(v); } }
  long(v,tag){ v=int32(v); if(v>=-2147483648&&v<=2147483647) this.int(v,tag); else { this._head(3,tag); this._push64(v); } }
  string(s,tag){
    if(s===null||s===undefined) return;
    const d=new TextEncoder().encode(String(s));
    if(d.length>255){ this._head(7,tag); this._push32(d.length); d.forEach(x=>this.b.push(x)); }
    else { this._head(6,tag); this.b.push(d.length); d.forEach(x=>this.b.push(x)); }
  }
  bytes(data,tag){
    this._head(13,tag); this._head(0,0); this.int(data.length,0);
    for(const x of data) this.b.push(x);
  }
  struct(fn,tag){ this._head(10,tag); fn(this); this._head(11,0); }
  list(items,tag){ this._head(9,tag); this.int(items.length,0); }
  _push16(v){ this.b.push((v>>8)&0xff, v&0xff); }
  _push32(v){ this.b.push((v>>>24)&0xff,(v>>>16)&0xff,(v>>>8)&0xff,v&0xff); }
  _push64(v){
    const hi=Math.floor(v/0x100000000), lo=v>>>0;
    this._push32(hi); this._push32(lo);
  }
  out(){ return new Uint8Array(this.b); }
}

function int32(v){ v=Number(v); return (v|0); }

// ---- 解码器（只用于取 playurl）----
class R {
  constructor(data){ this.d=data; this.p=0; }
  rem(){ return this.d.length-this.p; }
  get(n){ const b=this.d.slice(this.p,this.p+n); this.p+=n; return b; }
  u8(){ return this.d[this.p++]; }
  head(){ let b=this.u8(); let t=b&0xf; let tag=(b&0xf0)>>4; if(tag===15) tag=this.u8(); return [t,tag]; }
  value(t){
    switch(t){
      case 0: return new DataView(this.get(1).buffer).getInt8(0);
      case 1: return new DataView(this.get(2).buffer).getInt16(0);
      case 2: return new DataView(this.get(4).buffer).getInt32(0);
      case 3: { const b=this.get(8); const dv=new DataView(b.buffer); return Number(dv.getBigInt64(0)); }
      case 6: { const n=this.u8(); return new TextDecoder().decode(this.get(n)); }
      case 7: { const n=new DataView(this.get(4).buffer).getInt32(0); return new TextDecoder().decode(this.get(n)); }
      case 9: { const n=this._int(); const a=[]; for(let i=0;i<n;i++) a.push(this._fv()); return a; }
      case 10: return this.struct();
      case 11: return null;
      case 12: return 0;
      case 13: { this.head(); const n=this._int(); return this.get(n); }
      default: throw new Error("type "+t);
    }
  }
  _fv(){ const [t]=this.head(); return this.value(t); }
  _int(){ const [t]=this.head(); return int32(this.value(t)); }
  struct(){ const m={}; while(this.rem()>0){ const [t,tag]=this.head(); if(t===11) break; m[tag]=this.value(t); } return m; }
}

function jceHead(w,cmd,reqid){
  w.int(reqid,0); w.int(cmd,1);
  w.struct(ww=>{
    ww.string(VER_NAME,0); ww.string(VER_CODE,1);
    ww.int(1080,2); ww.int(2400,3); ww.int(3,4); ww.string("12",5);
    ww.int(1,6); ww.int(1,7); ww.int(420,8); ww.string(CHAN_ID,9);
    for(let i=10;i<15;i++) ww.string("",i);
    ww.struct(x=>{x.int(0,0);x.byte(0,1);x.string("",2);},15);
    ww.string("",16); ww.string("",17); ww.string("",18);
    ww.struct(x=>{x.int(0,0);x.float(0,1);x.float(0,2);x.double(0,3);},19);
    ww.string(GUID.slice(0,16),20); ww.string("Pixel 6",21);
    ww.int(1,22);
    for(let i=23;i<27;i++) ww.int(0,i);
    ww.string("",27); ww.string("",28); ww.string(GUID,29);
  },2);
  w.string(APP_ID,3); w.string(GUID,4);
  w.list([],5); w.struct(()=>{},6);
  w.list([],7);
  w.int(0,8); w.int(0,9); w.int(0,10);
}

function jceWrap(cmd, body, reqid){
  const w=new W();
  w.struct(ww=>jceHead(ww,cmd,reqid),0);
  w.bytes(body,1);
  const reqcmd=w.out();
  const inner=new Uint8Array(1+4+1+10+reqcmd.length+1);
  inner[0]=38; new DataView(inner.buffer).setInt32(1,reqcmd.length+17);
  inner[5]=1; inner.set(reqcmd,16); inner[inner.length-1]=40;
  const comp=gzipSync(inner);
  const out=new Uint8Array(33+comp.length+4+32+1+4+6+1+2+2+4+comp.length);
  const dv=new DataView(out.buffer);
  out[0]=19; dv.setInt32(1,0); dv.setUint16(5,2); dv.setUint16(7,65281);
  dv.setUint16(9,cmd); dv.setUint16(11,0);
  dv.setBigInt64(13,BigInt(reqid));
  dv.setInt32(21,531); dv.setInt32(25,QMF_APP_ID);
  dv.setBigInt64(29,BigInt(BIZ_ID));
  const gb=new TextEncoder().encode(GUID.slice(0,32));
  out.set(gb,37);
  dv.setInt8(69,QMF_PLATFORM); dv.setInt32(70,parseInt(VER_CODE));
  // 空位后面全 0，data 段
  let off=89+32+0;
  // 简化：直接拼出完整包（保持与原 python 一致，偏移略有差异但服务端以 length 头为准）
  // 由于复杂度，这里用更直接的拼装（见下方 buildJcePacket）
  return buildJcePacket(cmd, reqid, comp, inner.length);
}

function buildJcePacket(cmd, reqid, comp, innerLen){
  const headLen = 37 + 32 + 1 + 4 + 6;   // 到 vercode 为止
  const total = headLen + 1 + 2 + 2 + 4 + comp.length + 1;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  out[0]=19;
  dv.setInt32(1, total);
  dv.setUint16(5, 2);
  dv.setUint16(7, 65281);
  dv.setUint16(9, cmd);
  dv.setUint16(11, 0);
  dv.setBigInt64(13, BigInt(reqid));
  dv.setInt32(21, 531);
  dv.setInt32(25, QMF_APP_ID);
  dv.setBigInt64(29, BigInt(BIZ_ID));
  const gb = new TextEncoder().encode(GUID.slice(0,32));
  out.set(gb, 37);
  let p = 37 + 32;
  out[p++] = QMF_PLATFORM & 0xff;
  dv.setInt32(p, parseInt(VER_CODE)); p += 4;
  p += 6;                     // 6 个 0
  out[p++] = 0;               // 1 个 0
  dv.setUint16(p, 0); p += 2;
  dv.setUint16(p, 0); p += 2;
  dv.setInt32(p, innerLen); p += 4;
  out.set(comp, p); p += comp.length;
  out[p++] = 3;
  return out;
}

function jceUnwrap(data){
  if(data.length<90 || data[0]!==0x13) return null;
  const flags = new DataView(data.buffer, data.byteOffset).getInt32(21);
  let payload = data.slice(89, data.length-1);
  if(flags & 2) payload = gunzipSync(payload);
  if(payload[0]!==0x26 || payload[payload.length-1]!==0x28) return null;
  const rc = new R(payload.slice(16, payload.length-1)).struct();
  return rc[1] || new Uint8Array(0);
}

async function jceTimeshiftUrl(pid, sid, start, end, stream){
  const w = new W();
  w.string(pid,0); w.string(sid,1); w.long(start,2); w.long(end,3); w.string(stream,4);
  const body = w.out();
  const CMD = 25312;
  const reqid = (Date.now() % 0x7fffffff) | 0;
  const packet = buildJcePacket(CMD, reqid, gzipSync(packJceInner(CMD, reqid, body)), 0);
  // 重新精确构建（覆盖上面的粗略处理）
  const pkt = buildJceFullPacket(CMD, reqid, body);
  const resp = await fetch("https://jacc.ysp.cctv.cn", {
    method:"POST",
    headers:{"Content-Type":"application/octet-stream"},
    body: pkt,
  });
  const raw = new Uint8Array(await resp.arrayBuffer());
  const respBody = jceUnwrap(raw);
  if(!respBody) throw new Error("bad response");
  const m = new R(respBody).struct();
  const err = m[0] || 0;
  if(err!==0) throw new Error("errCode="+err);
  let url = m[2] || "";
  if(url.includes("liverecord.video.cloud.cctv.com")) throw new Error("DEAD_HOST");
  return url;
}

function packJceInner(cmd, reqid, body){
  const w = new W();
  w.struct(ww=>jceHead(ww,cmd,reqid),0);
  w.bytes(body,1);
  const reqcmd = w.out();
  const inner = new Uint8Array(1+4+1+10+reqcmd.length+1);
  inner[0]=38; new DataView(inner.buffer).setInt32(1, reqcmd.length+17);
  inner[5]=1; inner.set(reqcmd,16); inner[inner.length-1]=40;
  return inner;
}

function buildJceFullPacket(cmd, reqid, body){
  const inner = packJceInner(cmd, reqid, body);
  const comp = gzipSync(inner);
  return buildJcePacket(cmd, reqid, comp, inner.length);
}

// ------------------------------------------------------------------
// 3. cKey + bkliveinfo (备用协议)
// ------------------------------------------------------------------
const CK_PLATFORM = 4330403;
const CK_APPVER   = "V8.22.1035.3031";
const CK_TEA  = hexToBytes("59b2f7cf725ef43c34fdd7c123411ed3");
const CK_GTEA = hexToBytes("110DBEC10C23E7D2E56A1CAD6914EF1B");
const CK_XOR  = new Uint8Array([0x84,0x2e,0xed,0x08,0xf0,0x66,0xe6,0xea,0x48,0xb4,0xca,0xa9,0x91,0xed,0x6f,0xf3]);
const CK_GXOR = new Uint8Array([0xb3,0xc9,0x53,0xa0,0x69,0x13,0xad,0x4d]);

function hexToBytes(h){ const a=new Uint8Array(h.length/2); for(let i=0;i<a.length;i++) a[i]=parseInt(h.substr(i*2,2),16); return a; }

function u32(v){ return v>>>0; }

function teaBlk(blk, key){
  const dv = new DataView(blk.buffer);
  let y = dv.getUint32(0), z = dv.getUint32(4);
  const kd = new DataView(key.buffer);
  const k0=kd.getUint32(0), k1=kd.getUint32(4), k2=kd.getUint32(8), k3=kd.getUint32(12);
  let s = 0;
  for(let i=0;i<16;i++){
    s = u32(s + 0x9e3779b9);
    y = u32(y + u32(u32(u32(z<<4) + k0) ^ u32(z+s) ^ u32((z>>>5) + k1)));
    z = u32(z + u32(u32(u32(y<<4) + k2) ^ u32(y+s) ^ u32((y>>>5) + k3)));
  }
  const out = new Uint8Array(8);
  new DataView(out.buffer).setUint32(0,y);
  new DataView(out.buffer).setUint32(4,z);
  return out;
}

function cksum(buf){ let v=0; for(const b of buf) v=(0x83*v+b)&0x7fffffff; return v; }

function teaPkt(data, key){
  const pad = (8 - ((data.length+10)%8))%8;
  const rnd = new Uint8Array(1+pad+2);
  crypto.getRandomValues(rnd);
  const plain = new Uint8Array(1+pad+2+data.length+7);
  plain[0] = (rnd[0]&0xf8)|pad;
  plain.set(rnd.slice(1),1);
  plain.set(data, 1+pad+2);
  let pp = new Uint8Array(8), pc = new Uint8Array(8);
  const out = new Uint8Array(plain.length);
  for(let off=0; off<plain.length; off+=8){
    const mixed = new Uint8Array(8);
    for(let i=0;i<8;i++) mixed[i] = plain[off+i]^pc[i];
    const enc = teaBlk(mixed, key);
    const cipher = new Uint8Array(8);
    for(let i=0;i<8;i++) cipher[i] = enc[i]^pp[i];
    out.set(cipher, off);
    pp = mixed; pc = cipher;
  }
  return out;
}

function lp(s){ const d=new TextEncoder().encode(s); const o=new Uint8Array(2+d.length); new DataView(o.buffer).setUint16(0,d.length); o.set(d,2); return o; }

function ckGuard(ts, guid){
  const tail = v => { const t=String(v); return t.length>=5?t.slice(-5):""; };
  const parts = [new Uint8Array(4), lp(tail(guid)), lp(tail("null")), lp(tail("null")), lp("-1")];
  new DataView(parts[0].buffer).setUint32(0, ts);
  const body = concatBytes(...parts);
  const plain = lp(body);
  const enc0 = teaPkt(plain, CK_GTEA);
  const sum = new Uint8Array(4); new DataView(sum.buffer).setUint32(0, cksum(plain));
  const enc = concatBytes(enc0, sum);
  for(let i=0;i<enc.length;i++) enc[i] ^= CK_GXOR[i&7];
  return bytesToHex(enc).toUpperCase();
}

function concatBytes(...arrs){
  const n = arrs.reduce((a,b)=>a+b.length,0);
  const o = new Uint8Array(n); let p=0;
  for(const a of arrs){ o.set(a,p); p+=a.length; }
  return o;
}
function bytesToHex(b){ let s=""; for(const x of b) s+=x.toString(16).padStart(2,"0"); return s; }

function ckey(channelId){
  const ts = Math.floor(Date.now()/1000);
  const guid = randHex(16);
  const guard = ckGuard(ts, guid);
  const uid = randHex(4).toUpperCase();
  const appver = new TextEncoder().encode(CK_APPVER);
  const bodyParts = [
    hexToBytes("0000004200000004000004d2"),
    u32be(CK_PLATFORM), u32be(0), u32be(ts),
    lp("dcgh"), lp("_zj1A5Gh6QYcxWjIUGos2w=="), lp(CK_APPVER), lp(String(channelId)),
    lp(guid), u32be(1), u32be(1), lp(uid), lp("nil"),
    lp("57eab0c4-2c58-44c6-8ae9-dd2757525dc5"), lp("nil"), lp("v0.1.000"),
    lp("com.cctv.yangshipin.app.iphone"), lp(String(CK_PLATFORM)),
    lp("ex_json_bus"), lp("ex_json_vs"), lp(guard),
  ];
  const body = concatBytes(...bodyParts);
  const pkt = new Uint8Array(2 + body.length);
  new DataView(pkt.buffer).setUint16(0, body.length);
  pkt.set(body, 2);
  new DataView(pkt.buffer).setUint32(18, cksum(pkt));
  const enc0 = teaPkt(pkt, CK_TEA);
  const sum = new Uint8Array(4); new DataView(sum.buffer).setUint32(0, cksum(pkt));
  const enc = concatBytes(enc0, sum);
  for(let i=0;i<enc.length;i++) enc[i] ^= CK_XOR[i&15];
  const b64 = btoa(String.fromCharCode(...enc)).replace(/\+/g,"_").replace(/\//g,"-").replace(/=+$/,"");
  return { cKey:"--01"+b64, guid, ts,
           flowId: randHex(32).toUpperCase()+"_"+CK_PLATFORM };
}

function u32be(v){ const b=new Uint8Array(4); new DataView(b.buffer).setUint32(0,v>>>0); return b; }

const BK_H264 = btoa("H(30:1080,60:1080|30:1080,60:1080)");

async function bkPlayUrls(channelId, livePid, defn){
  const t = ckey(channelId);
  const params = {
    atime:"120", livepid:livePid, cnlid:channelId,
    appVer:CK_APPVER, app_version:"300090", caplv:"1", cmd:"2",
    defn:defn, device:"iPhone", encryptVer:"4.2", getpreviewinfo:"0",
    hevclv:"0", lang:"zh-Hans_CN", livequeue:"0", logintype:"1",
    nettype:"1", newnettype:"1", newplatform:String(CK_PLATFORM),
    platform:String(CK_PLATFORM), sdtfrom:"v3021", spacode:"23",
    spaudio:"1", spdemuxer:"6", spdrm:"2", spdynamicrange:"1",
    spflv:"1", spflvaudio:"1", sphdrfps:"60", sphttps:"1",
    spvcode:BK_H264, spvideo:"4", stream:"1", system:"1",
    sysver:"ios18.2.1", uhd_flag:"0", cKey:t.cKey, guid:t.guid,
    fntick:String(t.ts), flowid:t.flowId, playbacktime:"0",
  };
  const qs = new URLSearchParams(params).toString();
  const resp = await fetch("https://bkliveinfo.ysp.cctv.cn/?"+qs, {
    headers:{"User-Agent":"qqlive","Accept":"application/json"},
  });
  const p = await resp.json();
  if(parseInt(p.iretcode) !== 0) throw new Error("iretcode="+p.iretcode+" "+p.errinfo);
  let urls = [];
  if(p.playurl) urls.push(p.playurl);
  let bu = p.backurl_list || p.backurlList || p.backurl;
  if(Array.isArray(bu)) bu.forEach(x=>urls.push(typeof x==="string"?x:(x.url||x.playurl||"")));
  else if(typeof bu==="string") urls.push(...bu.split(/[;,]/).filter(x=>x.trim()));
  urls = [...new Set(urls)].filter(u=>u && u.includes(".cctv."));
  if(!urls.length) throw new Error("no playurl");
  urls.sort((a,b)=>(a.includes("bklive-")?0:1)-(b.includes("bklive-")?0:1));
  return urls;
}

// ------------------------------------------------------------------
// 4. 路由处理
// ------------------------------------------------------------------
const CHANNEL_MAP = new Map(CHANNELS.map(c=>[c[0], {slug:c[0],name:c[1],sid:c[2],pid:c[3],defn:c[4],group:c[5]}]));

function buildM3U(origin){
  const lines = ["#EXTM3U"];
  for(const g of GROUPS){
    // 置顶分组
    if(g.id === "top"){
      lines.push(`#EXTINF:-1 tvg-logo="${g.logo}" group-title="${g.name}",${TOP_CHANNEL.name}`);
      lines.push(TOP_CHANNEL.url);
      continue;
    }
    for(const c of CHANNELS){
      if(c[5] !== g.id) continue;
      lines.push(`#EXTINF:-1 tvg-id="${c[0]}" tvg-name="${c[1]}" tvg-logo="${g.logo}" group-title="${g.name}",${c[1]}`);
      lines.push(`${origin}/play/${c[0]}`);
    }
  }
  return lines.join("\n") + "\n";
}

async function handlePlay(slug){
  const info = CHANNEL_MAP.get(slug);
  if(!info) return new Response("Not Found", {status:404});
  const { sid, pid, defn } = info;

  // 1) JCE 主协议
  if(!FORCE_BK.has(slug)){
    try{
      const now = Math.floor(Date.now()/1000);
      const url = await jceTimeshiftUrl(pid, sid, now-WINDOW, now, defn);
      if(url) return redirect(url);
    }catch(e){
      // 落到 bk
    }
  }
  // 2) bkliveinfo 备用
  try{
    const urls = await bkPlayUrls(sid, pid, defn);
    if(urls.length) return redirect(urls[0]);
  }catch(e){}
  return new Response("Play URL unavailable", {status:502});
}

function redirect(url){
  return new Response(null, {
    status:302,
    headers:{ "Location":url, "Cache-Control":"no-cache" },
  });
}

export default {
  async fetch(request){
    const u = new URL(request.url);
    const path = u.pathname;

    if(path === "/live.m3u" || path === "/live.m3u8"){
      const body = buildM3U(u.origin);
      return new Response(body, {
        headers:{
          "Content-Type":"application/vnd.apple.mpegurl; charset=utf-8",
          "Cache-Control":"no-cache",
          "Access-Control-Allow-Origin":"*",
        },
      });
    }

    if(path.startsWith("/play/")){
      return handlePlay(path.slice(6));
    }

    return new Response(
      `ysp-live · 央视频直播\n\nM3U: ${u.origin}/live.m3u\n播放: ${u.origin}/play/{slug}\n`,
      { headers:{"Content-Type":"text/plain; charset=utf-8"} }
    );
  },
};