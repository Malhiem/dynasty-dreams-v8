// Guards the build configuration: these are the mistakes that made the app
// unbuildable (wrong entry point, undeclared imports, missing assets, placeholder ids).
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8')).expo;

function sourceFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? sourceFiles(path.join(dir, e.name)) : /\.(js|jsx|ts|tsx)$/.test(e.name) ? [path.join(dir, e.name)] : []);
}

describe('mobile build configuration', () => {
  test('entry point matches how the app is written (App.js + React Navigation, no expo-router)', () => {
    expect(fs.existsSync(path.join(root, 'App.js'))).toBe(true);
    expect(pkg.main).toBe('node_modules/expo/AppEntry.js');
    expect(pkg.dependencies['expo-router']).toBeUndefined();
    expect(app.plugins || []).not.toContain('expo-router');
    expect(fs.existsSync(path.join(root, 'app'))).toBe(false); // no half-present router folder
  });

  test('every package the code imports is declared as a dependency', () => {
    const declared = new Set(Object.keys(pkg.dependencies));
    const used = new Set();
    for (const file of [path.join(root, 'App.js'), ...sourceFiles(path.join(root, 'src'))]) {
      const text = fs.readFileSync(file, 'utf8');
      for (const m of text.matchAll(/from ['"]([^./'"][^'"]*)['"]/g)) {
        const parts = m[1].split('/');
        used.add(m[1].startsWith('@') ? parts.slice(0, 2).join('/') : parts[0]);
      }
    }
    const missing = [...used].filter((name) => !declared.has(name));
    expect(missing).toEqual([]);
  });

  test('every relative import resolves to a file', () => {
    const missing = [];
    for (const file of [path.join(root, 'App.js'), ...sourceFiles(path.join(root, 'src'))]) {
      const text = fs.readFileSync(file, 'utf8');
      for (const m of text.matchAll(/from ['"](\.[^'"]+)['"]/g)) {
        const base = path.resolve(path.dirname(file), m[1]);
        const ok = ['', '.js', '.jsx', '.ts', '.tsx', '/index.js'].some((ext) => fs.existsSync(base + ext) && fs.statSync(base + ext).isFile());
        if (!ok) missing.push(`${path.relative(root, file)} -> ${m[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });

  test('assets referenced by app.json exist', () => {
    const refs = [app.icon, app.splash?.image, app.android?.adaptiveIcon?.foregroundImage, app.web?.favicon].filter(Boolean);
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) expect(fs.existsSync(path.join(root, ref))).toBe(true);
  });

  test('no placeholder EAS project id is shipped', () => {
    const json = fs.readFileSync(path.join(root, 'app.json'), 'utf8');
    expect(json).not.toMatch(/0{8}-0{4}-0{4}-0{4}-0{12}/);
    const config = require('../app.config.js')({ config: app });
    expect(config.extra.eas.projectId).toBe(process.env.EXPO_PUBLIC_EAS_PROJECT_ID || undefined);
  });
});
