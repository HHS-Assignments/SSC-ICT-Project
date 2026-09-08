#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(pwd)}"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "ERROR: frontend directory not found at: $FRONTEND_DIR"
  echo "Run this script from ~/Docker/ssc_ict_self_service_portal or pass the project root as the first argument."
  exit 1
fi

cd "$FRONTEND_DIR"

echo "== Patching frontend/tsconfig.json =="
cat > tsconfig.json <<'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noImplicitAny": false,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "types": ["vite/client", "react", "react-dom"]
  },
  "include": ["src"],
  "references": []
}
EOF

echo "== Patching frontend/package.json dependencies =="
node <<'NODE'
const fs = require('fs');
const path = 'package.json';
const pkg = JSON.parse(fs.readFileSync(path, 'utf8'));

pkg.scripts = pkg.scripts || {};
pkg.scripts.build = pkg.scripts.build || 'tsc && vite build';
pkg.scripts.dev = pkg.scripts.dev || 'vite';
pkg.scripts.preview = pkg.scripts.preview || 'vite preview';

pkg.dependencies = pkg.dependencies || {};
pkg.dependencies.react = pkg.dependencies.react || '^18.3.1';
pkg.dependencies['react-dom'] = pkg.dependencies['react-dom'] || '^18.3.1';

pkg.devDependencies = pkg.devDependencies || {};
pkg.devDependencies['@types/react'] = pkg.devDependencies['@types/react'] || '^18.3.12';
pkg.devDependencies['@types/react-dom'] = pkg.devDependencies['@types/react-dom'] || '^18.3.1';
pkg.devDependencies['@vitejs/plugin-react'] = pkg.devDependencies['@vitejs/plugin-react'] || '^4.3.3';
pkg.devDependencies.typescript = pkg.devDependencies.typescript || '^5.6.3';
pkg.devDependencies.vite = pkg.devDependencies.vite || '^5.4.10';

fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
console.log(fs.readFileSync(path, 'utf8'));
NODE

echo "== Removing stale frontend install artifacts =="
rm -rf node_modules package-lock.json dist

echo "== Installing frontend dependencies locally for verification =="
npm install

echo "== Running frontend production build locally =="
npm run build

echo "== Frontend patch and local build succeeded =="
echo "Next run from project root: ./docker_build_fix.sh"
