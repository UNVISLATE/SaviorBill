# syntax=docker/dockerfile:1

# ── 1. Сборка React SPA фронтенда ─────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Аргументы сборки для динамической информации в About ("О системе")
ARG VITE_GIT_COMMIT=""
ARG VITE_GIT_COMMIT_DATE=""
ARG VITE_APP_VERSION=""

ENV VITE_GIT_COMMIT=$VITE_GIT_COMMIT \
    VITE_GIT_COMMIT_DATE=$VITE_GIT_COMMIT_DATE \
    VITE_APP_VERSION=$VITE_APP_VERSION

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run build

# ── 2. Раздача статики через Nginx Alpine ─────────────────────────────────────
FROM nginx:alpine AS runtime

RUN rm -rf /usr/share/nginx/html/*

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
