FROM node:22-alpine AS base
WORKDIR /app


# Dev target — all deps installed, runs Vite dev server with HMR.
# Used by docker-compose.override.yml.example for local development.
FROM base AS dev

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# Builder target — produces the production build/ directory.
FROM base AS builder

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npm run build && npm prune --omit=dev


# Runtime target — minimal image, only build/ + production node_modules.
# This is what `docker compose build frontend` (no override) produces.
FROM base AS runtime

ENV NODE_ENV=production \
    PORT=5173 \
    HOST=0.0.0.0

COPY --from=builder /app/build ./build
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

EXPOSE 5173
CMD ["node", "build/index.js"]
