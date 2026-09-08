#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "== SSC-ICT Docker deployment check =="
echo "Project root: $PROJECT_ROOT"

echo "\n== 1. Docker version =="
sudo docker version --format 'Docker Client {{.Client.Version}} / Server {{.Server.Version}}'
sudo docker compose version

echo "\n== 2. DNS checks inside Docker runtime =="
if sudo docker run --rm python:3.12-slim python -c "import socket; print(socket.gethostbyname('pypi.org'))"; then
  echo "Docker runtime can resolve pypi.org"
else
  echo "WARNING: Docker runtime cannot resolve pypi.org. Configure /etc/docker/daemon.json DNS if the build still fails."
fi

if sudo docker run --rm node:22-alpine sh -c "node -e \"require('dns').lookup('registry.npmjs.org',(e,a)=>{if(e){console.error(e);process.exit(1)}; console.log(a)})\""; then
  echo "Docker runtime can resolve registry.npmjs.org"
else
  echo "WARNING: Docker runtime cannot resolve registry.npmjs.org. Configure /etc/docker/daemon.json DNS if the build still fails."
fi

echo "\n== 3. Clean previous containers =="
sudo docker compose down --remove-orphans || true

echo "\n== 4. Build images =="
if sudo docker compose build --no-cache; then
  echo "Compose build succeeded."
else
  echo "Compose build failed. Trying explicit docker build --network=host fallback..."
  sudo docker build --network=host --no-cache -t ssc_ict_self_service_portal-api:local ./backend
  sudo docker build --network=host --no-cache -t ssc_ict_self_service_portal-frontend:local ./frontend
fi

echo "\n== 5. Start application =="
sudo docker compose up -d

echo "\n== 6. Container status =="
sudo docker compose ps

echo "\n== 7. API health check =="
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health >/tmp/ssc_ict_health.json; then
    cat /tmp/ssc_ict_health.json
    echo "\nAPI is healthy."
    echo "Frontend: http://localhost:8080"
    echo "API docs: http://localhost:8000/docs"
    exit 0
  fi
  sleep 1
done

echo "API did not become healthy in time. Showing logs:"
sudo docker compose logs --tail=100 api
exit 1
