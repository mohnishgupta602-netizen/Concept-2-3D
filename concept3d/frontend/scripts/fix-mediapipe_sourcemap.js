const fs = require('fs');
const path = require('path');

const mapPath = path.join(__dirname, '..', 'node_modules', '@mediapipe', 'tasks-vision', 'vision_bundle_mjs.js.map');
try {
  // Create parent dir if needed
  fs.mkdirSync(path.dirname(mapPath), { recursive: true });
  let writeMap = false;
  if (!fs.existsSync(mapPath)) {
    writeMap = true;
  } else {
    try {
      const content = fs.readFileSync(mapPath, { encoding: 'utf8' });
      const parsed = JSON.parse(content || '{}');
      // If parsed map doesn't have a `sources` array, replace it
      if (!Array.isArray(parsed.sources)) {
        writeMap = true;
      }
    } catch (err) {
      writeMap = true;
    }
  }

  if (writeMap) {
    const minimalMap = {
      version: 3,
      file: 'vision_bundle_mjs.js',
      sources: [],
      names: [],
      mappings: ''
    };
    fs.writeFileSync(mapPath, JSON.stringify(minimalMap), { encoding: 'utf8' });
    console.log('[fix-mediapipe_sourcemap] Wrote minimal source map file:', mapPath);
  }
} catch (err) {
  // don't fail the start if this can't be written
  console.warn('[fix-mediapipe_sourcemap] Could not create map file:', err.message);
}
