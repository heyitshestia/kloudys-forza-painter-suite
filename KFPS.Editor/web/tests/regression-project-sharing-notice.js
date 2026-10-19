async (page, options = {}) => {
  // Keep this historical suite entry executable with the replacement contract.
  const source=fs.readFileSync(path.join(__dirname,'regression-startup-tips.js'),'utf8');
  const result=await eval('('+source+')')(page,options);
  return {...result,retired:'Sharing acknowledgment popup intentionally removed; initial help, dormant flags, manual Help and destructive confirmation exercised instead.'};
}
