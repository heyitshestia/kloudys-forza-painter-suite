async (page, options = {}) => {
  const withRecovery = require(path.join(__dirname, 'chrome-reload-adapter.cjs'));
  const source = fs.readFileSync(path.join(__dirname, 'regression-docking-edges.js'), 'utf8');
  const run = eval(`(${source})`);
  return withRecovery(page, output, () => run(page, { ...options, dockingEdgesSection: 'persistence' }));
}
