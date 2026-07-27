FROM node:22.20.0-alpine AS build

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_CSRF_COOKIE_NAME=maintenance_csrf

ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_CSRF_COOKIE_NAME=${NEXT_PUBLIC_CSRF_COOKIE_NAME}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22.20.0-alpine AS runtime

ARG RELEASE_IDENTIFIER=unverified
ARG RELEASE_GIT_COMMIT=unverified

LABEL org.opencontainers.image.title="AI Maintenance Copilot frontend" \
      org.opencontainers.image.version="${RELEASE_IDENTIFIER}" \
      org.opencontainers.image.revision="${RELEASE_GIT_COMMIT}"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
USER node

COPY --from=build --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
