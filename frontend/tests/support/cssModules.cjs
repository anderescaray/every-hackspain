// Los tests de Node renderizan componentes que importan CSS modules; Next los resuelve en build,
// pero el runner no. Cada `styles.clase` devuelve su propio nombre para que el marcado sea comprobable.
const Module = require("node:module");
Module._extensions[".css"] = (module) => {
  const classes = new Proxy({}, { get: (_target, key) => (typeof key === "string" ? key : undefined) });
  module.exports = { __esModule: true, default: classes };
};
