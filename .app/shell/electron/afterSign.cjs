// Robust afterSign hook — ad-hoc deep sign สำหรับ macOS Sequoia 15+
//
// ปัญหา: `codesign --force --deep --sign -` อย่างเดียว (ที่ electron-builder
// default + simple afterSign hook ใช้) มัน DEPRECATED แล้วโดย Apple ตั้งแต่
// Catalina, และ Sequoia 15+ strict signature check รับไม่ผ่านถ้า:
//   - .node addon ใน app.asar.unpacked/ ไม่ได้ sign ตัวเอง
//   - native .dylib ใน node_modules/ ไม่ได้ sign ตัวเอง
//   - playwright/puppeteer browser binaries ใน Resources/ ไม่ได้ sign
//   - Helper apps ใน Frameworks/ มี signature นอก scope ของ --deep
// → Sequoia บอก "is damaged and can't be opened" (block แข็ง ไม่มีปุ่ม Open)
//
// แก้ด้วย inner-to-outer signing — sign ทุก binary ตัวในก่อน, แล้ว framework,
// แล้ว Helper apps, สุดท้าย root .app. ทำให้ทุก nested binary มี signature
// ของตัวเอง → strict verify ผ่าน → Sequoia ขึ้น "could not verify" (block อ่อน
// ที่มีปุ่ม Open Anyway) แทน "damaged".
//
// หมายเหตุ: ไม่ลบ quarantine xattr — quarantine ใส่ตอน user ดาวน์โหลด ไม่ใช่
// ตอน build. user mac ต้องทำเอง: `xattr -cr /Applications/<App>.app`
// (ดู Mac install section ใน README ของแต่ละแอป)

'use strict';

const { execSync } = require('node:child_process');
const fs = require('node:fs');

exports.default = async function afterSign(context) {
  if (context.electronPlatformName !== 'darwin') return;

  const appPath = `${context.appOutDir}/${context.packager.appInfo.productName}.app`;
  if (!fs.existsSync(appPath)) {
    console.warn(`[afterSign] skip: ${appPath} not found`);
    return;
  }

  console.log(`[afterSign] robust ad-hoc deep sign — ${appPath}`);

  const run = (label, cmd) => {
    try {
      execSync(cmd, { stdio: 'inherit' });
      return true;
    } catch (err) {
      console.warn(`[afterSign] ${label} failed (continuing): ${(err && err.message) || err}`);
      return false;
    }
  };

  // 1. sign .node + .dylib + .so addons individually
  //    inner binaries that --deep might miss in nested node_modules
  run('inner .node', `find "${appPath}" -type f -name "*.node" -exec codesign --force --sign - {} \\;`);
  run('inner .dylib', `find "${appPath}" -type f -name "*.dylib" -exec codesign --force --sign - {} \\;`);
  run('inner .so', `find "${appPath}" -type f -name "*.so" -exec codesign --force --sign - {} \\;`);

  // 2. sign every .framework bundle
  run('frameworks', `find "${appPath}/Contents" -type d -name "*.framework" -exec codesign --force --deep --sign - {} \\;`);

  // 3. sign nested .app bundles (Electron Helpers, browser binaries)
  run('helpers', `find "${appPath}/Contents" -type d -name "*.app" -exec codesign --force --deep --sign - {} \\;`);

  // 4. sign all Mach-O executables in Resources (covers playwright/chromium
  //    binaries, ffmpeg-static, etc — anything that's run as a subprocess)
  //    Use `file` to detect Mach-O so we don't mis-sign non-binaries.
  run(
    'resource binaries',
    `find "${appPath}/Contents/Resources" -type f -perm -u+x -exec sh -c 'file "$1" | grep -q "Mach-O" && codesign --force --sign - "$1" 2>/dev/null' _ {} \\;`,
  );

  // 5. final root sign — binds everything together
  run('root', `codesign --force --deep --sign - "${appPath}"`);

  // 6. verify (don't throw on failure — at least surface the message)
  run('verify', `codesign --verify --deep --strict --verbose=2 "${appPath}"`);

  console.log('[afterSign] done');
};
