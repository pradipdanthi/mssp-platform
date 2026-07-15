# KB-018: Admin frontend foundation.
#
# Node/npm are intentionally required only inside this image - never on the
# VM host (no Node.js/npm is installed there, and none should be). This is
# a development-phase image: it runs Vite's own dev server (not a
# production nginx static build - see docs/KB018 completion notes once
# written), so that editing files under frontend-admin/src on the host is
# visible on a page refresh without rebuilding this image, via the bind
# mount + anonymous node_modules volume configured in docker-compose.yml.
#
# frontend-admin/package-lock.json is committed with this module.
# `npm ci` is used for reproducible installs from the lockfile.
# Do not switch back to `npm install` unless the lockfile strategy changes.
FROM node:20-alpine

WORKDIR /app

# COPY package*.json ./ matches package.json unconditionally and
# package-lock.json only if present - it does not fail when the lockfile
# does not exist yet.
COPY package*.json ./
RUN npm ci

COPY . .

# Vite's dev server host/port are configured in vite.config.ts
# (server.host = "0.0.0.0", server.port = 5173) so there is exactly one
# place that setting lives, kept in sync with the "3000:5173" port mapping
# in docker-compose.yml.
EXPOSE 5173

CMD ["npm", "run", "dev"]
