# Runs the Playwright suite inside the same Compose network as the application.
FROM mcr.microsoft.com/playwright:v1.58.0-noble

WORKDIR /work

COPY e2e/package.json ./package.json
RUN npm install --global yarn@1.22.22 && yarn install --no-lockfile

COPY e2e/ ./e2e/
RUN rm -rf e2e/node_modules

CMD ["node", "e2e/run.mjs"]
