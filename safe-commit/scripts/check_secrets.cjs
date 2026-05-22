const { execSync } = require('child_process');

try {
  const stagedFiles = execSync('git diff --name-only --cached').toString().split('\n').filter(Boolean);
  const sensitivePatterns = [/\.json$/, /\.env$/, /\.pem$/, /\.key$/, /credentials/i, /secret/i];
  
  const badFiles = stagedFiles.filter(file => {
    // Ignore this script itself
    if (file.endsWith('check_secrets.cjs')) return false;
    return sensitivePatterns.some(pattern => pattern.test(file));
  });
  
  if (badFiles.length > 0) {
    console.log("❌ CRITICAL SECURITY WARNING: The following sensitive files are staged for commit:");
    badFiles.forEach(f => console.log(`  - ${f}`));
    console.log("\nPlease unstage these files before proceeding.");
    process.exit(1);
  } else {
    console.log("✅ No obvious sensitive files detected in staged changes.");
    process.exit(0);
  }
} catch (error) {
  // If no files are staged, git diff returns an error code. 
  // We can ignore it or handle it gracefully.
  if (error.status === 1 && !error.stderr.toString()) {
      // This usually means no changes or no staged files.
      process.exit(0);
  }
  console.error("Error checking staged files:", error.message);
  process.exit(1);
}
