/**
 * Post-build copy steps for Docker/Linux and local.
 * - Copy built index.html to ../lms/www/lms.html (create www if needed).
 * - Copy frappe-ui colors.json if present in node_modules; otherwise keep repo copy.
 */
const fs = require("fs");
const path = require("path");

const cwd = process.cwd();

// copy-html-entry: ensure ../lms/www exists, then copy index.html -> lms.html
const htmlSource = path.join(cwd, "..", "lms", "public", "frontend", "index.html");
const htmlDest = path.join(cwd, "..", "lms", "www", "lms.html");

// Ensure www directory exists
fs.mkdirSync(path.dirname(htmlDest), { recursive: true });

// Check if source exists and copy it
if (fs.existsSync(htmlSource)) {
	fs.copyFileSync(htmlSource, htmlDest);
	console.log("postbuild: copied index.html to lms.html");
} else if (fs.existsSync(htmlDest)) {
	// frappe-ui plugin already output directly to destination
	console.log("postbuild: lms.html already exists (handled by frappe-ui plugin)");
} else {
	console.error("postbuild: missing build output - neither source nor destination exists");
	console.error("  source:", htmlSource);
	console.error("  dest:", htmlDest);
	process.exit(1);
}

// copy-colors-json: only if frappe-ui ships the file (e.g. not in published npm package)
const colorsSource = path.join(cwd, "node_modules", "frappe-ui", "src", "tailwind", "colors.json");
const colorsDest = path.join(cwd, "src", "utils", "frappe-ui-colors.json");
if (fs.existsSync(colorsSource)) {
	fs.copyFileSync(colorsSource, colorsDest);
}
