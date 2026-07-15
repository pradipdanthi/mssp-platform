# KB-021: Customer frontend foundation.
#
# Node/npm only inside this image. Vite dev server (not nginx production
# static build). Bind-mount + anonymous node_modules volume in
# docker-compose.yml enables host-side edits without host Node.
#
# package-lock.json is committed; use npm ci for reproducible installs.
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
