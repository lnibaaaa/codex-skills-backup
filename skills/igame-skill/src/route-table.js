const fs = require('fs');
const path = require('path');

class RouteTable {
  constructor(jsonPath) {
    const raw = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
    this.modules = {};
    this.flatRoutes = new Map();

    for (const [moduleName, subModules] of Object.entries(raw)) {
      const normalizedName = moduleName === '_root' ? '_common' : moduleName;
      this.modules[normalizedName] = {};

      for (const [subName, apis] of Object.entries(subModules)) {
        this.modules[normalizedName][subName] = apis;
        for (const api of apis) {
          const routeKey = `/${normalizedName}/${subName}/${api.name}`;
          this.flatRoutes.set(routeKey, { ...api, module: normalizedName, sub: subName });
        }
      }
    }
  }

  listModules() {
    return Object.entries(this.modules).map(([name, subs]) => {
      let totalApis = 0;
      for (const apis of Object.values(subs)) totalApis += apis.length;
      return { name, subModules: Object.keys(subs).length, totalApis };
    });
  }

  listSubModules(moduleName) {
    const mod = this.modules[moduleName];
    if (!mod) return null;
    return Object.entries(mod).map(([name, apis]) => ({
      name,
      apis: apis.map(a => ({
        name: a.name,
        method: a.method,
        description: a.description || `${a.method} ${a.path}`
      }))
    }));
  }

  listApis(moduleName, subName) {
    const mod = this.modules[moduleName];
    if (!mod || !mod[subName]) return null;
    return mod[subName].map(a => ({
      name: a.name,
      method: a.method,
      path: a.path,
      params: a.params,
      description: a.description || ''
    }));
  }

  describeApi(routePath) {
    const parts = routePath.replace(/^\/+/, '').split('/');
    if (parts.length === 3) {
      const [mod, sub, name] = parts;
      return this.flatRoutes.get(`/${mod}/${sub}/${name}`) || null;
    }
    if (parts.length === 2) {
      const [mod, name] = parts;
      for (const [sub, apis] of Object.entries(this.modules[mod] || {})) {
        const found = apis.find(a => a.name === name);
        if (found) return { ...found, module: mod, sub };
      }
    }
    return null;
  }

  resolve(routePath) {
    const parts = routePath.replace(/^\/+/, '').split('/');
    if (parts.length === 0 || (parts.length === 1 && parts[0] === '')) {
      return { type: 'root', data: this.listModules() };
    }
    if (parts.length === 1) {
      const subs = this.listSubModules(parts[0]);
      if (subs) return { type: 'module', module: parts[0], data: subs };
      return { type: 'not_found', path: routePath };
    }
    if (parts.length === 2) {
      const apis = this.listApis(parts[0], parts[1]);
      if (apis) return { type: 'submodule', module: parts[0], sub: parts[1], data: apis };
      const desc = this.describeApi(routePath);
      if (desc) return { type: 'api', data: desc };
      return { type: 'not_found', path: routePath };
    }
    if (parts.length === 3) {
      const desc = this.describeApi(routePath);
      if (desc) return { type: 'api', data: desc };
      return { type: 'not_found', path: routePath };
    }
    return { type: 'not_found', path: routePath };
  }
}

module.exports = { RouteTable };
