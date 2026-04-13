#!/usr/bin/env node
const path = require('path');
const fs = require('fs');
const { RouteTable } = require('../src/route-table');

const AUTH_FILE = path.join(process.env.HOME, '.igame-auth.json');
const ROUTES_FILE = path.resolve(__dirname, '../igame-routes.json');
const API_HOST = 'https://webgw-cn.tap4fun.com';

// Supported game aliases → gameId mapping
const GAME_IDS = {
  p2:   '1041',
  x2:   '1089',
  x9:   '1108',
  x3:   '1133',
  '1041': '1041',
  '1089': '1089',
  '1108': '1108',
  '1133': '1133',
};

function parseArgs(argv) {
  // Strip node + script from argv, then find --game <value> anywhere in the args
  const args = argv.slice(2);
  let gameOverride = null;
  const filtered = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--game' && args[i + 1]) {
      gameOverride = args[++i];
    } else {
      filtered.push(args[i]);
    }
  }
  return { gameOverride, args: filtered };
}

function loadAuth(gameOverride) {
  if (!fs.existsSync(AUTH_FILE)) {
    console.error('ERROR: 认证文件不存在。请先运行 setup-auth.sh 配置认证信息。');
    console.error('  文件路径: ' + AUTH_FILE);
    console.error('  或手动创建，格式: {"token":"...","clientId":"...","gameId":"1041","regionId":"201"}');
    process.exit(1);
  }
  const auth = JSON.parse(fs.readFileSync(AUTH_FILE, 'utf-8'));
  if (gameOverride) {
    const resolved = GAME_IDS[gameOverride.toLowerCase()];
    if (!resolved) {
      console.error(`ERROR: 未知游戏 "${gameOverride}"，支持: ${Object.keys(GAME_IDS).filter(k => isNaN(k)).join(', ')}`);
      process.exit(1);
    }
    auth.gameId = resolved;
  }
  return auth;
}

function buildUrl(templatePath, params) {
  let url = templatePath;
  const usedParams = new Set();
  url = url.replace(/\{(\w+)\}/g, (_, key) => {
    for (const [k, v] of Object.entries(params)) {
      if (k === key || k.toLowerCase().includes(key.toLowerCase())) {
        usedParams.add(k);
        return encodeURIComponent(v);
      }
    }
    return `{${key}}`;
  });
  const remaining = {};
  for (const [k, v] of Object.entries(params)) {
    if (!usedParams.has(k)) remaining[k] = v;
  }
  return { url, remaining };
}

async function callApi(apiPath, method, params, auth) {
  const { url, remaining } = buildUrl(apiPath, params);
  const fullUrl = new URL('/ark' + url, API_HOST);

  const fetchOptions = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${auth.token}`,
      'clientid': auth.clientId,
      'gameid': auth.gameId || '1041',
      'regionid': auth.regionId || '201',
      'origin': 'https://igame.tap4fun.com',
      'referer': 'https://igame.tap4fun.com/',
    },
  };

  if (method === 'GET') {
    for (const [k, v] of Object.entries(remaining)) {
      fullUrl.searchParams.set(k, String(v));
    }
  } else {
    fetchOptions.body = JSON.stringify(remaining);
  }

  const resp = await fetch(fullUrl.toString(), fetchOptions);
  return resp.json();
}

async function main() {
  const { gameOverride, args } = parseArgs(process.argv);
  const [command, routePath, paramsJson] = args;

  if (!command) {
    console.log('iGame CLI\n');
    console.log('用法:');
    console.log('  igame-query.js [--game p2|x2|x9|x3] ls [path]                    列出模块/接口');
    console.log('  igame-query.js [--game p2|x2|x9|x3] describe <path>              查看接口详情');
    console.log('  igame-query.js [--game p2|x2|x9|x3] read <path> [params_json]    调用 GET 接口');
    console.log('  igame-query.js [--game p2|x2|x9|x3] write <path> [params_json]   调用写接口');
    console.log('\n示例:');
    console.log('  igame-query.js --game p2 read "serverMgr/serverList/getServerList" \'{"pageIndex":1,"pageSize":5}\'');
    console.log('  igame-query.js --game x2 write "serverMgr/serverList/setServerRate" \'{"id":"2936","serverRate":400}\'');
    console.log('  igame-query.js ls ""                        # 使用 auth 文件中的默认 gameId');
    process.exit(0);
  }

  const rt = new RouteTable(ROUTES_FILE);

  if (command === 'ls') {
    const result = rt.resolve(routePath || '');
    if (result.type === 'not_found') {
      console.log('路径不存在:', routePath);
      process.exit(1);
    }
    if (result.type === 'root') {
      console.log('iGame 模块列表:\n');
      for (const m of result.data) {
        console.log(`  ${m.name.padEnd(28)} ${String(m.totalApis).padStart(4)} 个接口  (${m.subModules} 个子模块)`);
      }
      console.log(`\n共 ${result.data.length} 个模块`);
    } else if (result.type === 'module') {
      console.log(`${result.module} 模块:\n`);
      for (const sub of result.data) {
        console.log(`  ${sub.name} (${sub.apis.length} 个接口)`);
        for (const api of sub.apis) {
          const desc = api.description ? ` — ${api.description}` : '';
          console.log(`      ${api.method.padEnd(7)} ${api.name}${desc}`);
        }
      }
    } else if (result.type === 'submodule') {
      console.log(`${result.module}/${result.sub}:\n`);
      for (const api of result.data) {
        const desc = api.description ? ` — ${api.description}` : '';
        console.log(`  ${api.method.padEnd(7)} ${api.name.padEnd(30)} ${api.path}${desc}`);
      }
    } else if (result.type === 'api') {
      const a = result.data;
      console.log(`${a.name}: ${a.method} ${a.path} (${a.params.join(', ')}) ${a.description || ''}`);
    }
    return;
  }

  if (command === 'describe') {
    if (!routePath) { console.log('请提供接口路径'); process.exit(1); }
    const desc = rt.describeApi(routePath);
    if (!desc) { console.log('接口不存在:', routePath); process.exit(1); }
    console.log(`名称: ${desc.name}`);
    console.log(`模块: ${desc.module}/${desc.sub}`);
    console.log(`方法: ${desc.method}`);
    console.log(`路径: /ark${desc.path}`);
    console.log(`参数: ${desc.params.length > 0 ? desc.params.join(', ') : '无'}`);
    console.log(`描述: ${desc.description || '无'}`);
    return;
  }

  if (command === 'read' || command === 'write') {
    if (!routePath) { console.log('请提供接口路径'); process.exit(1); }
    const api = rt.describeApi(routePath);
    if (!api) { console.log('接口不存在:', routePath); process.exit(1); }

    if (command === 'read' && api.method !== 'GET') {
      console.log(`接口 ${api.name} 是 ${api.method} 方法，请使用 write 命令`);
      process.exit(1);
    }
    if (command === 'write' && api.method === 'GET') {
      console.log(`接口 ${api.name} 是 GET 方法，请使用 read 命令`);
      process.exit(1);
    }

    const auth = loadAuth(gameOverride);
    const params = paramsJson ? JSON.parse(paramsJson) : {};
    const result = await callApi(api.path, api.method, params, auth);
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  console.log('未知命令:', command);
  process.exit(1);
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
