# Builds the SPA and serves it through the E2E same-origin Nginx proxy.
FROM docker.io/library/node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json ./package.json
RUN corepack enable && yarn install --no-lockfile

COPY frontend/ ./
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN DISABLE_ESLINT_PLUGIN=true yarn build

FROM docker.io/library/nginx:1.27-alpine

COPY --from=build /app/build /usr/share/nginx/html
COPY e2e/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
