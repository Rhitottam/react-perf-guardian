import { ReactAstAnalyzer } from "./analyzer.js";
import * as fs from "fs";
import * as readline from "readline";

const analyzer = new ReactAstAnalyzer();

async function main() {
  const args = process.argv.slice(2);

  if (args.length > 0 && args[0] !== "-") {
    // File path provided
    const code = fs.readFileSync(args[0], "utf-8");
    const result = analyzer.parse(code, args[0]);
    console.log(JSON.stringify(result, null, 2));
  } else {
    // Read from stdin
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false
    });

    let code = "";
    for await (const line of rl) {
      code += line + "\n";
    }

    const result = analyzer.parse(code);
    console.log(JSON.stringify(result, null, 2));
  }
}

main().catch(console.error);
