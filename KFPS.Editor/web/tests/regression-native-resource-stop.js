async () => {
  fs.writeFileSync(path.join(output, "stop-test.json"), JSON.stringify({
    reason: "Injected resource guard qualification, not real memory pressure", utc: Date.now(),
  }));
  await new Promise(resolve => setTimeout(resolve, 10000));
  throw Error("The native runner ignored the external stop marker");
}
