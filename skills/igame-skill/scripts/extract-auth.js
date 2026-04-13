// TapFS 自动提取认证信息
// 在 igame.tap4fun.com 页面上下文中执行
// 通过 osascript 注入 Chrome，或手动粘贴到 Console
// 输出: JSON {token, clientId}
(function() {
  var token = localStorage.getItem('ark_token');
  if (!token) return JSON.stringify({error: 'NO_TOKEN', hint: '请先登录 igame.tap4fun.com'});

  // MD5 (RFC 1321, 输出 base64, 和 Node.js crypto.createHash('md5').digest('base64') 一致)
  function md5(string) {
    function cmn(q,a,b,x,s,t) { a = add(add(a,q), add(x,t)); return add(a<<s | a>>>(32-s), b); }
    function ff(a,b,c,d,x,s,t) { return cmn((b&c)|((~b)&d),a,b,x,s,t); }
    function gg(a,b,c,d,x,s,t) { return cmn((b&d)|(c&(~d)),a,b,x,s,t); }
    function hh(a,b,c,d,x,s,t) { return cmn(b^c^d,a,b,x,s,t); }
    function ii(a,b,c,d,x,s,t) { return cmn(c^(b|(~d)),a,b,x,s,t); }
    function add(a,b) { var l=(a&0xFFFF)+(b&0xFFFF); return ((a>>16)+(b>>16)+(l>>16))<<16|(l&0xFFFF); }
    var k, n = string.length, i, a = 1732584193, b = -271733879, c = -1732584194, d = 271733878, x = [];
    var bytes = [];
    for (i = 0; i < n; i++) {
      var code = string.charCodeAt(i);
      if (code < 0x80) bytes.push(code);
      else if (code < 0x800) { bytes.push(0xC0|(code>>6), 0x80|(code&0x3F)); }
      else if (code < 0xD800 || code >= 0xE000) { bytes.push(0xE0|(code>>12), 0x80|((code>>6)&0x3F), 0x80|(code&0x3F)); }
      else { i++; code = 0x10000+((code&0x3FF)<<10)|(string.charCodeAt(i)&0x3FF); bytes.push(0xF0|(code>>18), 0x80|((code>>12)&0x3F), 0x80|((code>>6)&0x3F), 0x80|(code&0x3F)); }
    }
    n = bytes.length;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    var bits = n * 8;
    bytes.push(bits&0xFF, (bits>>8)&0xFF, (bits>>16)&0xFF, (bits>>24)&0xFF, 0, 0, 0, 0);
    for (i = 0; i < bytes.length; i += 4) x.push(bytes[i]|(bytes[i+1]<<8)|(bytes[i+2]<<16)|(bytes[i+3]<<24));
    for (k = 0; k < x.length; k += 16) {
      var p = [a,b,c,d];
      a=ff(a,b,c,d,x[k+0],7,-680876936);d=ff(d,a,b,c,x[k+1],12,-389564586);c=ff(c,d,a,b,x[k+2],17,606105819);b=ff(b,c,d,a,x[k+3],22,-1044525330);
      a=ff(a,b,c,d,x[k+4],7,-176418897);d=ff(d,a,b,c,x[k+5],12,1200080426);c=ff(c,d,a,b,x[k+6],17,-1473231341);b=ff(b,c,d,a,x[k+7],22,-45705983);
      a=ff(a,b,c,d,x[k+8],7,1770035416);d=ff(d,a,b,c,x[k+9],12,-1958414417);c=ff(c,d,a,b,x[k+10],17,-42063);b=ff(b,c,d,a,x[k+11],22,-1990404162);
      a=ff(a,b,c,d,x[k+12],7,1804603682);d=ff(d,a,b,c,x[k+13],12,-40341101);c=ff(c,d,a,b,x[k+14],17,-1502002290);b=ff(b,c,d,a,x[k+15],22,1236535329);
      a=gg(a,b,c,d,x[k+1],5,-165796510);d=gg(d,a,b,c,x[k+6],9,-1069501632);c=gg(c,d,a,b,x[k+11],14,643717713);b=gg(b,c,d,a,x[k+0],20,-373897302);
      a=gg(a,b,c,d,x[k+5],5,-701558691);d=gg(d,a,b,c,x[k+10],9,38016083);c=gg(c,d,a,b,x[k+15],14,-660478335);b=gg(b,c,d,a,x[k+4],20,-405537848);
      a=gg(a,b,c,d,x[k+9],5,568446438);d=gg(d,a,b,c,x[k+14],9,-1019803690);c=gg(c,d,a,b,x[k+3],14,-187363961);b=gg(b,c,d,a,x[k+8],20,1163531501);
      a=gg(a,b,c,d,x[k+13],5,-1444681467);d=gg(d,a,b,c,x[k+2],9,-51403784);c=gg(c,d,a,b,x[k+7],14,1735328473);b=gg(b,c,d,a,x[k+12],20,-1926607734);
      a=hh(a,b,c,d,x[k+5],4,-378558);d=hh(d,a,b,c,x[k+8],11,-2022574463);c=hh(c,d,a,b,x[k+11],16,1839030562);b=hh(b,c,d,a,x[k+14],23,-35309556);
      a=hh(a,b,c,d,x[k+1],4,-1530992060);d=hh(d,a,b,c,x[k+4],11,1272893353);c=hh(c,d,a,b,x[k+7],16,-155497632);b=hh(b,c,d,a,x[k+10],23,-1094730640);
      a=hh(a,b,c,d,x[k+13],4,681279174);d=hh(d,a,b,c,x[k+0],11,-358537222);c=hh(c,d,a,b,x[k+3],16,-722521979);b=hh(b,c,d,a,x[k+6],23,76029189);
      a=hh(a,b,c,d,x[k+9],4,-640364487);d=hh(d,a,b,c,x[k+12],11,-421815835);c=hh(c,d,a,b,x[k+15],16,530742520);b=hh(b,c,d,a,x[k+2],23,-995338651);
      a=ii(a,b,c,d,x[k+0],6,-198630844);d=ii(d,a,b,c,x[k+7],10,1126891415);c=ii(c,d,a,b,x[k+14],15,-1416354905);b=ii(b,c,d,a,x[k+5],21,-57434055);
      a=ii(a,b,c,d,x[k+12],6,1700485571);d=ii(d,a,b,c,x[k+3],10,-1894986606);c=ii(c,d,a,b,x[k+10],15,-1051523);b=ii(b,c,d,a,x[k+1],21,-2054922799);
      a=ii(a,b,c,d,x[k+8],6,1873313359);d=ii(d,a,b,c,x[k+15],10,-30611744);c=ii(c,d,a,b,x[k+6],15,-1560198380);b=ii(b,c,d,a,x[k+13],21,1309151649);
      a=ii(a,b,c,d,x[k+4],6,-145523070);d=ii(d,a,b,c,x[k+11],10,-1120210379);c=ii(c,d,a,b,x[k+2],15,718787259);b=ii(b,c,d,a,x[k+9],21,-343485551);
      a=add(a,p[0]);b=add(b,p[1]);c=add(c,p[2]);d=add(d,p[3]);
    }
    var hash = [a,b,c,d], out = [];
    for (i = 0; i < 4; i++) out.push(hash[i]&0xFF, (hash[i]>>8)&0xFF, (hash[i]>>16)&0xFF, (hash[i]>>24)&0xFF);
    var b64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    var result = '';
    for (i = 0; i < out.length; i += 3) {
      var v = (out[i]<<16) | ((out[i+1]||0)<<8) | (out[i+2]||0);
      result += b64[(v>>18)&63] + b64[(v>>12)&63];
      result += (i+1 < out.length) ? b64[(v>>6)&63] : '=';
      result += (i+2 < out.length) ? b64[v&63] : '=';
    }
    return result;
  }

  // Canvas 指纹 (1:1 复刻 @t4f/login-token/src/getClientId.ts)
  function save(c) { return c.toDataURL(); }
  function makeTextImage(canvas, ctx) {
    canvas.width = 240; canvas.height = 60;
    ctx.textBaseline = 'alphabetic'; ctx.fillStyle = '#f60'; ctx.fillRect(100, 1, 62, 20);
    ctx.fillStyle = '#069'; ctx.font = '11pt "Times New Roman"';
    var t = 'Cwm fjordbank gly ' + String.fromCharCode(55357, 56835);
    ctx.fillText(t, 2, 15); ctx.fillStyle = 'rgba(102, 204, 0, 0.2)'; ctx.font = '18pt Arial'; ctx.fillText(t, 4, 45);
    return save(canvas);
  }
  function makeGeometryImage(canvas, ctx) {
    canvas.width = 122; canvas.height = 110; ctx.globalCompositeOperation = 'multiply';
    var cs = [['#f2f',40,40],['#2ff',80,40],['#ff2',60,80]];
    for (var i = 0; i < cs.length; i++) { ctx.fillStyle = cs[i][0]; ctx.beginPath(); ctx.arc(cs[i][1], cs[i][2], 40, 0, Math.PI*2, true); ctx.closePath(); ctx.fill(); }
    ctx.fillStyle = '#f9c'; ctx.arc(60, 60, 60, 0, Math.PI*2, true); ctx.arc(60, 60, 20, 0, Math.PI*2, true); ctx.fill('evenodd');
    return save(canvas);
  }
  function doesSupportWinding(ctx) { ctx.rect(0,0,10,10); ctx.rect(2,2,6,6); return !ctx.isPointInPath(5,5,'evenodd'); }
  function getClientId() {
    try {
      var canvas = document.createElement('canvas'); canvas.width = 1; canvas.height = 1;
      var ctx = canvas.getContext('2d');
      if (!ctx || !canvas.toDataURL) return navigator.userAgent;
      var w = doesSupportWinding(ctx), g = makeGeometryImage(canvas, ctx), t = makeTextImage(canvas, ctx);
      return (+w) + md5(g) + md5(t);
    } catch(e) { return navigator.userAgent; }
  }

  return JSON.stringify({ token: token, clientId: getClientId() });
})()
