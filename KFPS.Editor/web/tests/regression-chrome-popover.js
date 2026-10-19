async (page, options = {}) => {
  const errors = [];
  const record = error => errors.push({ message: error.message, stack: error.stack });
  page.on('pageerror', record);
  try {
    const source = fs.readFileSync(path.join(__dirname, 'regression-docked-editing.js'), 'utf8');
    const run = eval(`(${source})`);
    return await run(page, options);
  } finally {
    page.off('pageerror', record);
    fs.writeFileSync(path.join(output, 'popover-errors.json'), JSON.stringify(errors, null, 2));
  }
}
